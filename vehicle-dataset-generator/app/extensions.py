"""
Flask Extensions
Flask 확장들의 초기화를 관리
"""

def init_extensions(app):
    """
    Flask 확장들을 초기화
    
    Args:
        app: Flask 애플리케이션 인스턴스
    """
    
    # 현재는 특별한 확장이 없지만, 향후 다음과 같은 확장들을 추가할 수 있음:
    # - Flask-SQLAlchemy (데이터베이스 ORM)
    # - Flask-Login (사용자 인증)
    # - Flask-WTF (폼 처리)
    # - Flask-Migrate (데이터베이스 마이그레이션)
    # - Flask-CORS (CORS 처리)
    
    # 예시: 향후 확장 추가시
    # db.init_app(app)
    # login_manager.init_app(app)
    # migrate.init_app(app, db)
    
    pass
