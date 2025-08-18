import pymysql
from config import Config

class Database:
    def __init__(self):
        self.config = Config()
        self.connection = None
    
    def connect(self):
        """데이터베이스 연결"""
        try:
            self.connection = pymysql.connect(
                host=self.config.DB_HOST,
                port=self.config.DB_PORT,
                user=self.config.DB_USER,
                password=self.config.DB_PASSWORD,
                database=self.config.DB_DATABASE,
                charset='utf8mb4',
                cursorclass=pymysql.cursors.DictCursor
            )
            return True
        except Exception as e:
            print(f"Database connection error: {e}")
            return False
    
    def disconnect(self):
        """데이터베이스 연결 해제"""
        if self.connection:
            self.connection.close()
    
    def get_all_manufacturers(self):
        """모든 제조사 정보 조회"""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT code, english_name, korean_name, is_domestic 
                    FROM manufacturers 
                    ORDER BY is_domestic DESC, english_name
                """)
                return cursor.fetchall()
        except Exception as e:
            print(f"Error getting manufacturers: {e}")
            return []
    
    def get_manufacturer_by_code(self, code):
        """코드로 제조사 정보 조회"""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM manufacturers WHERE code = %s
                """, (code,))
                return cursor.fetchone()
        except Exception as e:
            print(f"Error getting manufacturer by code: {e}")
            return None
    
    def get_models_by_manufacturer(self, manufacturer_code):
        """제조사별 모델 정보 조회"""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT code, english_name, korean_name 
                    FROM vehicle_models 
                    WHERE manufacturer_code = %s 
                    ORDER BY english_name
                """, (manufacturer_code,))
                return cursor.fetchall()
        except Exception as e:
            print(f"Error getting models: {e}")
            return []
    
    def get_model_by_code(self, model_code):
        """코드로 모델 정보 조회"""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    SELECT vm.*, m.english_name as manufacturer_english_name, 
                           m.korean_name as manufacturer_korean_name
                    FROM vehicle_models vm
                    JOIN manufacturers m ON vm.manufacturer_code = m.code
                    WHERE vm.code = %s
                """, (model_code,))
                return cursor.fetchone()
        except Exception as e:
            print(f"Error getting model by code: {e}")
            return None
    
    def add_manufacturer(self, code, english_name, korean_name, is_domestic=False):
        """새 제조사 추가"""
        try:
            if not self.connection:
                self.connect()
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO manufacturers (code, english_name, korean_name, is_domestic)
                    VALUES (%s, %s, %s, %s)
                """, (code, english_name, korean_name, is_domestic))
                self.connection.commit()
                return True
        except Exception as e:
            print(f"Error adding manufacturer: {e}")
            return False
    
    def add_model(self, code, manufacturer_code, english_name, korean_name):
        """새 모델 추가"""
        try:
            if not self.connection:
                self.connect()
            
            # 제조사 ID 조회
            manufacturer = self.get_manufacturer_by_code(manufacturer_code)
            if not manufacturer:
                return False
            
            with self.connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO vehicle_models (code, manufacturer_id, manufacturer_code, english_name, korean_name)
                    VALUES (%s, %s, %s, %s, %s)
                """, (code, manufacturer['id'], manufacturer_code, english_name, korean_name))
                self.connection.commit()
                return True
        except Exception as e:
            print(f"Error adding model: {e}")
            return False

# 전역 데이터베이스 인스턴스
db = Database()
