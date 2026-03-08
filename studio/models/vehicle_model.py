"""
차량 모델 모델
"""
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from studio.models.database import Base


class VehicleModel(Base):
    """차량 모델 테이블 (사용자 제공 DDL 기반)"""

    __tablename__ = "vehicle_models"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(100), nullable=False, index=True)
    manufacturer_id = Column(BigInteger, ForeignKey("manufacturers.id", ondelete="CASCADE"), nullable=False, index=True)
    manufacturer_code = Column(String(50), nullable=False, index=True)
    english_name = Column(String(200), nullable=False)
    korean_name = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 관계 설정
    manufacturer = relationship("Manufacturer", back_populates="vehicle_models")
    analyzed_vehicles = relationship("AnalyzedVehicle", back_populates="matched_model")
    training_datasets = relationship("TrainingDataset", back_populates="model")

    def __repr__(self):
        return f"<VehicleModel(id={self.id}, code={self.code}, name={self.korean_name})>"

    def to_dict(self):
        """딕셔너리 변환 (API 응답용)"""
        return {
            "id": self.id,
            "code": self.code,
            "manufacturer_id": self.manufacturer_id,
            "manufacturer_code": self.manufacturer_code,
            "english_name": self.english_name,
            "korean_name": self.korean_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
