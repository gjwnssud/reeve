"""
Blueprints Registration
모든 블루프린트를 등록하는 모듈
"""

def register_blueprints(app):
    """
    모든 블루프린트를 Flask 앱에 등록
    
    Args:
        app: Flask 애플리케이션 인스턴스
    """
    
    # 메인 페이지 블루프린트
    from .main import main_bp
    app.register_blueprint(main_bp)
    
    # 분석 관련 블루프린트
    from .analysis import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/analysis')
    
    # 데이터셋 관련 블루프린트
    from .dataset import dataset_bp
    app.register_blueprint(dataset_bp, url_prefix='/dataset')
    
    # 차량 정보 관련 블루프린트
    from .vehicle_info import vehicle_info_bp
    app.register_blueprint(vehicle_info_bp, url_prefix='/vehicle-info')
