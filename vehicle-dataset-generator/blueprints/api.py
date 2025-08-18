import json
import os
import uuid

from flask import Blueprint, request, jsonify, current_app, Response
from werkzeug.utils import secure_filename

from database import db
from dataset_generator import dataset_generator
from vehicle_analysis import analyzer
from vehicle_detection import detector

api = Blueprint('api', __name__, url_prefix='/api')

def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@api.route('/upload', methods=['POST'])
def upload_files():
    """다중 이미지 업로드"""
    try:
        if 'files' not in request.files:
            return jsonify({'status': 'error', 'message': 'No files provided'}), 400
        
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'status': 'error', 'message': 'No files selected'}), 400
        
        uploaded_files = []
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        for file in files:
            if file and allowed_file(file.filename):
                # 안전한 파일명 생성
                filename = secure_filename(file.filename)
                unique_filename = f"{uuid.uuid4()}_{filename}"
                file_path = os.path.join(upload_folder, unique_filename)
                
                # 파일 저장
                file.save(file_path)
                
                uploaded_files.append({
                    'original_name': filename,
                    'file_path': file_path,
                    'unique_name': unique_filename
                })
        
        return jsonify({
            'status': 'success',
            'message': f'{len(uploaded_files)} files uploaded successfully',
            'files': uploaded_files
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api.route('/detect', methods=['POST'])
def detect_vehicles():
    """차량 탐지 API"""
    try:
        data = request.get_json()
        if not data or 'file_path' not in data:
            return jsonify({'status': 'error', 'message': 'File path required'}), 400
        
        file_path = data['file_path']
        if not os.path.exists(file_path):
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        # 차량 탐지
        vehicles = detector.detect_vehicles(file_path)
        
        return jsonify({
            'status': 'success',
            'vehicles': vehicles
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api.route('/analyze', methods=['POST'])
def analyze_vehicle():
    """차량 분석 API (다중 이미지 스트리밍)"""
    try:
        data = request.get_json()
        
        # 다중 이미지 분석을 위한 데이터 구조 체크
        if not data:
            return jsonify({'status': 'error', 'message': 'No data provided'}), 400
        
        # 단일 이미지 분석 (기존 호환성)
        if 'file_path' in data:
            file_path = data['file_path']
            bbox = data.get('bbox')
            
            if not os.path.exists(file_path):
                return jsonify({'status': 'error', 'message': 'File not found'}), 404
            
            return _analyze_single_image_stream(file_path, bbox)
        
        # 다중 이미지 분석
        elif 'images' in data:
            images = data['images']
            
            if not isinstance(images, list) or len(images) == 0:
                return jsonify({'status': 'error', 'message': 'Images array required'}), 400
            
            # 이미지 파일 존재 여부 확인
            for img_data in images:
                if 'file_path' not in img_data:
                    return jsonify({'status': 'error', 'message': 'Each image must have file_path'}), 400

                if not os.path.exists(img_data['file_path']):
                    return jsonify({'status': 'error', 'message': f'File not found: {img_data["file_path"]}'}), 404
            
            return _analyze_multiple_images_stream(images)
        
        else:
            return jsonify({'status': 'error', 'message': 'Either file_path or images array required'}), 400
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def _analyze_single_image_stream(file_path, bbox=None):
    """단일 이미지 분석 스트리밍"""
    def generate_analysis_stream():
        try:
            for result in analyzer.analyze_vehicle_stream(file_path, bbox):
                # Server-Sent Events 형태로 데이터 전송
                yield f"data: {json.dumps(result)}\n\n"
        except Exception as e:
            error_result = {
                'status': 'error',
                'message': str(e),
                'progress': 100
            }
            yield f"data: {json.dumps(error_result)}\n\n"
    
    return Response(
        generate_analysis_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )

def _analyze_multiple_images_stream(images):
    """다중 이미지 분석 스트리밍"""
    def generate_multi_analysis_stream():
        try:
            total_images = len(images)
            
            # 전체 분석 시작 알림
            yield f"data: {json.dumps({
                'status': 'batch_started',
                'total_images': total_images,
                'message': f'{total_images}개 이미지 분석을 시작합니다.'
            })}\n\n"
            
            for idx, img_data in enumerate(images):
                file_path = img_data['file_path']
                bbox = img_data.get('bbox')
                image_id = img_data.get('id', f'image_{idx}')
                
                # 현재 이미지 분석 시작 알림
                yield f"data: {json.dumps({
                    'status': 'analyzing',
                    'current_image': idx + 1,
                    'total_images': total_images,
                    'image_id': image_id,
                    'file_path': file_path,
                    'message': f'이미지 {idx + 1}/{total_images} 분석 중...'
                })}\n\n"
                
                try:
                    # 개별 이미지 분석
                    for result in analyzer.analyze_vehicle_stream(file_path, bbox):
                        # 결과에 이미지 정보 추가
                        result['image_id'] = image_id
                        result['image_index'] = idx
                        result['total_images'] = total_images
                        result['file_path'] = file_path
                        
                        yield f"data: {json.dumps(result)}\n\n"
                        
                        # 개별 이미지 분석 완료시 다음 이미지까지 대기 (rate limiting)
                        if 'success' in result.get('status'):
                            if idx < total_images - 1:  # 마지막 이미지가 아닌 경우
                                yield f"data: {json.dumps({
                                    'status': 'waiting',
                                    'current_image': idx + 1,
                                    'total_images': total_images,
                                    'message': 'API 제한으로 30초 대기 중...',
                                    'wait_seconds': 30
                                })}\n\n"
                                
                                # 30초 대기 (1분에 2장 제한)
                                import time
                                time.sleep(30)
                
                except Exception as e:
                    # 개별 이미지 분석 실패
                    error_result = {
                        'status': 'error',
                        'image_id': image_id,
                        'image_index': idx,
                        'total_images': total_images,
                        'file_path': file_path,
                        'message': f'이미지 {idx + 1} 분석 실패: {str(e)}'
                    }
                    yield f"data: {json.dumps(error_result)}\n\n"
            
            # 전체 분석 완료
            yield f"data: {json.dumps({
                'status': 'all_completed',
                'total_images': total_images,
                'message': f'총 {total_images}개 이미지 분석이 완료되었습니다.'
            })}\n\n"
            
        except Exception as e:
            error_result = {
                'status': 'batch_error',
                'message': f'다중 이미지 분석 실패: {str(e)}',
                'progress': 100
            }
            yield f"data: {json.dumps(error_result)}\n\n"
    
    return Response(
        generate_multi_analysis_stream(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no'
        }
    )


