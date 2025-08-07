import os
import time
import json
import tempfile
import base64
from datetime import datetime
from io import BytesIO

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response, send_file
from PIL import Image

from src.core.dataset_manager import DatasetManager
from src.core.vehicle_data_extractor import VehicleDataExtractor

# .env 파일 로드
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size

extractor = VehicleDataExtractor()
dataset_manager = DatasetManager()

# 임시 디렉토리 생성
image_temp_dir = os.getenv('IMAGE_TEMP_DIR', '../../images_daytime/temp')
os.makedirs(image_temp_dir, exist_ok=True)
print(f"✅ 임시 이미지 디렉토리 준비: {image_temp_dir}")


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze_text', methods=['POST'])
def analyze_text():
    try:
        data = request.get_json()
        text = data.get('text', '')

        if not text.strip():
            return jsonify({'error': '분석할 텍스트를 입력해주세요.'}), 400

        result = extractor.analyze_vehicle_from_text(text)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/detect_vehicles_multi', methods=['POST'])
def detect_vehicles_multi():
    """다중 이미지에서 차량 일괄 감지 (바운딩 박스 조절용)"""
    
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
            
            # 파일 내용을 메모리에 읽기
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
                
                # 이미지 임시 저장 디렉토리 설정
                image_temp_dir = os.getenv('IMAGE_TEMP_DIR', '../../images_daytime/temp')
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
                            'temp_path': temp_path,  # 임시 파일 경로
                            'temp_filename': temp_filename  # 웹에서 접근할 파일명
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
            finally:
                # 임시 파일 정리는 하지 않음 (바운딩 박스 조절을 위해 유지)
                pass

        return Response(generate(), mimetype='text/plain')
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/temp_image/<filename>')
def serve_temp_image(filename):
    """임시 이미지 파일 서빙"""
    try:
        image_temp_dir = os.getenv('IMAGE_TEMP_DIR', '../../images_daytime/temp')
        file_path = os.path.join(image_temp_dir, filename)
        
        if not os.path.exists(file_path):
            return jsonify({'error': '파일을 찾을 수 없습니다.'}), 404
            
        return send_file(file_path, mimetype='image/jpeg')
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/cleanup_temp_files', methods=['POST'])
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


