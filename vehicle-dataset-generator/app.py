from flask import Flask
from flask_cors import CORS
from config import Config
from database import db
from blueprints.main import main
from blueprints.api import api

def create_app():
    """Flask 애플리케이션 팩토리"""
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # CORS 설정
    CORS(app)
    
    # 데이터베이스 연결
    db.connect()
    
    # Blueprint 등록
    app.register_blueprint(main)
    app.register_blueprint(api)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=4000)
