"""
Celery 비동기 작업 태스크
차량 판별 작업을 백그라운드 큐로 처리
"""
import contextvars
import logging
import tempfile
import os
from typing import List, Optional

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from identifier.celery_app import celery_app
from identifier.config import settings

logger = logging.getLogger(__name__)

# main.py와 동일한 컨텍스트 변수 (워커 프로세스에서 독립)
_request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class IdentifierTask(Task):
    """
    VehicleIdentifier 싱글톤을 관리하는 베이스 태스크

    워커 프로세스당 1개의 identifier 인스턴스만 생성
    """
    _identifier = None

    @property
    def identifier(self):
        if self._identifier is None:
            from identifier.identifier import VehicleIdentifier
            logger.info("Initializing VehicleIdentifier in worker...")
            self._identifier = VehicleIdentifier()
            self._identifier.initialize()
        return self._identifier

    def _restore_request_id(self):
        """Celery 헤더에서 request_id를 복원하여 contextvars에 세팅"""
        headers = getattr(self.request, "headers", None) or {}
        rid = headers.get("request_id", "-")
        _request_id_var.set(rid)


@celery_app.task(
    bind=True,
    base=IdentifierTask,
    max_retries=settings.celery_max_retries,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def identify_image_task(
    self,
    image_path: str,
    bbox: Optional[List[int]] = None,
) -> dict:
    """
    단일 이미지 판별 작업

    Args:
        image_path: 이미지 파일 경로 (서버 파일시스템)
        bbox: 선택된 차량 bbox (옵션)

    Returns:
        IdentificationResult.dict()
    """
    self._restore_request_id()
    try:
        logger.info(f"Task {self.request.id}: Processing {image_path}")
        result = self.identifier.identify(image_path, bbox)
        return result.dict()
    except SoftTimeLimitExceeded:
        logger.error(
            f"Task {self.request.id}: SoftTimeLimitExceeded for {image_path}"
        )
        return {
            "status": "low_confidence",
            "confidence": 0.0,
            "message": "처리 시간 초과 — 이미지를 다시 시도해 주세요.",
        }
    except Exception as e:
        logger.error(f"Task {self.request.id} failed: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=IdentifierTask,
    max_retries=settings.celery_max_retries,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def identify_batch_task(
    self,
    image_paths: List[str],
    batch_size: Optional[int] = None,
) -> dict:
    """
    배치 이미지 판별 작업

    Args:
        image_paths: 이미지 파일 경로 리스트
        batch_size: 내부 배치 크기 (기본값: 설정값)

    Returns:
        BatchIdentificationResult.dict()
    """
    self._restore_request_id()
    try:
        logger.info(
            f"Task {self.request.id}: Processing batch "
            f"({len(image_paths)} images)"
        )
        batch_size = batch_size or settings.batch_size
        result = self.identifier.identify_batch(image_paths, batch_size)
        return result.dict()
    except SoftTimeLimitExceeded:
        logger.error(
            f"Task {self.request.id}: SoftTimeLimitExceeded for batch "
            f"({len(image_paths)} images)"
        )
        return {
            "status": "low_confidence",
            "confidence": 0.0,
            "message": f"배치 처리 시간 초과 ({len(image_paths)}장)",
            "items": [],
            "total": len(image_paths),
            "success_count": 0,
            "error_count": len(image_paths),
            "processing_time_ms": 0.0,
        }
    except Exception as e:
        logger.error(f"Task {self.request.id} failed: {e}", exc_info=True)
        raise


@celery_app.task(
    bind=True,
    base=IdentifierTask,
    max_retries=settings.celery_max_retries,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
)
def identify_uploaded_files_task(
    self,
    temp_file_paths: List[str],
    original_filenames: List[str],
    batch_size: Optional[int] = None,
) -> dict:
    """
    업로드된 파일 배치 판별 (임시 파일 자동 정리)

    Args:
        temp_file_paths: 임시 파일 경로 리스트
        original_filenames: 원본 파일명 리스트
        batch_size: 내부 배치 크기

    Returns:
        BatchIdentificationResult.dict() (image_path는 원본 파일명)
    """
    self._restore_request_id()
    try:
        logger.info(
            f"Task {self.request.id}: Processing uploaded files "
            f"({len(temp_file_paths)} files)"
        )
        batch_size = batch_size or settings.batch_size
        result = self.identifier.identify_batch(temp_file_paths, batch_size)

        # 원본 파일명으로 복원
        for i, item in enumerate(result.items):
            if i < len(original_filenames):
                item.image_path = original_filenames[i]

        return result.dict()

    except SoftTimeLimitExceeded:
        logger.error(
            f"Task {self.request.id}: SoftTimeLimitExceeded for uploaded files "
            f"({len(temp_file_paths)} files)"
        )
        return {
            "status": "low_confidence",
            "confidence": 0.0,
            "message": f"업로드 파일 처리 시간 초과 ({len(temp_file_paths)}장)",
            "items": [],
            "total": len(temp_file_paths),
            "success_count": 0,
            "error_count": len(temp_file_paths),
            "processing_time_ms": 0.0,
        }
    except Exception as e:
        logger.error(f"Task {self.request.id} failed: {e}", exc_info=True)
        raise

    finally:
        # 임시 파일 정리
        for temp_path in temp_file_paths:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