@api.route('/save-dataset', methods=['POST'])
def save_to_dataset():
    """데이터셋 저장 API"""
    try:
        data = request.get_json()
        required_fields = ['file_path', 'manufacturer_code', 'model_code']
        
        if not all(field in data for field in required_fields):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
        file_path = data['file_path']
        bbox = data.get('bbox')
        
        # 분석 결과 구성
        analysis_result = {
            'status': 'success',
            'manufacturer_code': data['manufacturer_code'],
            'manufacturer_confidence': data.get('manufacturer_confidence', 1.0),
            'model_code': data['model_code'],
            'model_confidence': data.get('model_confidence', 1.0)
        }
        
        # 데이터베이스에서 상세 정보 조회
        manufacturer_info = db.get_manufacturer_by_code(data['manufacturer_code'])
        model_info = db.get_model_by_code(data['model_code'])
        
        if manufacturer_info:
            analysis_result['manufacturer_english_name'] = manufacturer_info['english_name']
            analysis_result['manufacturer_korean_name'] = manufacturer_info['korean_name']
        
        if model_info:
            analysis_result['model_english_name'] = model_info['english_name']
            analysis_result['model_korean_name'] = model_info['korean_name']
        
        # 데이터셋에 저장
        success = dataset_generator.add_to_dataset(file_path, analysis_result, bbox)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Data saved to dataset successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to save data to dataset'
            }), 500
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api.route('/add-manufacturer', methods=['POST'])
def add_manufacturer():
    """새 제조사 추가 API"""
    try:
        data = request.get_json()
        required_fields = ['code', 'english_name', 'korean_name']
        
        if not all(field in data for field in required_fields):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
        success = db.add_manufacturer(
            data['code'],
            data['english_name'],
            data['korean_name'],
            data.get('is_domestic', False)
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Manufacturer added successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to add manufacturer'
            }), 500
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@api.route('/add-model', methods=['POST'])
def add_model():
    """새 모델 추가 API"""
    try:
        data = request.get_json()
        required_fields = ['code', 'manufacturer_code', 'english_name', 'korean_name']
        
        if not all(field in data for field in required_fields):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400
        
        success = db.add_model(
            data['code'],
            data['manufacturer_code'],
            data['english_name'],
            data['korean_name']
        )
        
        if success:
            return jsonify({
                'status': 'success',
                'message': 'Model added successfully'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Failed to add model'
            }), 500
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
