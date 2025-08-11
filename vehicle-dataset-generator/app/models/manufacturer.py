from sqlalchemy import Column, BigInteger, String, Boolean, DateTime, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Manufacturer(Base):
    """제조사 모델"""
    __tablename__ = 'manufacturers'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(50), nullable=False, unique=True, index=True)
    english_name = Column(String(100), nullable=False)
    korean_name = Column(String(100), nullable=False)
    is_domestic = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=func.current_timestamp())
    updated_at = Column(DateTime, default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # 복합 인덱스
    __table_args__ = (
        Index('idx_domestic_code', 'is_domestic', 'code'),
    )
    
    def to_dict(self):
        """딕셔너리로 변환"""
        return {
            'id': self.id,
            'code': self.code,
            'english_name': self.english_name,
            'korean_name': self.korean_name,
            'is_domestic': self.is_domestic,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
    
    def __repr__(self):
        return f"<Manufacturer(id={self.id}, code='{self.code}', korean_name='{self.korean_name}')>"
