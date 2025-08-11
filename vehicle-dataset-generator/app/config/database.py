import os

import pymysql
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

load_dotenv()

class DatabaseConfig:
    """MySQL 데이터베이스 연결 설정"""
    
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = int(os.getenv('DB_PORT', 3306))
        self.user = os.getenv('DB_USER', 'reeve')
        self.password = os.getenv('DB_PASSWORD', '1q2w3e!@')
        self.database = os.getenv('DB_DATABASE', 'reeve')
        
        # SQLAlchemy 엔진 생성
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
    
    def _create_engine(self):
        """SQLAlchemy 엔진 생성"""
        database_url = f"mysql+pymysql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        return create_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600
        )
    
    def get_connection(self):
        """Raw MySQL 연결 반환"""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )
    
    def get_session(self):
        """SQLAlchemy 세션 반환"""
        return self.SessionLocal()
    
    def test_connection(self):
        """데이터베이스 연결 테스트"""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text("SELECT 1 as test"))
                return result.fetchone() is not None
        except Exception as e:
            print(f"데이터베이스 연결 실패: {e}")
            return False

# 전역 데이터베이스 설정 인스턴스
db_config = DatabaseConfig()

def get_db_session():
    """데이터베이스 세션 의존성"""
    session = db_config.get_session()
    try:
        yield session
    finally:
        session.close()
