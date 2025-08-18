import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask 설정
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    
    # OpenAI 설정
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
    
    # 파일 경로 설정
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER', './temp')
    DATASET_FOLDER = os.getenv('DATASET_FOLDER', './dataset')
    
    # 데이터베이스 설정
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', 3306))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_DATABASE = os.getenv('DB_DATABASE', 'reeve')
    
    # 업로드 설정
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
    
    # YOLO 모델
    YOLO_MODEL_PATH = os.getenv('YOLO_MODEL_PATH', './')
    YOLO_MODEL = os.getenv('YOLO_MODEL', 'yolo11n.pt')
    
    # 데이터셋 설정
    MAX_DATASET_SIZE = 1000  # 파일당 최대 데이터 개수
