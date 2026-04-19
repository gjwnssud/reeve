"""
Reeve - 차량 제조사/모델 자동 분류 시스템
FastAPI 메인 애플리케이션
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
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
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)

    logger.info("Starting Reeve application...")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Database: {settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}")

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


# 데이터 디렉토리 서빙 (업로드된 이미지)
from fastapi.staticfiles import StaticFiles
data_path = Path(__file__).parent.parent / "data"
if data_path.exists():
    app.mount("/data", StaticFiles(directory=str(data_path)), name="data")


# 전역 예외 핸들러
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.environment == "development" else "An unexpected error occurred"
        }
    )


@app.get("/health", tags=["Health"])
async def health_check():
    """상세 헬스체크"""
    return {
        "status": "healthy",
        "database": "connected",
        "environment": settings.environment
    }


# API 라우터 등록 — SPA catch-all보다 먼저 등록해야 API 라우트가 가로채이지 않음
from studio.api import admin, analyze, finetune
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(analyze.router, prefix="/api", tags=["Analysis"])
app.include_router(finetune.router, prefix="/finetune", tags=["Finetune"])


# SPA 라우팅 — 반드시 모든 API 라우터 include_router 이후에 등록
# StaticFiles 마운트 대신 커스텀 라우트를 사용해 SPA 딥링크를 지원한다.
# (StaticFiles 마운트는 파일 미존재 시 FastAPI catch-all을 우회하고 자체 404를 반환함)
from fastapi.responses import RedirectResponse

# 신규 이미지: /app/static/ (studio/ bind-mount와 분리)
# 구 이미지(재빌드 전): /app/studio/static/ (anonymous volume 보호)
_STATIC_DIR = next(
    (p for p in [
        Path(__file__).parent.parent / "static",
        Path(__file__).parent / "static",
    ] if p.is_dir()),
    Path(__file__).parent.parent / "static",
)
_SPA_INDEX = _STATIC_DIR / "index.html"


@app.get("/", include_in_schema=False)
async def spa_root():
    return RedirectResponse(url="/static/", status_code=302)


@app.get("/static", include_in_schema=False)
@app.get("/static/", include_in_schema=False)
async def spa_static_root():
    if _SPA_INDEX.exists():
        return FileResponse(_SPA_INDEX)
    return {"service": "Reeve Studio", "status": "running"}


@app.get("/static/{path:path}", include_in_schema=False)
async def serve_static(path: str):
    """정적 파일이 있으면 반환, 없으면 SPA index.html 반환 (딥링크 지원)"""
    try:
        file_path = (_STATIC_DIR / path).resolve()
        file_path.relative_to(_STATIC_DIR.resolve())  # path traversal 방지
    except ValueError:
        raise HTTPException(status_code=403)
    if file_path.is_file():
        return FileResponse(file_path)
    if _SPA_INDEX.exists():
        return FileResponse(_SPA_INDEX)
    raise HTTPException(status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "studio.main:app",
        host="0.0.0.0",
        port=settings.studio_port,
        reload=settings.environment == "development"
    )
