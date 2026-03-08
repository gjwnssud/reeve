"""
제조사 모델
"""
from sqlalchemy import Column, BigInteger, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from studio.models.database import Base


class  Manufacturer(Base):
    """제조사 테이블 (사용자 제공 DDL 기반)"""

    __tablename__ = "manufacturers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    english_name = Column(String(100), nullable=False)
    korean_name = Column(String(100), nullable=False)
    is_domestic = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 관계 설정
    vehicle_models = relationship("VehicleModel", back_populates="manufacturer", cascade="all, delete-orphan")
    analyzed_vehicles = relationship("AnalyzedVehicle", back_populates="matched_manufacturer")
    training_datasets = relationship("TrainingDataset", back_populates="manufacturer")

    def __repr__(self):
        return f"<Manufacturer(id={self.id}, code={self.code}, name={self.korean_name})>"

    def to_dict(self):
        """딕셔너리 변환 (API 응답용)"""
        return {
            "id": self.id,
            "code": self.code,
            "english_name": self.english_name,
            "korean_name": self.korean_name,
            "is_domestic": self.is_domestic,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
