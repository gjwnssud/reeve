"""
차량 판별 서비스 설정
Studio와 독립적으로 동작하며, 공유 .env 파일에서 필요한 설정만 읽음
"""
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class IdentifierSettings(BaseSettings):
    """차량 판별 서비스 전용 설정"""

    # 서비스 설정
    identifier_port: int = Field(default=8001, alias="IDENTIFIER_PORT")

    # Qdrant
    qdrant_host: str = Field(default="localhost", alias="QDRANT_HOST")
    qdrant_port: int = Field(default=6333, alias="QDRANT_PORT")

    # Redis (Celery broker/backend)
    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_db: int = Field(default=0, alias="REDIS_DB")

    # 임베딩 모델
    embedding_device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")

    # 파일 업로드
    max_upload_size: int = Field(default=5242880, alias="MAX_UPLOAD_SIZE")  # 5MB
    allowed_extensions: str = Field(default="jpg,jpeg,png,webp", alias="ALLOWED_EXTENSIONS")

    # 판별 알고리즘 설정
    top_k: int = Field(default=10, alias="IDENTIFIER_TOP_K")
    confidence_threshold: float = Field(default=0.80, alias="IDENTIFIER_CONFIDENCE_THRESHOLD")
    min_similarity: float = Field(default=0.3, alias="IDENTIFIER_MIN_SIMILARITY")
    vote_threshold: int = Field(default=3, alias="IDENTIFIER_VOTE_THRESHOLD")
    vote_concentration_threshold: float = Field(default=0.3, alias="IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD")

    # 차량 감지 (YOLO26)
    vehicle_detection: bool = Field(default=True, alias="IDENTIFIER_VEHICLE_DETECTION")
    yolo_confidence: float = Field(default=0.25, alias="IDENTIFIER_YOLO_CONFIDENCE")
    crop_padding: int = Field(default=10, alias="IDENTIFIER_CROP_PADDING")
    require_vehicle_detection: bool = Field(default=False, alias="IDENTIFIER_REQUIRE_VEHICLE_DETECTION")

    # 배치 처리
    batch_size: int = Field(default=32, alias="IDENTIFIER_BATCH_SIZE")
    max_batch_files: int = Field(default=100, alias="IDENTIFIER_MAX_BATCH_FILES")
    max_batch_upload_size: int = Field(default=104857600, alias="IDENTIFIER_MAX_BATCH_UPLOAD_SIZE")  # 100MB

    # 성능 튜닝
    torch_threads: int = Field(default=8, alias="IDENTIFIER_TORCH_THREADS")
    enable_torch_compile: bool = Field(default=True, alias="IDENTIFIER_ENABLE_TORCH_COMPILE")

    # 판별 모드: "efficientnet" (기본), "embedding_only", "visual_rag", "vlm_only"
    identifier_mode: str = Field(default="efficientnet", alias="IDENTIFIER_MODE")

    # EfficientNetV2-M 분류기
    efficientnet_model_path: Optional[str] = Field(
        default=None, alias="EFFICIENTNET_MODEL_PATH",
        description="파인튜닝된 EfficientNetV2-M .pth 파일 경로. 없으면 부트스트랩 모드(특징 추출만)"
    )
    efficientnet_class_mapping_path: Optional[str] = Field(
        default=None, alias="EFFICIENTNET_CLASS_MAPPING_PATH",
        description="class_mapping.json 파일 경로"
    )
    classifier_confidence_threshold: float = Field(
        default=0.0, alias="CLASSIFIER_CONFIDENCE_THRESHOLD",
        description=(
            "EfficientNetV2-M 분류기 'identified' 판정 최소 신뢰도. "
            "0이면 confidence_threshold (IDENTIFIER_CONFIDENCE_THRESHOLD) 값을 자동 사용."
        )
    )
    classifier_low_confidence_threshold: float = Field(
        default=0.40, alias="CLASSIFIER_LOW_CONFIDENCE_THRESHOLD",
        description=(
            "EfficientNetV2-M 분류기에서 VLM 폴백으로 내려가는 최소 신뢰도. "
            "이 값 이상이면 분류기 결과를 low_confidence로 반환 (VLM 없음). "
            "이 값 미만이면 VLM 폴백 실행."
        )
    )

    # VLM (Ollama) 설정
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    vlm_model_name: str = Field(default="qwen3-vl:8b", alias="VLM_MODEL_NAME")
    vlm_timeout: float = Field(default=30.0, alias="VLM_TIMEOUT")
    vlm_max_candidates: int = Field(default=5, alias="VLM_MAX_CANDIDATES")
    vlm_fallback_to_embedding: bool = Field(default=True, alias="VLM_FALLBACK_TO_EMBEDDING")
    vlm_batch_concurrency: int = Field(default=2, alias="VLM_BATCH_CONCURRENCY")
    vlm_max_retries: int = Field(default=2, alias="VLM_MAX_RETRIES",
                                  description="VLM 호출 최대 재시도 횟수 (타임아웃/5xx만 재시도)")
    vlm_circuit_breaker_threshold: int = Field(default=3, alias="VLM_CIRCUIT_BREAKER_THRESHOLD",
                                                description="서킷 브레이커 open 전환 연속 실패 횟수")
    vlm_circuit_breaker_cooldown: float = Field(default=30.0, alias="VLM_CIRCUIT_BREAKER_COOLDOWN",
                                                 description="서킷 브레이커 open→half-open 대기 시간 (초)")

    # Celery
    celery_task_time_limit: int = Field(default=600, alias="CELERY_TASK_TIME_LIMIT")  # 10분
    celery_task_soft_time_limit: int = Field(default=540, alias="CELERY_TASK_SOFT_TIME_LIMIT")  # 9분
    celery_max_retries: int = Field(default=3, alias="CELERY_MAX_RETRIES")

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    # 로깅
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="./logs/identifier/service.log", alias="IDENTIFIER_LOG_FILE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip() for ext in self.allowed_extensions.split(",")]


settings = IdentifierSettings()
