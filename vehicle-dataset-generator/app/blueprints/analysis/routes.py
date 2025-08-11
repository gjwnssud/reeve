"""
Analysis Routes
데이터 분석 관련 라우트 정의
"""

import base64
import json
import os
import tempfile
import time
from io import BytesIO

from PIL import Image
from flask import render_template, request, jsonify, current_app, Response

# 프로젝트 루트의 src 모듈을 import하기 위한 경로 추가
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from . import analysis_bp
from src.core.vehicle_data_extractor import VehicleDataExtractor

# 전역 extractor 인스턴스
extractor = VehicleDataExtractor()

@analysis_bp.route('/')
def analysis_page():
    """분석 페이지"""
    return render_template('analysis.html')

@analysis_bp.route('/text', methods=['POST'])
def analyze_text():
    """텍스트 분석"""
    try:
        data = request.get_json()
        text = data.get('text', '')

        if not text.strip():
            return jsonify({'error': '분석할 텍스트를 입력해주세요.'}), 400

        result = extractor.analyze_vehicle_from_text(text)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/image/single', methods=['POST'])
def analyze_single_image():
    """단일 이미지 분석"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        # 임시 파일로 저장
        temp_path = f"temp_{file.filename}"
        file.save(temp_path)

        try:
            result = extractor.analyze_vehicle_from_image(temp_path)
            return jsonify(result)
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/vehicle/detect', methods=['POST'])
def detect_vehicles():
    """이미지에서 차량 감지"""
    try:
        data = request.get_json()
        image_data = data.get('image_data', '')
        
        if not image_data:
            return jsonify({'error': '이미지 데이터가 없습니다.'}), 400
        
        # Base64 이미지 디코딩
        try:
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(BytesIO(image_bytes))
            
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                image.save(tmp_file.name, 'JPEG')
                temp_path = tmp_file.name
            
            try:
                # 차량 감지
                detected_vehicles = extractor.detect_vehicles_in_image(temp_path)
                
                # 이미지 크기 정보 추가
                width, height = image.size
                
                return jsonify({
                    'success': True,
                    'image_size': {'width': width, 'height': height},
                    'vehicles': detected_vehicles,
                    'message': f'{len(detected_vehicles)}대의 차량이 감지되었습니다.'
                })
                
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            return jsonify({'error': f'이미지 처리 오류: {str(e)}'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/vehicle/detect/multi', methods=['POST'])
def detect_vehicles_multi():
    """다중 이미지에서 차량 일괄 감지"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        # 먼저 모든 파일을 메모리에 로드
        file_data_list = []
        for i, file in enumerate(files):
            if file.filename == '':
                continue
            
            file_content = file.read()
            file_data_list.append({
                'index': i,
                'filename': file.filename,
                'content': file_content
            })

        def generate():
            results = []
            temp_files = []
            
            try:
                # 시작 알림
                yield f"data: {json.dumps({
                    'type': 'start',
                    'total_count': len(file_data_list),
                    'message': f'{len(file_data_list)}개 이미지에서 차량을 감지합니다.'
                })}\n\n"
                
                image_temp_dir = current_app.config.get('IMAGE_TEMP_DIR', '../../images_daytime/temp')
                os.makedirs(image_temp_dir, exist_ok=True)
                
                # 모든 이미지 파일을 임시 저장하고 차량 감지
                for file_data in file_data_list:
                    i = file_data['index']
                    filename = file_data['filename']
                    content = file_data['content']
                    
                    try:
                        # 진행 상황 알림
                        yield f"data: {json.dumps({
                            'type': 'detecting',
                            'index': i,
                            'filename': filename,
                            'total_count': len(file_data_list)
                        })}\n\n"
                        
                        # 안전한 파일명 생성
                        safe_filename = filename.replace('/', '_').replace('\\', '_').replace(':', '')
                        temp_filename = f"temp_{i}_{int(time.time())}_{safe_filename}"
                        temp_path = os.path.join(image_temp_dir, temp_filename)
                        
                        # 파일을 디스크에 저장
                        with open(temp_path, 'wb') as temp_file:
                            temp_file.write(content)
                        
                        temp_files.append(temp_path)
                        
                        # 이미지 크기 확인
                        image = Image.open(temp_path)
                        width, height = image.size
                        
                        # 차량 감지
                        detected_vehicles = extractor.detect_vehicles_in_image(temp_path)
                        
                        result = {
                            'index': i,
                            'filename': filename,
                            'image_size': {'width': width, 'height': height},
                            'vehicles': detected_vehicles,
                            'temp_path': temp_path,
                            'temp_filename': temp_filename
                        }
                        
                        results.append(result)
                        
                        # 개별 결과 전송
                        yield f"data: {json.dumps({
                            'type': 'result',
                            'index': i,
                            'result': result,
                            'completed': len(results),
                            'total': len(file_data_list)
                        })}\n\n"
                        
                    except Exception as e:
                        error_result = {
                            'index': i,
                            'filename': filename,
                            'error': f'이미지 처리 오류: {str(e)}'
                        }
                        results.append(error_result)
                        
                        yield f"data: {json.dumps({
                            'type': 'error',
                            'index': i,
                            'result': error_result,
                            'completed': len(results),
                            'total': len(file_data_list)
                        })}\n\n"
                
                # 완료 알림
                success_count = len([r for r in results if 'error' not in r])
                yield f"data: {json.dumps({
                    'type': 'complete',
                    'total_count': len(results),
                    'success_count': success_count,
                    'message': f'차량 감지 완료! 성공: {success_count}개, 전체: {len(results)}개'
                })}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({
                    'type': 'fatal_error',
                    'error': str(e)
                })}\n\n"

        return Response(generate(), mimetype='text/plain')
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/region/analyze', methods=['POST'])
def analyze_cropped_region():
    """사용자가 조절한 바운딩 박스 영역 분석"""
    try:
        data = request.get_json()
        image_data = data.get('image_data', '')
        bbox = data.get('bbox', [])
        
        if not image_data:
            return jsonify({'error': '이미지 데이터가 필요합니다.'}), 400

        # Base64 이미지 디코딩
        try:
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            
            image_bytes = base64.b64decode(image_data)
            image = Image.open(BytesIO(image_bytes))
            
            # 임시 파일로 저장
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                image.save(tmp_file.name, 'JPEG')
                temp_path = tmp_file.name
            
            try:
                # 바운딩 박스 영역으로 분석
                result = extractor.analyze_vehicle_with_bbox(temp_path, bbox)
                
                return jsonify({
                    'success': True,
                    'result': result
                })
                
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(temp_path)
                except:
                    pass
                    
        except Exception as e:
            return jsonify({'error': f'이미지 처리 오류: {str(e)}'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/multi/analyze', methods=['POST'])
def analyze_multi_with_bboxes():
    """다중 이미지를 각각의 바운딩 박스로 분석"""
    try:
        data = request.get_json()
        image_configs = data.get('image_configs', [])
        
        if not image_configs:
            return jsonify({'error': '분석할 이미지 설정이 없습니다.'}), 400

        def generate():
            results = []
            total_count = len(image_configs)
            
            try:
                # 시작 알림
                yield f"data: {json.dumps({
                    'type': 'start',
                    'total_count': total_count,
                    'message': f'{total_count}개 이미지의 선택된 영역을 분석합니다.'
                })}\n\n"
                
                # 각 이미지 순차 처리
                for i, config in enumerate(image_configs):
                    temp_path = config.get('temp_path')
                    bbox = config.get('bbox')
                    filename = config.get('filename', f'image_{i+1}')
                    
                    try:
                        # 진행 상황 알림
                        yield f"data: {json.dumps({
                            'type': 'analyzing',
                            'index': i,
                            'filename': filename,
                            'progress': round((i / total_count) * 100, 1)
                        })}\n\n"
                        
                        # 파일 존재 확인
                        if not temp_path or not os.path.exists(temp_path):
                            raise Exception('임시 파일이 존재하지 않습니다')
                        
                        # 바운딩 박스 영역으로 분석
                        result = extractor.analyze_vehicle_with_bbox(temp_path, bbox)
                        result['input'] = filename
                        result['index'] = i
                        
                        results.append(result)
                        
                        # 개별 결과 전송
                        yield f"data: {json.dumps({
                            'type': 'result',
                            'index': i,
                            'result': result,
                            'completed': len(results),
                            'total': total_count,
                            'progress': round((len(results) / total_count) * 100, 1)
                        })}\n\n"
                        
                        # API 요청 제한 방지를 위한 대기
                        if i < total_count - 1:
                            time.sleep(2)
                        
                    except Exception as e:
                        error_result = {
                            'input': filename,
                            'index': i,
                            'error': f'분석 오류: {str(e)}'
                        }
                        results.append(error_result)
                        
                        yield f"data: {json.dumps({
                            'type': 'error',
                            'index': i,
                            'result': error_result,
                            'completed': len(results),
                            'total': total_count,
                            'progress': round((len(results) / total_count) * 100, 1)
                        })}\n\n"
                
                # 완료 알림
                success_count = len([r for r in results if 'error' not in r])
                yield f"data: {json.dumps({
                    'type': 'complete',
                    'results': results,
                    'total_count': len(results),
                    'success_count': success_count,
                    'message': f'분석 완료! 성공: {success_count}개, 전체: {len(results)}개'
                })}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({
                    'type': 'fatal_error',
                    'error': str(e)
                })}\n\n"
            finally:
                # 임시 파일들 정리
                for config in image_configs:
                    try:
                        temp_path = config.get('temp_path')
                        if temp_path and os.path.exists(temp_path):
                            os.unlink(temp_path)
                    except Exception as e:
                        print(f"Error removing temp file: {e}")

        return Response(generate(), mimetype='text/plain')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/temp/cleanup', methods=['POST'])
def cleanup_temp_files():
    """임시 파일들 정리"""
    try:
        data = request.get_json()
        temp_paths = data.get('temp_paths', [])
        
        cleaned_count = 0
        for temp_path in temp_paths:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                    cleaned_count += 1
            except Exception as e:
                print(f"Error removing {temp_path}: {e}")
        
        return jsonify({
            'success': True,
            'cleaned_count': cleaned_count,
            'message': f'{cleaned_count}개 임시 파일을 정리했습니다.'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
