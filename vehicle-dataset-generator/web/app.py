import os
import time
import json
from datetime import datetime

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, Response

from src.core.dataset_manager import DatasetManager
from src.core.vehicle_data_extractor import VehicleDataExtractor

# .env 파일 로드
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200MB max file size

extractor = VehicleDataExtractor()
dataset_manager = DatasetManager()


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
            delay_between_batches = 3  # 대기 시간 증가
            
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
