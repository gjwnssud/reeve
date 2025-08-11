"""
Main Routes
메인 페이지의 라우트 정의
"""

from flask import render_template, jsonify
from . import main_bp

@main_bp.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html')

@main_bp.route('/health')
def health_check():
    """헬스 체크 엔드포인트"""
    return jsonify({
        'status': 'healthy',
        'service': 'vehicle-dataset-generator',
        'version': '1.0.0'
    })
