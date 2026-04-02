"""
데이터베이스 연결 및 세션 관리
SQLAlchemy를 사용한 동기/비동기 DB 연결
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator, AsyncGenerator
from studio.config import settings

# SQLAlchemy Base 클래스
Base = declarative_base()

# 동기 엔진 (일반 작업용)
engine = create_engine(
    settings.database_url,
    pool_size=20,        # 기본 커넥션 풀 크기
    max_overflow=40,     # 풀 초과 시 추가 허용 커넥션 수 (최대 60개)
    pool_timeout=60,     # 커넥션 대기 타임아웃 (초)
    pool_pre_ping=True,  # 연결 전 ping으로 유효성 확인
    pool_recycle=3600,   # 1시간마다 연결 재생성
    echo=False
)

# 비동기 엔진 (고성능 API용)
async_engine = create_async_engine(
    settings.async_database_url,
    pool_size=20,
    max_overflow=40,
    pool_timeout=60,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False
)

# 세션 팩토리
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session
)

# 비동기 세션 팩토리
AsyncSessionLocal = async_sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """
    동기 데이터베이스 세션 의존성
    FastAPI Depends에서 사용
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    비동기 데이터베이스 세션 의존성
    FastAPI Depends에서 사용 (비동기 엔드포인트)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def init_db():
    """
    데이터베이스 초기화
    테이블 생성 (마이그레이션 파일이 실행되지 않은 경우)
    """
    # 주의: 프로덕션에서는 마이그레이션 도구(Alembic) 사용 권장
    Base.metadata.create_all(bind=engine)
