"""
학습 데이터셋 모델
"""
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from studio.models.database import Base


class TrainingDataset(Base):
    """학습 데이터셋 테이블 (검증된 데이터만 저장)"""

    __tablename__ = "training_dataset"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    image_path = Column(String(500), unique=True, nullable=False, comment="검증된 이미지 경로")
    manufacturer_id = Column(
        BigInteger,
        ForeignKey("manufacturers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="제조사 ID"
    )
    model_id = Column(
        BigInteger,
        ForeignKey("vehicle_models.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="모델 ID"
    )
    qdrant_id = Column(String(255), nullable=True, index=True, comment="QdrantDB 문서 ID")
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 관계 설정
    manufacturer = relationship("Manufacturer", back_populates="training_datasets")
    model = relationship("VehicleModel", back_populates="training_datasets")

    def __repr__(self):
        return f"<TrainingDataset(id={self.id}, image_path={self.image_path}, qdrant_id={self.qdrant_id})>"

    def to_dict(self):
        """딕셔너리 변환 (API 응답용)"""
        return {
            "id": self.id,
            "image_path": self.image_path,
            "manufacturer_id": self.manufacturer_id,
            "model_id": self.model_id,
            "qdrant_id": self.qdrant_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
