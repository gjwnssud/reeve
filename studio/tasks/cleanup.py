"""
데이터 라이프사이클 관리 작업
검수 완료된 analyzed_vehicles를 자동으로 정리
"""
import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from studio.models.analyzed_vehicle import AnalyzedVehicle
from studio.models.database import SessionLocal
from studio.config import settings

logger = logging.getLogger(__name__)


async def cleanup_old_analyzed_vehicles():
    """
    오래된 미검수 analyzed_vehicles 자동 삭제

    - 삭제 대상: is_verified=false AND created_at < (현재 - RETENTION_DAYS)
    - 크롭 이미지 + 원본 이미지 + training_dataset + DB 레코드 모두 삭제
    """
    if not settings.cleanup_enabled:
        logger.info("Cleanup is disabled in settings")
        return

    from studio.api.admin import _delete_analyzed_vehicle

    cutoff_date = datetime.now() - timedelta(days=settings.analyzed_vehicles_retention_days)

    # DB 세션 생성
    db = SessionLocal()

    try:
        # 삭제 대상 조회: 미검수 + 오래된 데이터
        old_records = db.query(AnalyzedVehicle).filter(
            and_(
                AnalyzedVehicle.is_verified == False,
                AnalyzedVehicle.created_at < cutoff_date
            )
        ).all()

        if not old_records:
            logger.info(f"No old analyzed_vehicles to clean up (cutoff: {cutoff_date})")
            return

        deleted_count = 0
        deleted_image_count = 0
        failed_image_count = 0

        for record in old_records:
            result = _delete_analyzed_vehicle(record, db)
            deleted_image_count += result["deleted_files"]
            failed_image_count += result["failed_files"]
            deleted_count += 1

        db.commit()

        logger.info(
            f"Cleanup completed: "
            f"deleted {deleted_count} records, "
            f"{deleted_image_count} files deleted, "
            f"{failed_image_count} file deletion failures "
            f"(retention: {settings.analyzed_vehicles_retention_days} days, cutoff: {cutoff_date})"
        )

    except Exception as e:
        db.rollback()
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise

    finally:
        db.close()


async def get_cleanup_stats(db: Session) -> dict:
    """
    정리 대상 통계 조회 (삭제 전 확인용)

    Returns:
        dict: 정리 대상 통계
    """
    cutoff_date = datetime.now() - timedelta(days=settings.analyzed_vehicles_retention_days)

    # 정리 대상 개수 (미검수 + 오래된 데이터)
    cleanup_candidates = db.query(AnalyzedVehicle).filter(
        and_(
            AnalyzedVehicle.is_verified == False,
            AnalyzedVehicle.created_at < cutoff_date
        )
    ).count()

    # 가장 오래된 미검수 레코드
    oldest_unverified = db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).order_by(AnalyzedVehicle.created_at.asc()).first()

    return {
        "retention_days": settings.analyzed_vehicles_retention_days,
        "cutoff_date": cutoff_date.isoformat(),
        "cleanup_candidates": cleanup_candidates,
        "oldest_unverified_at": oldest_unverified.created_at.isoformat() if oldest_unverified else None,
        "cleanup_enabled": settings.cleanup_enabled,
        "next_cleanup_hour": settings.cleanup_hour
    }