@app.route('/detect_vehicles_batch', methods=['POST'])
def detect_vehicles_batch():
    """다중 이미지에서 차량 일괄 감지 (기존 호환성용)"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        def generate():
            results = []
            temp_files = []
            
            try:
                # 시작 알림
                yield f"data: {json.dumps({
                    'type': 'start',
                    'total_count': len(files),
                    'message': f'{len(files)}개 이미지에서 차량을 감지합니다.'
                })}\n\n"
                
                # 모든 이미지 파일을 임시 저장하고 차량 감지
                for i, file in enumerate(files):
                    if file.filename == '':
                        continue
                    
                    try:
                        # 진행 상황 알림
                        yield f"data: {json.dumps({
                            'type': 'processing',
                            'index': i,
                            'filename': file.filename,
                            'progress': round((i / len(files)) * 100, 1)
                        })}\n\n"
                        
                        # 임시 파일로 저장
                        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                            file.save(tmp_file.name)
                            temp_files.append(tmp_file.name)
                            
                            # 이미지 크기 확인
                            image = Image.open(tmp_file.name)
                            width, height = image.size
                            
                            # 차량 감지
                            detected_vehicles = extractor.detect_vehicles_in_image(tmp_file.name)
                            
                            # 이미지를 base64로 인코딩 (썸네일 크기)
                            thumbnail_size = (300, 200)
                            image.thumbnail(thumbnail_size, Image.Resampling.LANCZOS)
                            
                            buffer = BytesIO()
                            image.save(buffer, format='JPEG', quality=85)
                            thumbnail_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
                            
                            result = {
                                'index': i,
                                'filename': file.filename,
                                'image_size': {'width': width, 'height': height},
                                'vehicles': detected_vehicles,
                                'thumbnail': f'data:image/jpeg;base64,{thumbnail_base64}',
                                'temp_path': tmp_file.name  # 임시 파일 경로
                            }
                            
                            results.append(result)
                            
                            # 개별 결과 전송
                            yield f"data: {json.dumps({
                                'type': 'result',
                                'index': i,
                                'result': result,
                                'completed': len(results),
                                'total': len(files),
                                'progress': round((len(results) / len(files)) * 100, 1)
                            })}\n\n"
                            
                    except Exception as e:
                        error_result = {
                            'index': i,
                            'filename': file.filename,
                            'error': f'이미지 처리 오류: {str(e)}',
                            'temp_path': tmp_file.name if 'tmp_file' in locals() else None
                        }
                        results.append(error_result)
                        
                        yield f"data: {json.dumps({
                            'type': 'error',
                            'index': i,
                            'result': error_result,
                            'completed': len(results),
                            'total': len(files),
                            'progress': round((len(results) / len(files)) * 100, 1)
                        })}\n\n"
                
                # 완료 알림
                success_count = len([r for r in results if 'error' not in r])
                yield f"data: {json.dumps({
                    'type': 'complete',
                    'results': results,
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


@app.route('/analyze_multi_with_bboxes', methods=['POST'])
def analyze_multi_with_bboxes():
    """다중 이미지를 각각의 바운딩 박스로 분석"""
    try:
        data = request.get_json()
        image_configs = data.get('image_configs', [])  # [{temp_path, bbox, filename}, ...]
        
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
                    bbox = config.get('bbox')  # [x1, y1, x2, y2] 또는 None
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
                        if i < total_count - 1:  # 마지막이 아니면
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


@app.route('/detect_vehicles', methods=['POST'])
def detect_vehicles():
    """이미지에서 차량을 감지하고 바운딩 박스 반환"""
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


@app.route('/analyze_cropped_region', methods=['POST'])
def analyze_cropped_region():
    """사용자가 조절한 바운딩 박스 영역을 분석"""
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


@app.route('/analyze_multiple_images_stream', methods=['POST'])
def analyze_multiple_images_stream():
    """다중 이미지 분석 (스트리밍)"""
    temp_files_data = []
    
    try:
        if 'images' not in request.files:
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        # Generator 함수 외부에서 전체 파일을 먼저 디스크에 저장
        for i, file in enumerate(files):
            if file.filename == '':
                continue
                
            # 안전한 파일명 생성
            safe_filename = file.filename.replace('/', '_').replace('\\', '_').replace(':', '')
            image_temp_dir = os.getenv('IMAGE_TEMP_DIR', '../../images_daytime/temp')
            os.makedirs(image_temp_dir, exist_ok=True)
            temp_path = f"{image_temp_dir}/temp_{i}_{int(time.time())}_{safe_filename}"
            
            try:
                # 파일 내용 읽기
                file_content = file.read()
                file.seek(0)  # 파일 포인터 리셋
                
                # 임시 파일로 저장
                with open(temp_path, 'wb') as temp_file:
                    temp_file.write(file_content)
                
                temp_files_data.append({
                    'path': temp_path,
                    'filename': file.filename,
                    'index': i
                })
                
            except Exception as e:
                print(f"Error saving file {file.filename}: {e}")
                continue

        def generate():
            results = []
            batch_size = 3  # 배치 크기 축소 (안정성 향상)
            delay_between_batches = 20  # 대기 시간 증가
            
            try:
                # 전체 진행 상황 전송
                yield f"data: {json.dumps({
                    'type': 'start',
                    'total_count': len(temp_files_data),
                    'batch_size': batch_size,
                    'estimated_time': len(temp_files_data) * 4 // batch_size
                })}\n\n"
                
                yield f"data: {json.dumps({
                    'type': 'files_saved',
                    'message': f'{len(temp_files_data)}개 파일 준비 완료, 분석 시작'
                })}\n\n"
                
                # 배치별로 처리
                for batch_start in range(0, len(temp_files_data), batch_size):
                    batch_end = min(batch_start + batch_size, len(temp_files_data))
                    batch_data = temp_files_data[batch_start:batch_end]
                    batch_results = []
                    
                    # 배치 시작 알림
                    batch_filenames = [data['filename'] for data in batch_data]
                    
                    yield f"data: {json.dumps({
                        'type': 'batch_start',
                        'batch_number': batch_start // batch_size + 1,
                        'batch_start': batch_start,
                        'batch_end': batch_end,
                        'processing_files': batch_filenames
                    })}\n\n"
                    
                    # 배치 내 파일들을 순서대로 처리
                    for file_data in batch_data:
                        temp_path = file_data['path']
                        filename = file_data['filename']
                        original_index = file_data['index']
                        
                        try:
                            # 개별 분석 시작 알림
                            yield f"data: {json.dumps({
                                'type': 'analyzing',
                                'index': original_index,
                                'filename': filename
                            })}\n\n"
                            
                            # 파일 존재 확인
                            if not os.path.exists(temp_path):
                                raise Exception(f'임시 파일이 없습니다: {temp_path}')
                            
                            result = analyze_single_image(temp_path, filename, original_index)
                            batch_results.append(result)
                            results.append(result)
                            
                            # 개별 결과 전송
                            if 'error' in result:
                                yield f"data: {json.dumps({
                                    'type': 'error',
                                    'index': original_index,
                                    'result': result,
                                    'completed': len(results),
                                    'total': len(temp_files_data)
                                })}\n\n"
                            else:
                                yield f"data: {json.dumps({
                                    'type': 'result',
                                    'index': original_index,
                                    'result': result,
                                    'completed': len(results),
                                    'total': len(temp_files_data)
                                })}\n\n"
                                
                        except Exception as e:
                            error_result = {
                                'input': filename,
                                'index': original_index,
                                'error': f'분석 오류: {str(e)}'
                            }
                            batch_results.append(error_result)
                            results.append(error_result)
                            
                            yield f"data: {json.dumps({
                                'type': 'error',
                                'index': original_index,
                                'result': error_result,
                                'completed': len(results),
                                'total': len(temp_files_data)
                            })}\n\n"
                    
                    # 배치 완료 알림
                    yield f"data: {json.dumps({
                        'type': 'batch_complete',
                        'batch_number': batch_start // batch_size + 1,
                        'batch_results': len(batch_results),
                        'total_completed': len(results)
                    })}\n\n"
                    
                    # 다음 배치 전 대기 (마지막 배치가 아니면)
                    if batch_end < len(temp_files_data):
                        yield f"data: {json.dumps({
                            'type': 'waiting',
                            'message': f'{delay_between_batches}초 대기 중... (API 요청 제한 방지)',
                            'next_batch': batch_start // batch_size + 2
                        })}\n\n"
                        time.sleep(delay_between_batches)
                
                # 전체 완료
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
                # 모든 임시 파일들 정리
                for file_data in temp_files_data:
                    try:
                        if os.path.exists(file_data['path']):
                            os.remove(file_data['path'])
                    except Exception as e:
                        print(f"Error removing temp file {file_data['path']}: {e}")

        return Response(generate(), mimetype='text/plain')
        
    except Exception as e:
        # 오류 발생 시 임시 파일들 정리
        for file_data in temp_files_data:
            try:
                if os.path.exists(file_data['path']):
                    os.remove(file_data['path'])
            except:
                pass
        return jsonify({'error': str(e)}), 500


def analyze_single_image(temp_path, filename, index):
    """단일 이미지 분석"""
    try:
        result = extractor.analyze_vehicle_from_image(temp_path)
        result['input'] = filename
        result['index'] = index
        return result
    except Exception as e:
        return {
            'input': filename,
            'index': index,
            'error': f'분석 오류: {str(e)}'
        }


@app.route('/analyze_multiple_images', methods=['POST'])
def analyze_multiple_images():
    """기존 다중 이미지 분석 (호환성을 위해 유지)"""
    return jsonify({
        'error': '이 API는 더 이상 사용되지 않습니다. /analyze_multiple_images_stream을 사용하세요.',
        'redirect': '/analyze_multiple_images_stream'
    }), 410


@app.route('/save_to_dataset', methods=['POST'])
def save_to_dataset():
    """결과를 데이터셋에 저장"""
    try:
        data = request.get_json()
        results = data.get('results', [])

        if not results:
            return jsonify({'error': '저장할 결과가 없습니다.'}), 400

        # 데이터셋에 저장
        save_info = dataset_manager.save_results(results, "image")

        if save_info:
            return jsonify({
                'message': '데이터셋 저장 완료',
                'save_info': save_info
            })
        else:
            return jsonify({'error': '데이터셋 저장 실패'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dataset_stats')
def get_dataset_stats():
    """데이터셋 통계 조회"""
    try:
        stats = dataset_manager.get_dataset_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_image', methods=['POST'])
def analyze_image():
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4000)
