"""
차량 데이터베이스 서비스
제조사 및 모델 정보 조회/매칭 담당
"""

import logging
from typing import List, Dict, Optional

from app.config.database import db_config

logger = logging.getLogger(__name__)

class VehicleDatabaseService:
    """차량 데이터베이스 서비스"""
    
    def __init__(self):
        self.db_config = db_config
        
    def get_all_manufacturers(self) -> List[Dict]:
        """모든 제조사 정보 조회"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, code, english_name, korean_name, is_domestic
                        FROM manufacturers 
                        ORDER BY is_domestic DESC, korean_name
                    """)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"제조사 조회 오류: {e}")
            return []
    
    def get_domestic_manufacturers(self) -> List[Dict]:
        """국산 제조사 조회"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, code, english_name, korean_name
                        FROM manufacturers 
                        WHERE is_domestic = 1
                        ORDER BY korean_name
                    """)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"국산 제조사 조회 오류: {e}")
            return []
    
    def get_imported_manufacturers(self) -> List[Dict]:
        """수입 제조사 조회"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT id, code, english_name, korean_name
                        FROM manufacturers 
                        WHERE is_domestic = 0
                        ORDER BY korean_name
                    """)
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"수입 제조사 조회 오류: {e}")
            return []
    
    def get_models_by_manufacturer(self, manufacturer_code: str) -> List[Dict]:
        """특정 제조사의 모든 모델 조회"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT vm.id, vm.code, vm.english_name, vm.korean_name,
                               m.korean_name as manufacturer_korean_name,
                               m.english_name as manufacturer_english_name
                        FROM vehicle_models vm
                        JOIN manufacturers m ON vm.manufacturer_id = m.id
                        WHERE m.code = %s
                        ORDER BY vm.korean_name
                    """, (manufacturer_code,))
                    return cursor.fetchall()
        except Exception as e:
            logger.error(f"모델 조회 오류 (제조사: {manufacturer_code}): {e}")
            return []
    
    def find_manufacturer_by_name(self, name: str) -> Optional[Dict]:
        """이름으로 제조사 검색 (한글/영문 모두)"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 정확한 매치 우선
                    cursor.execute("""
                        SELECT id, code, english_name, korean_name, is_domestic
                        FROM manufacturers 
                        WHERE korean_name = %s OR english_name = %s
                        LIMIT 1
                    """, (name, name))
                    
                    result = cursor.fetchone()
                    if result:
                        return result
                    
                    # 부분 매치
                    cursor.execute("""
                        SELECT id, code, english_name, korean_name, is_domestic
                        FROM manufacturers 
                        WHERE korean_name LIKE %s OR english_name LIKE %s
                        ORDER BY 
                            CASE 
                                WHEN korean_name = %s OR english_name = %s THEN 1
                                WHEN korean_name LIKE %s OR english_name LIKE %s THEN 2
                                ELSE 3
                            END
                        LIMIT 1
                    """, (f'%{name}%', f'%{name}%', name, name, f'{name}%', f'{name}%'))
                    
                    return cursor.fetchone()
        except Exception as e:
            logger.error(f"제조사 검색 오류 ({name}): {e}")
            return None
    
    def find_model_by_name(self, manufacturer_code: str, model_name: str) -> Optional[Dict]:
        """제조사 내에서 모델명으로 검색"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 정확한 매치 우선
                    cursor.execute("""
                        SELECT vm.id, vm.code, vm.english_name, vm.korean_name,
                               m.korean_name as manufacturer_korean_name,
                               m.english_name as manufacturer_english_name
                        FROM vehicle_models vm
                        JOIN manufacturers m ON vm.manufacturer_id = m.id
                        WHERE m.code = %s AND (vm.korean_name = %s OR vm.english_name = %s)
                        LIMIT 1
                    """, (manufacturer_code, model_name, model_name))
                    
                    result = cursor.fetchone()
                    if result:
                        return result
                    
                    # 부분 매치
                    cursor.execute("""
                        SELECT vm.id, vm.code, vm.english_name, vm.korean_name,
                               m.korean_name as manufacturer_korean_name,
                               m.english_name as manufacturer_english_name
                        FROM vehicle_models vm
                        JOIN manufacturers m ON vm.manufacturer_id = m.id
                        WHERE m.code = %s AND (vm.korean_name LIKE %s OR vm.english_name LIKE %s)
                        ORDER BY 
                            CASE 
                                WHEN vm.korean_name LIKE %s OR vm.english_name LIKE %s THEN 1
                                ELSE 2
                            END
                        LIMIT 1
                    """, (manufacturer_code, f'%{model_name}%', f'%{model_name}%', f'{model_name}%', f'{model_name}%'))
                    
                    return cursor.fetchone()
        except Exception as e:
            logger.error(f"모델 검색 오류 ({manufacturer_code}, {model_name}): {e}")
            return None
    
    def get_manufacturer_prompt_examples(self, limit: int = 10) -> str:
        """제조사 식별을 위한 프롬프트 예시 생성"""
        try:
            manufacturers = self.get_all_manufacturers()
            if not manufacturers:
                return ""
            
            # 국산/수입 분리하여 예시 생성
            domestic = [m for m in manufacturers if m['is_domestic']][:limit//2]
            imported = [m for m in manufacturers if not m['is_domestic']][:limit//2]
            
            examples = []
            for m in domestic + imported:
                examples.append(f"- 코드: {m['code']}, 한글명: {m['korean_name']}, 영문명: {m['english_name']}")
            
            return "\n".join(examples)
        except Exception as e:
            logger.error(f"제조사 예시 생성 오류: {e}")
            return ""
    
    def get_model_prompt_examples(self, manufacturer_code: str, limit: int = 15) -> str:
        """특정 제조사의 모델 식별을 위한 프롬프트 예시 생성"""
        try:
            models = self.get_models_by_manufacturer(manufacturer_code)
            if not models:
                return ""
            
            # 최대 limit개까지만 예시로 사용
            selected_models = models[:limit]
            
            examples = []
            for m in selected_models:
                examples.append(f"- 코드: {m['code']}, 한글명: {m['korean_name']}, 영문명: {m['english_name']}")
            
            return "\n".join(examples)
        except Exception as e:
            logger.error(f"모델 예시 생성 오류 ({manufacturer_code}): {e}")
            return ""
    
    def match_manufacturer_response(self, response_text: str) -> Optional[Dict]:
        """AI 응답에서 제조사 매칭"""
        try:
            # 응답에서 코드 추출 시도
            lines = response_text.strip().split('\n')
            for line in lines:
                if 'code:' in line.lower() or '코드:' in line:
                    # 코드 추출
                    parts = line.split(':')
                    if len(parts) >= 2:
                        code = parts[1].strip().replace('"', '').replace("'", '')
                        
                        # 코드로 제조사 조회
                        with self.db_config.get_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    SELECT id, code, english_name, korean_name, is_domestic
                                    FROM manufacturers 
                                    WHERE code = %s
                                """, (code,))
                                result = cursor.fetchone()
                                if result:
                                    return result
            
            return None
        except Exception as e:
            logger.error(f"제조사 매칭 오류: {e}")
            return None
    
    def match_model_response(self, manufacturer_code: str, response_text: str) -> Optional[Dict]:
        """AI 응답에서 모델 매칭"""
        try:
            # 응답에서 코드 추출 시도
            lines = response_text.strip().split('\n')
            for line in lines:
                if 'code:' in line.lower() or '코드:' in line:
                    # 코드 추출
                    parts = line.split(':')
                    if len(parts) >= 2:
                        code = parts[1].strip().replace('"', '').replace("'", '')
                        
                        # 코드로 모델 조회
                        with self.db_config.get_connection() as conn:
                            with conn.cursor() as cursor:
                                cursor.execute("""
                                    SELECT vm.id, vm.code, vm.english_name, vm.korean_name,
                                           m.korean_name as manufacturer_korean_name,
                                           m.english_name as manufacturer_english_name
                                    FROM vehicle_models vm
                                    JOIN manufacturers m ON vm.manufacturer_id = m.id
                                    WHERE m.code = %s AND vm.code = %s
                                """, (manufacturer_code, code))
                                result = cursor.fetchone()
                                if result:
                                    return result
            
            return None
        except Exception as e:
            logger.error(f"모델 매칭 오류: {e}")
            return None
    
    def get_stats(self) -> Dict:
        """데이터베이스 통계 조회"""
        try:
            with self.db_config.get_connection() as conn:
                with conn.cursor() as cursor:
                    # 제조사 통계
                    cursor.execute("SELECT COUNT(*) as total FROM manufacturers")
                    total_manufacturers = cursor.fetchone()['total']
                    
                    cursor.execute("SELECT COUNT(*) as domestic FROM manufacturers WHERE is_domestic = 1")
                    domestic_manufacturers = cursor.fetchone()['domestic']
                    
                    # 모델 통계
                    cursor.execute("SELECT COUNT(*) as total FROM vehicle_models")
                    total_models = cursor.fetchone()['total']
                    
                    cursor.execute("""
                        SELECT m.korean_name, COUNT(vm.id) as model_count
                        FROM manufacturers m
                        LEFT JOIN vehicle_models vm ON m.id = vm.manufacturer_id
                        GROUP BY m.id, m.korean_name
                        ORDER BY model_count DESC
                        LIMIT 10
                    """)
                    top_manufacturers = cursor.fetchall()
                    
                    return {
                        'total_manufacturers': total_manufacturers,
                        'domestic_manufacturers': domestic_manufacturers,
                        'imported_manufacturers': total_manufacturers - domestic_manufacturers,
                        'total_models': total_models,
                        'top_manufacturers': top_manufacturers
                    }
        except Exception as e:
            logger.error(f"통계 조회 오류: {e}")
            return {}

# 전역 서비스 인스턴스
vehicle_db_service = VehicleDatabaseService()
