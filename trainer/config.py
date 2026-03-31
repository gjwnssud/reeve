"""
Trainer 서비스 설정
TRAINER_BACKEND=llamafactory  → Linux/Windows (Docker, LlamaFactory CLI)
TRAINER_BACKEND=mlx           → Mac Apple Silicon (네이티브, mlx-lm)
TRAINER_BACKEND=efficientnet  → EfficientNetV2-M 이미지 분류기 (PyTorch, MPS/CUDA/CPU 자동 감지)
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Literal, Optional
from pathlib import Path


class Settings(BaseSettings):
    trainer_backend: Literal["llamafactory", "mlx", "efficientnet"] = Field(
        default="llamafactory",
        alias="TRAINER_BACKEND",
    )
    # 학습 데이터 디렉토리 (컨테이너 내: /app/data, 네이티브: data/finetune)
    data_dir: str = Field(default="data/finetune", alias="TRAINER_DATA_DIR")
    # 체크포인트 출력 디렉토리 (컨테이너 내: /app/output, 네이티브: output)
    output_dir: str = Field(default="output", alias="TRAINER_OUTPUT_DIR")

    # Ollama 배포
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    identifier_url: str = Field(default="http://localhost:8001", alias="IDENTIFIER_URL")
    # llama.cpp의 convert_hf_to_gguf.py 절대 경로 (미설정 시 GGUF 자동변환 비활성)
    gguf_converter_path: Optional[str] = Field(default=None, alias="GGUF_CONVERTER_PATH")

    # EfficientNet 학습 설정
    efficientnet_model_dir: str = Field(default="output/efficientnet", alias="EFFICIENTNET_MODEL_DIR")
    studio_url: str = Field(default="http://localhost:8000", alias="STUDIO_URL")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir).resolve()

    @property
    def output_path(self) -> Path:
        return Path(self.output_dir).resolve()


settings = Settings()
