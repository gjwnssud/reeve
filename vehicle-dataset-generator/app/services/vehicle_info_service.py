from typing import List, Dict, Optional

from sqlalchemy import or_

from ..config.database import db_config
from ..models.manufacturer import Manufacturer
from ..models.vehicle_model import VehicleModel


class VehicleInfoService:
    """차량 정보 조회 서비스"""
    
    def __init__(self):
        self.db_config = db_config
    
    def get_all_manufacturers(self, is_domestic: Optional[bool] = None) -> List[Dict]:
        """모든 제조사 조회"""
        session = self.db_config.get_session()
        try:
            query = session.query(Manufacturer)
            
            if is_domestic is not None:
                query = query.filter(Manufacturer.is_domestic == is_domestic)
            
            manufacturers = query.order_by(
                Manufacturer.is_domestic.desc(),  # 국산 먼저
                Manufacturer.korean_name
            ).all()
            
            return [manufacturer.to_dict() for manufacturer in manufacturers]
            
        finally:
            session.close()
    
    def get_manufacturer_by_id(self, manufacturer_id: int) -> Optional[Dict]:
        """ID로 제조사 조회"""
        session = self.db_config.get_session()
        try:
            manufacturer = session.query(Manufacturer).filter(
                Manufacturer.id == manufacturer_id
            ).first()
            
            return manufacturer.to_dict() if manufacturer else None
            
        finally:
            session.close()
    
    def get_manufacturer_by_code(self, code: str) -> Optional[Dict]:
        """코드로 제조사 조회"""
        session = self.db_config.get_session()
        try:
            manufacturer = session.query(Manufacturer).filter(
                Manufacturer.code == code
            ).first()
            
            return manufacturer.to_dict() if manufacturer else None
            
        finally:
            session.close()
    
    def search_manufacturers(self, search_term: str) -> List[Dict]:
        """제조사 검색 (한글명, 영문명으로 검색)"""
        session = self.db_config.get_session()
        try:
            search_pattern = f"%{search_term}%"
            
            manufacturers = session.query(Manufacturer).filter(
                or_(
                    Manufacturer.korean_name.like(search_pattern),
                    Manufacturer.english_name.like(search_pattern),
                    Manufacturer.code.like(search_pattern)
                )
            ).order_by(
                Manufacturer.is_domestic.desc(),
                Manufacturer.korean_name
            ).all()
            
            return [manufacturer.to_dict() for manufacturer in manufacturers]
            
        finally:
            session.close()
    
    def get_models_by_manufacturer_id(self, manufacturer_id: int) -> List[Dict]:
        """제조사 ID로 모델 목록 조회"""
        session = self.db_config.get_session()
        try:
            models = session.query(VehicleModel).filter(
                VehicleModel.manufacturer_id == manufacturer_id
            ).order_by(VehicleModel.korean_name).all()
            
            return [model.to_dict() for model in models]
            
        finally:
            session.close()
    
    def get_models_by_manufacturer_code(self, manufacturer_code: str) -> List[Dict]:
        """제조사 코드로 모델 목록 조회"""
        session = self.db_config.get_session()
        try:
            models = session.query(VehicleModel).filter(
                VehicleModel.manufacturer_code == manufacturer_code
            ).order_by(VehicleModel.korean_name).all()
            
            return [model.to_dict() for model in models]
            
        finally:
            session.close()
    
    def get_vehicle_model_by_id(self, model_id: int) -> Optional[Dict]:
        """ID로 차량 모델 조회"""
        session = self.db_config.get_session()
        try:
            model = session.query(VehicleModel).filter(
                VehicleModel.id == model_id
            ).first()
            
            return model.to_dict() if model else None
            
        finally:
            session.close()
    
    def get_vehicle_model_by_code(self, model_code: str) -> Optional[Dict]:
        """코드로 차량 모델 조회"""
        session = self.db_config.get_session()
        try:
            model = session.query(VehicleModel).filter(
                VehicleModel.code == model_code
            ).first()
            
            return model.to_dict() if model else None
            
        finally:
            session.close()
    
    def search_vehicle_models(self, search_term: str, manufacturer_id: Optional[int] = None) -> List[Dict]:
        """차량 모델 검색"""
        session = self.db_config.get_session()
        try:
            search_pattern = f"%{search_term}%"
            
            query = session.query(VehicleModel).filter(
                or_(
                    VehicleModel.korean_name.like(search_pattern),
                    VehicleModel.english_name.like(search_pattern),
                    VehicleModel.code.like(search_pattern)
                )
            )
            
            if manufacturer_id:
                query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)
            
            models = query.order_by(VehicleModel.korean_name).all()
            
            return [model.to_dict() for model in models]
            
        finally:
            session.close()
    
    def get_vehicle_info_with_manufacturer(self, model_id: int) -> Optional[Dict]:
        """모델 정보와 제조사 정보를 함께 조회"""
        session = self.db_config.get_session()
        try:
            result = session.query(VehicleModel, Manufacturer).join(
                Manufacturer, VehicleModel.manufacturer_id == Manufacturer.id
            ).filter(VehicleModel.id == model_id).first()
            
            if result:
                model, manufacturer = result
                return {
                    'model': model.to_dict(),
                    'manufacturer': manufacturer.to_dict()
                }
            
            return None
            
        finally:
            session.close()
    
    def test_database_connection(self) -> bool:
        """데이터베이스 연결 테스트"""
        return self.db_config.test_connection()
