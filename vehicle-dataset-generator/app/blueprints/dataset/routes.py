"""
Dataset Routes
데이터셋 생성 및 관리 관련 라우트 정의
"""

import os
import sys
from pathlib import Path
from flask import render_template, request, jsonify, current_app, send_file

# 프로젝트 루트의 src 모듈을 import하기 위한 경로 추가
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from . import dataset_bp
from src.core.dataset_manager import DatasetManager

# 전역 dataset_manager 인스턴스
dataset_manager = DatasetManager()

@dataset_bp.route('/')
def dataset_page():
    """데이터셋 생성 페이지"""
    return render_template('dataset.html')

@dataset_bp.route('/save', methods=['POST'])
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
                'success': True,
                'message': '데이터셋 저장 완료',
                'save_info': save_info
            })
        else:
            return jsonify({'error': '데이터셋 저장 실패'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dataset_bp.route('/stats', methods=['GET'])
def get_dataset_stats():
    """데이터셋 통계 조회"""
    try:
        stats = dataset_manager.get_dataset_stats()
        return jsonify({
            'success': True,
            'stats': stats
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@dataset_bp.route('/export', methods=['POST'])
def export_dataset():
    """데이터셋 내보내기"""
    try:
        data = request.get_json()
        export_format = data.get('format', 'json')  # json, csv, xlsx
        filter_options = data.get('filters', {})
        
        # TODO: 데이터셋 내보내기 기능 구현
        export_info = dataset_manager.export_dataset(export_format, filter_options)
        
        return jsonify({
            'success': True,
            'message': f'{export_format} 형식으로 내보내기 완료',
            'export_info': export_info
        })
        
    except Exception as e:
        current_app.logger.error(f"데이터셋 내보내기 중 오류 발생: {str(e)}")
        return jsonify({'error': str(e)}), 500

@dataset_bp.route('/download/<path:filename>')
def download_dataset(filename):
    """생성된 데이터셋 다운로드"""
    try:
        # 보안을 위해 파일 경로 검증
        safe_path = current_app.config['UPLOAD_FOLDER'] / filename
        
        if not safe_path.exists() or not safe_path.is_file():
            return jsonify({
                'success': False,
                'error': '파일을 찾을 수 없습니다.'
            }), 404
        
        return send_file(
            safe_path,
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"파일 다운로드 중 오류 발생: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'파일 다운로드 중 오류가 발생했습니다: {str(e)}'
        }), 500

@dataset_bp.route('/backup', methods=['POST'])
def backup_dataset():
    """데이터셋 백업"""
    try:
        backup_info = dataset_manager.backup_dataset()
        
        return jsonify({
            'success': True,
            'message': '데이터셋 백업이 완료되었습니다.',
            'backup_info': backup_info
        })
        
    except Exception as e:
        current_app.logger.error(f"데이터셋 백업 중 오류 발생: {str(e)}")
        return jsonify({'error': str(e)}), 500

@dataset_bp.route('/list', methods=['GET'])
def list_datasets():
    """데이터셋 목록 조회"""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        datasets = dataset_manager.list_datasets(page=page, per_page=per_page)
        
        return jsonify({
            'success': True,
            'datasets': datasets
        })
        
    except Exception as e:
        current_app.logger.error(f"데이터셋 목록 조회 중 오류 발생: {str(e)}")
        return jsonify({'error': str(e)}), 500

@dataset_bp.route('/delete/<int:dataset_id>', methods=['DELETE'])
def delete_dataset(dataset_id):
    """데이터셋 삭제"""
    try:
        success = dataset_manager.delete_dataset(dataset_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': '데이터셋이 삭제되었습니다.'
            })
        else:
            return jsonify({
                'success': False,
                'error': '데이터셋 삭제에 실패했습니다.'
            }), 400
        
    except Exception as e:
        current_app.logger.error(f"데이터셋 삭제 중 오류 발생: {str(e)}")
        return jsonify({'error': str(e)}), 500
