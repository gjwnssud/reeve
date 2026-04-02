"""
분석 결과 모델
"""
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Numeric, Boolean, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from studio.models.database import Base


class AnalyzedVehicle(Base):
    """분석 결과 테이블 (OpenAI Vision API 분석 결과 저장)"""

    __tablename__ = "analyzed_vehicles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    image_path = Column(String(500), nullable=False, index=True)
    raw_result = Column(JSON, nullable=True, comment="OpenAI Vision API 원본 응답")
    manufacturer = Column(String(100), nullable=True, comment="추출된 제조사명")
    model = Column(String(200), nullable=True, comment="추출된 모델명")
    year = Column(String(50), nullable=True, comment="추출된 연식")
    matched_manufacturer_id = Column(
        BigInteger,
        ForeignKey("manufacturers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="매칭된 제조사 ID"
    )
    matched_model_id = Column(
        BigInteger,
        ForeignKey("vehicle_models.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="매칭된 모델 ID"
    )
    confidence_score = Column(Numeric(5, 2), nullable=True, comment="신뢰도 점수 (0-100)")
    is_verified = Column(Boolean, default=False, nullable=False, index=True, comment="검수 완료 여부")
    verified_by = Column(String(100), nullable=True, comment="검수자")
    verified_at = Column(DateTime, nullable=True, comment="검수 일시")
    notes = Column(Text, nullable=True, comment="검수 메모")
    processing_stage = Column(String(50), nullable=True, default='uploaded',
        comment="처리 단계: uploaded/yolo_detected/analysis_complete/verified")
    original_image_path = Column(String(500), nullable=True,
        comment="원본 업로드 이미지 경로 (YOLO 재실행용)")
    yolo_detections = Column(JSON, nullable=True,
        comment="YOLO 감지 결과 bbox 목록")
    selected_bbox = Column(JSON, nullable=True,
        comment="사용자 선택 또는 자동 선택 bbox")
    source = Column(String(20), nullable=False, default='file',
        comment="데이터 출처: file/folder")
    client_uuid = Column(String(36), nullable=True, index=True,
        comment="브라우저 UUID (다중 사용자 구분)")
    created_at = Column(DateTime, default=func.now(), index=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # 관계 설정
    matched_manufacturer = relationship("Manufacturer", back_populates="analyzed_vehicles")
    matched_model = relationship("VehicleModel", back_populates="analyzed_vehicles")

    def __repr__(self):
        return f"<AnalyzedVehicle(id={self.id}, manufacturer={self.manufacturer}, model={self.model}, verified={self.is_verified})>"

    def to_dict(self, include_raw: bool = False):
        """딕셔너리 변환 (API 응답용)
        include_raw=False(기본): 목록 조회 시 raw_result 제외로 응답 크기 축소
        include_raw=True: 상세 조회 시 원본 Vision API 응답 포함
        """
        return {
            "id": self.id,
            "image_path": self.image_path,
            "raw_result": self.raw_result if include_raw else None,
            "manufacturer": self.manufacturer,
            "model": self.model,
            "year": self.year,
            "matched_manufacturer_id": self.matched_manufacturer_id,
            "matched_model_id": self.matched_model_id,
            "confidence_score": float(self.confidence_score) if self.confidence_score else None,
            "is_verified": self.is_verified,
            "verified_by": self.verified_by,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "notes": self.notes,
            "processing_stage": self.processing_stage,
            "original_image_path": self.original_image_path,
            "yolo_detections": self.yolo_detections,
            "selected_bbox": self.selected_bbox,
            "source": self.source,
            "client_uuid": self.client_uuid,
            "created_at": self.created_at.isoformat() + "+00:00" if self.created_at else None,
            "updated_at": self.updated_at.isoformat() + "+00:00" if self.updated_at else None,
        }
