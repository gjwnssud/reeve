"""
Trainer 서비스 — FastAPI 앱
파인튜닝 백엔드를 추상화:
- llamafactory: LlamaFactory CLI (Linux/Windows, NVIDIA GPU)
- mlx: mlx-lm (Mac Apple Silicon, 네이티브)
"""
import logging
from fastapi import FastAPI
from trainer.api.train import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Reeve Trainer",
    description="파인튜닝 API (LlamaFactory / MLX 백엔드)",
    version="1.0.0",
)

app.include_router(router, tags=["Train"])


@app.get("/health")
async def health():
    from trainer.config import settings
    return {"status": "ok", "backend": settings.trainer_backend}
