# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Reeve** is an AI-powered vehicle manufacturer and model auto-classification system. It is a monorepo of three FastAPI microservices backed by MySQL, Qdrant (vector DB), Redis, and Ollama.

## Development Commands

### Running Services

```bash
# Linux/Windows (NVIDIA GPU)
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d

# Mac (Apple Silicon)
docker compose -f docker/docker-compose.yml -f docker/docker-compose.mac.yml up -d
```

### Reindexing the Qdrant Knowledge Base

```bash
python3 .claude/index_qdrant.py --clear
```

### Deployment Packaging

```bash
# Creates self-contained deployment packages
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows]
```

## Architecture

Three microservices communicate over a shared Docker network:

| Service | Port | Purpose |
|---------|------|---------|
| `studio` | 8000 | Web UI, admin CRUD, image upload, OpenAI/Ollama vision analysis |
| `identifier` | 8001 | ML pipeline: YOLO detection → EfficientNetV2-M embeddings → Qdrant search → voting |
| `trainer` | 8002 | Fine-tuning backend (LlamaFactory on Linux/Windows, MLX on Mac) |

### Vehicle Identification Pipeline (`identifier/`)

Default mode: `efficientnet`

1. **YOLO26** — detects vehicle bounding boxes
2. **EfficientNetV2-M** — extracts 1280-dim feature vectors and classifies
3. confidence ≥ 0.9 → return result directly
4. confidence < 0.9 → **Qwen3-VL:8b** fallback inference

Other modes (configured via `IDENTIFIER_MODE`):
- `visual_rag`: EfficientNet embedding → Qdrant search → always calls Qwen3-VL for final judgment
- `vlm_only`: YOLO crop → Qwen3-VL only (no Qdrant/embedding)

Async batch jobs are handled by **Celery + Redis** (`identifier/start_worker.sh`).

### Studio Service (`studio/`)

- Manages Manufacturer, VehicleModel, AnalyzedVehicle, TrainingDataset entities (SQLAlchemy + MySQL)
- Calls `identifier` for ML analysis and `trainer` for fine-tuning jobs
- Uses OpenAI (GPT-5-mini) or local Ollama (Qwen3-VL:8b) for vision pre-analysis
- APScheduler runs automatic cleanup of old analyzed vehicles

### Trainer Service (`trainer/`)

- On Linux/Windows: wraps LlamaFactory CLI for LLM fine-tuning
- On Mac: uses MLX backend (Apple Silicon native)
- Supports EfficientNet classifier fine-tuning as well

## Configuration

Copy `docker/.env.example` to `docker/.env` and configure:
- `OPENAI_API_KEY` / `GEMINI_API_KEY` for cloud vision
- MySQL credentials (dev only — production uses external DB)
- `EMBEDDING_DEVICE` (`cuda` / `cpu`)
- Identifier mode and VLM settings
- Retention and cleanup schedule for analyzed vehicles

## Key File Locations

- Entry points: `studio/main.py`, `identifier/main.py`, `trainer/main.py`
- ML inference core: `identifier/services/`
- Database models: `studio/models/`
- OpenAI vision wrapper: `studio/services/openai_vision.py` (current model: `gpt-5-mini`)
- SQL schema & seed data: `sql/`
- Architecture diagram: `docs/architecture.svg`
- Async API usage guide: `docs/ASYNC_USAGE.md`

## Platform Notes

- `docker/docker-compose.dev.yml` — Linux/Windows with NVIDIA GPU; hot-reload via bind mounts
- `docker/docker-compose.mac.yml` — Apple Silicon; uses CPU/MLX backends instead of CUDA
- `Dockerfile.identifier` is multi-arch (`linux/amd64` builds with CUDA, `linux/arm64` uses CPU)
- Uvicorn worker count in `identifier/start.sh` is auto-calculated from CPU core count
