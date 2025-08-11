"""
Vehicle Info Routes
차량 정보 관련 라우트 정의
"""

import json
import logging
import time
import os
import sys
import tempfile
from pathlib import Path
from flask import render_template, request, jsonify, current_app, Response

# 프로젝트 루트의 src 모듈을 import하기 위한 경로 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from . import vehicle_info_bp
from src.core.vehicle_data_extractor import vehicle_extractor

# 기존 서비스들은 나중에 새로운 구조로 이전 예정
try:
    from web.services.vehicle_db_service import vehicle_db_service
except ImportError:
    # 임시로 None으로 설정, 추후 새로운 서비스로 교체
    vehicle_db_service = None

logger = logging.getLogger(__name__)

@vehicle_info_bp.route('/')
def vehicle_info_page():
    """차량 정보 페이지"""
    return render_template('vehicle_info.html')

@vehicle_info_bp.route('/manufacturers', methods=['GET'])
def get_manufacturers():
    """모든 제조사 조회"""
    try:
        if vehicle_db_service is None:
            return jsonify({'error': '데이터베이스 서비스를 사용할 수 없습니다.'}), 503
            
        manufacturers = vehicle_db_service.get_all_manufacturers()
        
        # 국산/수입 분리
        domestic = [m for m in manufacturers if m['is_domestic']]
        imported = [m for m in manufacturers if not m['is_domestic']]
        
        return jsonify({
            'success': True,
            'data': {
                'domestic': domestic,
                'imported': imported,
                'total': len(manufacturers)
            }
        })
        
    except Exception as e:
        logger.error(f"제조사 조회 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/manufacturers/<manufacturer_code>/models', methods=['GET'])
def get_models_by_manufacturer(manufacturer_code):
    """특정 제조사의 모델 조회"""
    try:
        if vehicle_db_service is None:
            return jsonify({'error': '데이터베이스 서비스를 사용할 수 없습니다.'}), 503
            
        models = vehicle_db_service.get_models_by_manufacturer(manufacturer_code)
        
        if not models:
            return jsonify({
                'success': False,
                'error': f'제조사 코드 "{manufacturer_code}"의 모델을 찾을 수 없습니다.'
            }), 404
        
        return jsonify({
            'success': True,
            'data': {
                'manufacturer_code': manufacturer_code,
                'models': models,
                'total': len(models)
            }
        })
        
    except Exception as e:
        logger.error(f"모델 조회 오류 ({manufacturer_code}): {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/search/manufacturer', methods=['POST'])
def search_manufacturer():
    """제조사 이름으로 검색"""
    try:
        if vehicle_db_service is None:
            return jsonify({'error': '데이터베이스 서비스를 사용할 수 없습니다.'}), 503
            
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'error': '검색할 제조사명을 입력해주세요.'}), 400
        
        manufacturer = vehicle_db_service.find_manufacturer_by_name(name)
        
        if manufacturer:
            return jsonify({
                'success': True,
                'data': manufacturer
            })
        else:
            return jsonify({
                'success': False,
                'error': f'제조사 "{name}"을 찾을 수 없습니다.'
            }), 404
            
    except Exception as e:
        logger.error(f"제조사 검색 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/search/model', methods=['POST'])
def search_model():
    """제조사 내에서 모델 검색"""
    try:
        if vehicle_db_service is None:
            return jsonify({'error': '데이터베이스 서비스를 사용할 수 없습니다.'}), 503
            
        data = request.get_json()
        manufacturer_code = data.get('manufacturer_code', '').strip()
        model_name = data.get('model_name', '').strip()
        
        if not manufacturer_code or not model_name:
            return jsonify({'error': '제조사 코드와 모델명을 모두 입력해주세요.'}), 400
        
        model = vehicle_db_service.find_model_by_name(manufacturer_code, model_name)
        
        if model:
            return jsonify({
                'success': True,
                'data': model
            })
        else:
            return jsonify({
                'success': False,
                'error': f'제조사 "{manufacturer_code}"에서 모델 "{model_name}"을 찾을 수 없습니다.'
            }), 404
            
    except Exception as e:
        logger.error(f"모델 검색 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/analyze/text/v2', methods=['POST'])
def analyze_text_v2():
    """향상된 텍스트 분석 (DB 기반 2단계)"""
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        
        if not text:
            return jsonify({'error': '분석할 텍스트를 입력해주세요.'}), 400
        
        result = vehicle_extractor.analyze_vehicle_from_text_v2(text)
        
        return jsonify({
            'success': 'error' not in result,
            'result': result
        })
        
    except Exception as e:
        logger.error(f"향상된 텍스트 분석 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/analyze/image/v2', methods=['POST'])
def analyze_image_v2():
    """향상된 이미지 분석 (DB 기반 2단계)"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        # 임시 파일로 저장
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
            file.save(tmp_file.name)
            temp_path = tmp_file.name

        try:
            result = vehicle_extractor.analyze_vehicle_from_image_v2(temp_path)
            
            return jsonify({
                'success': 'error' not in result,
                'result': result
            })
            
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        logger.error(f"향상된 이미지 분석 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/analyze/batch/v2', methods=['POST'])
def analyze_batch_v2():
    """향상된 배치 분석 (스트리밍)"""
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
                    'message': f'{len(files)}개 이미지를 향상된 방식으로 분석합니다.'
                })}\n\n"
                
                # 파일들을 임시 저장
                for i, file in enumerate(files):
                    if file.filename == '':
                        continue
                    
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        file.save(tmp_file.name)
                        temp_files.append({
                            'path': tmp_file.name,
                            'filename': file.filename,
                            'index': i
                        })
                
                # 배치 처리
                batch_size = 2  # API 안정성을 위해 작은 배치
                delay_between_batches = 25  # 충분한 대기 시간
                
                for batch_start in range(0, len(temp_files), batch_size):
                    batch_end = min(batch_start + batch_size, len(temp_files))
                    batch_files = temp_files[batch_start:batch_end]
                    
                    # 배치 시작 알림
                    yield f"data: {json.dumps({
                        'type': 'batch_start',
                        'batch_number': batch_start // batch_size + 1,
                        'processing_files': [f['filename'] for f in batch_files]
                    })}\n\n"
                    
                    # 배치 내 파일들 처리
                    for file_info in batch_files:
                        try:
                            # 분석 시작 알림
                            yield f"data: {json.dumps({
                                'type': 'analyzing',
                                'index': file_info['index'],
                                'filename': file_info['filename']
                            })}\n\n"
                            
                            # 향상된 분석 수행
                            result = vehicle_extractor.analyze_vehicle_from_image_v2(file_info['path'])
                            result['index'] = file_info['index']
                            results.append(result)
                            
                            # 결과 전송
                            yield f"data: {json.dumps({
                                'type': 'result',
                                'index': file_info['index'],
                                'result': result,
                                'completed': len(results),
                                'total': len(temp_files)
                            })}\n\n"
                            
                        except Exception as e:
                            error_result = {
                                'input': file_info['filename'],
                                'index': file_info['index'],
                                'error': f'분석 오류: {str(e)}'
                            }
                            results.append(error_result)
                            
                            yield f"data: {json.dumps({
                                'type': 'error',
                                'index': file_info['index'],
                                'result': error_result,
                                'completed': len(results),
                                'total': len(temp_files)
                            })}\n\n"
                    
                    # 배치 완료 대기
                    if batch_end < len(temp_files):
                        yield f"data: {json.dumps({
                            'type': 'waiting',
                            'message': f'{delay_between_batches}초 대기 중... (API 요청 제한 방지)'
                        })}\n\n"
                        time.sleep(delay_between_batches)
                
                # 완료
                success_count = len([r for r in results if 'error' not in r])
                yield f"data: {json.dumps({
                    'type': 'complete',
                    'results': results,
                    'total_count': len(results),
                    'success_count': success_count,
                    'message': f'향상된 분석 완료! 성공: {success_count}개, 전체: {len(results)}개'
                })}\n\n"
                
            except Exception as e:
                yield f"data: {json.dumps({
                    'type': 'fatal_error',
                    'error': str(e)
                })}\n\n"
                
            finally:
                # 임시 파일 정리
                for file_info in temp_files:
                    try:
                        if os.path.exists(file_info['path']):
                            os.unlink(file_info['path'])
                    except Exception as e:
                        logger.error(f"임시 파일 삭제 오류: {e}")

        return Response(generate(), mimetype='text/plain')
        
    except Exception as e:
        logger.error(f"향상된 배치 분석 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/stats', methods=['GET'])
def get_vehicle_stats():
    """차량 데이터베이스 통계"""
    try:
        if vehicle_db_service is None:
            return jsonify({'error': '데이터베이스 서비스를 사용할 수 없습니다.'}), 503
            
        stats = vehicle_db_service.get_stats()
        
        return jsonify({
            'success': True,
            'data': stats
        })
        
    except Exception as e:
        logger.error(f"통계 조회 오류: {e}")
        return jsonify({'error': str(e)}), 500

@vehicle_info_bp.route('/test/connection', methods=['GET'])
def test_db_connection():
    """데이터베이스 연결 테스트"""
    try:
        if vehicle_db_service is None:
            return jsonify({
                'success': False,
                'error': '데이터베이스 서비스를 사용할 수 없습니다.'
            }), 503
            
        from web.config.database import db_config
        
        is_connected = db_config.test_connection()
        
        if is_connected:
            # 간단한 통계도 함께 조회
            stats = vehicle_db_service.get_stats()
            
            return jsonify({
                'success': True,
                'message': '데이터베이스 연결 성공',
                'stats': stats
            })
        else:
            return jsonify({
                'success': False,
                'error': '데이터베이스 연결 실패'
            }), 500
            
    except Exception as e:
        logger.error(f"DB 연결 테스트 오류: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
