"""
Flask Application Factory
애플리케이션 팩토리 패턴을 사용한 Flask 앱 생성
"""

from flask import Flask
from config import get_config

def create_app(config_name=None):
    """
    Flask 애플리케이션 팩토리
    
    Args:
        config_name: 설정 이름 (development, production, testing)
    
    Returns:
        Flask: 설정된 Flask 애플리케이션 인스턴스
    """
    app = Flask(__name__)
    
    # 설정 로드
    config = get_config()
    app.config.from_object(config)
    
    # 정적 파일 및 템플릿 경로 설정
    app.static_folder = str(config.STATIC_FOLDER)
    app.template_folder = str(config.TEMPLATE_FOLDER)
    
    # 업로드 폴더 생성
    config.UPLOAD_FOLDER.mkdir(exist_ok=True)
    
    # 확장 초기화
    from .extensions import init_extensions
    init_extensions(app)
    
    # 블루프린트 등록
    from .blueprints import register_blueprints
    register_blueprints(app)
    
    # 에러 핸들러 등록
    register_error_handlers(app)
    
    # 컨텍스트 프로세서 등록
    register_context_processors(app)
    
    return app

def register_error_handlers(app):
    """에러 핸들러 등록"""
    
    @app.errorhandler(404)
    def not_found(error):
        return "페이지를 찾을 수 없습니다.", 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return "서버 내부 오류가 발생했습니다.", 500

def register_context_processors(app):
    """템플릿 컨텍스트 프로세서 등록"""
    
    @app.context_processor
    def inject_config():
        """설정 정보를 템플릿에 주입"""
        return {
            'app_name': '차량 데이터셋 생성기',
            'version': '1.0.0'
        }
