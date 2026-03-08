"""
Celery 애플리케이션 설정
비동기 작업 큐 (Redis broker/backend)
"""
from celery import Celery
from identifier.config import settings

# Celery 앱 생성
celery_app = Celery(
    "identifier",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# Celery 설정
celery_app.conf.update(
    # 작업 시간 제한
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,

    # 재시도 설정
    task_acks_late=True,  # 작업 완료 후 ACK
    task_reject_on_worker_lost=True,

    # 결과 저장
    result_expires=86400,  # 24시간
    result_extended=True,

    # 직렬화
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 워커 설정
    worker_prefetch_multiplier=1,  # 한 번에 1개씩 가져옴 (배치 처리 최적화)
    worker_max_tasks_per_child=100,  # 메모리 누수 방지

    # 타임존
    timezone="Asia/Seoul",
    enable_utc=True,
)

# 태스크 자동 검색
celery_app.autodiscover_tasks(["identifier"])
