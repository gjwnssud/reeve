"""
Reeve - 차량 제조사/모델 자동 분류 시스템
FastAPI 메인 애플리케이션
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import logging.handlers
from pathlib import Path

from studio.config import settings
from studio.models import init_db
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from studio.tasks.cleanup import cleanup_old_analyzed_vehicles

# 로깅 설정
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_level = getattr(logging, settings.log_level)

# 로그 디렉토리 생성 + 파일 핸들러
log_path = Path(settings.log_file)
log_path.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=log_level,
    format=log_format,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ),
    ],
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 시작/종료 이벤트 처리"""
    # 시작 시
    logger.info("Starting Reeve application...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")
    logger.info(f"Qdrant: {settings.qdrant_url}")

    # 데이터베이스 초기화 (개발 환경에서만)
    if settings.environment == "development":
        logger.info("Initializing database tables...")
        try:
            init_db()
            logger.info("Database initialization completed")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    # 스케줄러 시작 (자동 정리 작업)
    scheduler = AsyncIOScheduler()
    if settings.cleanup_enabled:
        scheduler.add_job(
            cleanup_old_analyzed_vehicles,
            'cron',
            hour=settings.cleanup_hour,
            minute=0,
            id='cleanup_analyzed_vehicles',
            name='Cleanup old analyzed_vehicles'
        )
        scheduler.start()
        logger.info(
            f"Cleanup scheduler started: "
            f"retention={settings.analyzed_vehicles_retention_days} days, "
            f"daily at {settings.cleanup_hour}:00"
        )
    else:
        logger.info("Cleanup scheduler disabled")

    yield

    # 종료 시
    if settings.cleanup_enabled:
        scheduler.shutdown()
        logger.info("Cleanup scheduler stopped")
    logger.info("Shutting down Reeve application...")


# FastAPI 애플리케이션 생성
app = FastAPI(
    title="Reeve - 차량 제조사/모델 자동 분류 시스템",
    description="차량 이미지에서 제조사와 모델을 자동으로 식별하는 AI 기반 시스템",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정 (개발 환경)
if settings.environment == "development":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# 정적 파일 서빙 (프론트엔드)
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

# 데이터 디렉토리 서빙 (업로드된 이미지)
data_path = Path(__file__).parent.parent / "data"
if data_path.exists():
    app.mount("/data", StaticFiles(directory=str(data_path)), name="data")


# HTML 페이지 서빙
from fastapi.responses import FileResponse

@app.get("/admin-ui", tags=["UI"])
async def admin_ui():
    """관리자 UI 페이지"""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"error": "Admin UI not found"}


@app.get("/analyze-ui", tags=["UI"])
async def analyze_ui():
    """이미지 분석 UI 페이지 (차량 감지 + 바운딩 박스 편집 + SSE 스트리밍)"""
    html_path = Path(__file__).parent / "static" / "analyze_v2.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"error": "Analyze UI not found"}



# 전역 예외 핸들러
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """모든 예외를 캐치하여 JSON 응답으로 변환"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.environment == "development" else "An unexpected error occurred"
        }
    )


# 헬스체크 엔드포인트
@app.get("/", tags=["UI"])
async def root():
    """메인 페이지 - 이미지 분석 UI"""
    html_path = Path(__file__).parent / "static" / "analyze_v2.html"
    if html_path.exists():
        return FileResponse(html_path)
    return {"service": "Reeve", "status": "running"}


@app.get("/health", tags=["Health"])
async def health_check():
    """상세 헬스체크"""
    return {
        "status": "healthy",
        "database": "connected",  # TODO: 실제 DB 연결 확인 추가
        "qdrant": "connected",  # TODO: 실제 Qdrant 연결 확인 추가
        "environment": settings.environment
    }


# API 라우터 등록
from studio.api import admin, analyze, finetune
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(analyze.router, prefix="/api", tags=["Analysis"])
app.include_router(finetune.router, prefix="/finetune", tags=["Finetune"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "studio.main:app",
        host="0.0.0.0",
        port=settings.studio_port,
        reload=settings.environment == "development"
    )
