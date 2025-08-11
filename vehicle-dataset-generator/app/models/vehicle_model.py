from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class VehicleModel(Base):
    """차량 모델"""
    __tablename__ = 'vehicle_models'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(100), nullable=False, index=True)
    manufacturer_id = Column(BigInteger, ForeignKey('manufacturers.id', ondelete='CASCADE'), nullable=False, index=True)
    manufacturer_code = Column(String(50), nullable=False, index=True)
    english_name = Column(String(200), nullable=False)
    korean_name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # 관계 설정 (필요시 사용)
    # manufacturer = relationship("Manufacturer", back_populates="vehicle_models")
    
    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            'id': self.id,
            'code': self.code,
            'manufacturer_id': self.manufacturer_id,
            'manufacturer_code': self.manufacturer_code,
            'english_name': self.english_name,
            'korean_name': self.korean_name,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<VehicleModel(id={self.id}, code='{self.code}', korean_name='{self.korean_name}')>"
