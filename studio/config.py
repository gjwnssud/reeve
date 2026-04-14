"""
Studio 서비스 설정 관리
환경변수를 pydantic-settings로 로드하여 타입 안전성 보장
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Studio 서비스 전역 설정"""

    # API 설정
    studio_port: int = Field(default=8000, alias="STUDIO_PORT")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # MySQL 데이터베이스 설정
    mysql_host: str = Field(default="localhost", alias="MYSQL_HOST")
    mysql_port: int = Field(default=3306, alias="MYSQL_PORT")
    mysql_database: str = Field(default="reeve", alias="MYSQL_DATABASE")
    mysql_user: str = Field(default="reeve_user", alias="MYSQL_USER")
    mysql_password: str = Field(default="", alias="MYSQL_PASSWORD")

    # OpenAI API
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: Optional[str] = Field(default="gpt-5-mini", alias="OPENAI_MODEL")

    # Gemini API
    gemini_api_key: Optional[str] = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    # 임베딩 설정
    embedding_device: str = Field(default="cpu", alias="EMBEDDING_DEVICE")

    # 파일 업로드 설정
    max_upload_size: int = Field(default=5242880, alias="MAX_UPLOAD_SIZE")  # 5MB
    allowed_extensions: str = Field(default="jpg,jpeg,png,webp", alias="ALLOWED_EXTENSIONS")

    # 매칭 알고리즘 설정
    fuzzy_match_threshold: int = Field(default=80, alias="FUZZY_MATCH_THRESHOLD")

    # 로깅 설정
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_file: str = Field(default="./logs/studio/service.log", alias="STUDIO_LOG_FILE")

    # 데이터 라이프사이클 설정
    analyzed_vehicles_retention_days: int = Field(
        default=30,
        alias="ANALYZED_VEHICLES_RETENTION_DAYS",
        description="검수 완료 후 analyzed_vehicles 보관 기간 (일)"
    )
    cleanup_enabled: bool = Field(
        default=True,
        alias="CLEANUP_ENABLED",
        description="자동 정리 활성화 여부"
    )
    cleanup_hour: int = Field(
        default=3,
        alias="CLEANUP_HOUR",
        description="자동 정리 실행 시간 (0-23시)"
    )

    # Trainer 서비스 URL (파인튜닝 API)
    trainer_url: str = Field(
        default="http://localhost:8002",
        alias="TRAINER_URL",
        description="Trainer 서비스 URL (LlamaFactory 또는 MLX 백엔드)"
    )

    identifier_url: str = Field(
        default="http://localhost:8001",
        alias="IDENTIFIER_URL",
        description="Identifier 서비스 URL (Before/After 평가용)"
    )

    # Vision 백엔드 설정
    vision_backend: str = Field(
        default="openai",
        alias="VISION_BACKEND",
        description="Vision 분석 백엔드 (openai 또는 ollama)"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
        description="Ollama 서버 URL"
    )
    studio_vlm_model: str = Field(
        default="qwen3-vl:8b",
        alias="STUDIO_VLM_MODEL",
        description="Studio용 VLM 모델명"
    )
    studio_vlm_timeout: int = Field(
        default=60,
        alias="STUDIO_VLM_TIMEOUT",
        description="VLM 요청 타임아웃 (초)"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @property
    def database_url(self) -> str:
        """SQLAlchemy 데이터베이스 URL 생성"""
        return f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"

    @property
    def async_database_url(self) -> str:
        """비동기 SQLAlchemy 데이터베이스 URL 생성"""
        return f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"

    @property
    def allowed_extensions_list(self) -> list[str]:
        """허용된 파일 확장자 리스트"""
        return [ext.strip() for ext in self.allowed_extensions.split(",")]


# 전역 설정 인스턴스
settings = Settings()
