# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reeve is an AI-powered vehicle manufacturer/model identification system. It has two independent FastAPI services:

- **Studio (port 8000)** — Development & admin service. Uses OpenAI Vision API (gpt-4o) for initial vehicle analysis, MySQL for structured data, and syncs verified training data to Qdrant.
- **Identifier (port 8001)** — Production identification service. Lightweight, MySQL-free. Uses CLIP image embeddings + Qdrant vector search with weighted voting to identify vehicles. Supports sync batch and async (Celery) processing.

**Data flow:** Image → OpenAI Vision → fuzzy match to DB → admin review → CLIP embedding → Qdrant → identifier service uses trained vectors for future identification.

## Commands

```bash
# Start Studio (Mac)
cd docker && ./dev/mac/start.sh

# Start Studio (Linux)
cd docker && ./dev/linux/start.sh

# Start production only (qdrant + identifier + redis + celery-worker + ollama)
cd docker && docker compose -f docker-compose.yml up -d

# Run studio locally
uvicorn studio.main:app --reload --port 8000

# Run identifier locally
uvicorn identifier.main:app --reload --port 8001

# Run celery worker locally
celery -A identifier.celery_app worker --loglevel=info

# Tests
pytest
pytest -k test_name          # single test
pytest --asyncio-mode=auto   # async tests
```

## Architecture

```
studio/                              identifier/
├── api/                          ├── main.py         (FastAPI entry, sync + async endpoints)
│   ├── admin.py  (CRUD, review,  ├── config.py       (Pydantic Settings)
│   │   sync, batch,              ├── identifier.py   (voting algorithm, batch support)
│   │   bulk-delete)              ├── celery_app.py   (Celery config, Redis broker)
│   ├── analyze.py (vision, SSE,  ├── tasks.py        (Celery tasks: single/batch)
│   │      detection,             ├── vlm_service.py  (Ollama VLM integration)
│   │      date-based dirs)       ├── start.sh        (uvicorn, workers auto-calc)
│   └── finetune.py (export,      └── start_worker.sh (celery worker startup)
│          deploy-cmd)
├── models/         (SQLAlchemy ORM: manufacturers, vehicle_models,
│                    analyzed_vehicles, training_dataset)
├── services/
│   ├── openai_vision.py   (gpt-4o integration)
│   ├── matcher.py         (code match → RapidFuzz → auto-register)
│   ├── embedding.py       (CLIP image embeddings, 512d)
│   ├── vectordb.py        (Qdrant: training_images collection only)
│   ├── vehicle_detector.py (YOLO26)
│   ├── image_utils.py
│   └── llm_local.py       (local Vision LLM, air-gapped env)
└── static/
    ├── index.html      (관리자: 기초DB관리 탭 + 학습데이터추출 탭)
    ├── analyze_v2.html (분석 UI, 메인 페이지 /)
    └── finetune.html   (파인튜닝 관리 UI: Export + 배포 커맨드)
```

### Key design decisions

- **Single Qdrant collection** (`training_images`, 512d CLIP). Manufacturer/model names are denormalized into the Qdrant payload so identifier doesn't need MySQL.
- **Identifier is MySQL-free.** It reads names directly from Qdrant payload fields: `manufacturer_korean`, `manufacturer_english`, `model_korean`, `model_english`.
- **Identifier voting algorithm** (`identifier.py`): queries top-K similar images, aggregates by (manufacturer_id, model_id) pair, applies adaptive confidence threshold (`IDENTIFIER_VOTE_THRESHOLD`). Two safeguards prevent false positives: **vote concentration** (winner's share of top-K must exceed `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD`, default 30%) and **YOLO detection penalty** (if no vehicle detected, result is capped at `uncertain` regardless of similarity score).
- **Identifier modes** (`IDENTIFIER_MODE`): `clip_only` (default), `visual_rag` (CLIP candidates → VLM rerank), `vlm_only`. VLM via Ollama (`OLLAMA_BASE_URL`, `VLM_MODEL_NAME`).
- **Identifier OpenAPI docs** (`main.py`): comprehensive Swagger documentation with endpoint guides, status interpretation tables, async polling instructions, and Pydantic Field descriptions on all response models. Designed for CCTV integration engineers.
- **Batch processing**: YOLO/CLIP/Qdrant all run in batch mode. `/identify/batch` accepts up to 100 files / 100MB.
- **Async queue pattern**: FastAPI (identifier) pushes to Redis queue → Celery Worker pulls and processes → result stored in Redis 24h. API and Worker share the same Docker image (`Dockerfile.identifier`) but run as separate containers.
- **Finetune pipeline** (`studio/api/finetune.py`): Export training data → saves `vehicle_train.json`, `vehicle_val.json`, `dataset_info.json` directly to `data/finetune/` (LLaMA-Factory sharegpt format, auto-registered) → LLaMA-Factory WebUI (port 7860) → QLoRA 4bit training → LoRA merge → GGUF convert → Ollama deploy. Train/stop/status/logs endpoints removed — LLaMA-Factory WebUI handles training.
- **Docker Compose env-specific files**: `docker-compose.yml` is the production base (qdrant + identifier + redis + celery-worker + ollama + llamafactory with NVIDIA GPU). `.env`는 `docker/.env`에 위치. OS별 override는 `docker/dev/` 하위에 분리: `dev/mac/docker-compose.yml` (ollama+llamafactory CPU 모드, mysql+studio 추가), `dev/linux/docker-compose.yml` (NVIDIA GPU 유지, mysql+studio 추가), `dev/windows/docker-compose.yml` (GPU 유지, mysql+studio 추가). `docker-compose.override.yml` 삭제됨. Identifier standalone은 `docker/prod/{linux,windows}/docker-compose.yml` (별도 compose, pre-built image 사용).
- **DB-First upload architecture** (`analyze.py`): `POST /api/upload` first saves file to `data/uploads/YYYY-MM-DD/` and creates `analyzed_vehicles` record (processing_stage='uploaded'). Frontend then calls `POST /api/detect-vehicle` (YOLO), user selects bbox, then `POST /api/analyze-vehicle-stream` triggers SSE: crop → Vision API → DB update. This separates file ingestion from analysis.
- **Studio UI routing**: `GET /` and `GET /analyze-ui` → analyze_v2.html (main). `GET /admin-ui` → index.html with two tabs: "기초DB관리" (CRUD) and "학습데이터추출" (export + LLaMA-Factory link).
- **Workers auto-calculation**: `workers = cpu_count // IDENTIFIER_TORCH_THREADS`. Set only `IDENTIFIER_TORCH_THREADS` in `.env`; `start.sh` calculates the rest.
- **Date-based file storage**: Uploads and crops saved under `data/uploads/YYYY-MM-DD/` and `data/crops/YYYY-MM-DD/` for organized lifecycle management.
- **File delete policy** (`admin.py`): Both individual delete (`DELETE /review/{id}`) and bulk delete (`DELETE /review-delete-all`) remove crop image AND original upload file (`raw_result.original_image`) in addition to MySQL record. Bulk delete uses a single SQL query instead of N individual API calls.
- **Qdrant version**: `latest` tag (previously pinned to v1.13.2). Scalar Quantization available when dataset grows large (apply via PATCH API — no re-ingestion needed).

## Configuration

Both services use Pydantic Settings loading from `.env`. Key settings:

| Variable | Used by | Purpose |
|----------|---------|---------|
| `QDRANT_HOST` / `QDRANT_PORT` | both | Vector DB connection |
| `EMBEDDING_DEVICE` | both | `cpu` or `cuda` |
| `OPENAI_API_KEY` | studio | Vision API |
| `MYSQL_*` | studio only | Database connection |
| `IDENTIFIER_TOP_K` | identifier | Qdrant 검색 결과 수 (default 10) |
| `IDENTIFIER_VOTE_THRESHOLD` | identifier | Minimum votes for confident match (default 3) |
| `IDENTIFIER_CONFIDENCE_THRESHOLD` | identifier | Minimum confidence score (default 0.80) |
| `IDENTIFIER_MIN_SIMILARITY` | identifier | Minimum cosine similarity to consider (default 0.3) |
| `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD` | identifier | Min winner vote ratio in top-K (default 0.3 = 30%) |
| `IDENTIFIER_VEHICLE_DETECTION` | identifier | Enable YOLO detection (default true) |
| `IDENTIFIER_REQUIRE_VEHICLE_DETECTION` | identifier | Block `identified` if YOLO misses vehicle (default false) |
| `IDENTIFIER_YOLO_CONFIDENCE` | identifier | YOLO detection confidence threshold (default 0.25) |
| `IDENTIFIER_CROP_PADDING` | identifier | Padding around detected bbox in pixels (default 10) |
| `IDENTIFIER_TORCH_THREADS` | identifier | PyTorch threads per worker (also controls worker count) |
| `IDENTIFIER_BATCH_SIZE` | identifier | Internal batch size for CLIP/Qdrant (default 32) |
| `IDENTIFIER_MAX_BATCH_FILES` | identifier | Max files for `/identify/batch` (default 100) |
| `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` | identifier | Max total size for `/identify/batch` (default 100MB) |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | identifier | Enable torch.compile JIT (default true) |
| `REDIS_HOST` / `REDIS_PORT` / `REDIS_DB` | identifier | Redis connection for Celery (DB default 0) |
| `CELERY_TASK_TIME_LIMIT` | identifier | Task hard timeout in seconds (default 600) |
| `CELERY_TASK_SOFT_TIME_LIMIT` | identifier | Task soft timeout for graceful shutdown (default 540) |
| `CELERY_MAX_RETRIES` | identifier | Auto-retry count on failure (default 3) |
| `IDENTIFIER_MODE` | identifier | `clip_only` / `visual_rag` / `vlm_only` (default: clip_only) |
| `OLLAMA_BASE_URL` | identifier | Ollama server URL (default: http://localhost:11434) |
| `VLM_MODEL_NAME` | identifier | Ollama model name (default: vehicle-vlm-v1) |
| `VLM_TIMEOUT` | identifier | VLM request timeout in seconds (default 30) |
| `VLM_MAX_CANDIDATES` | identifier | Candidates passed to VLM in visual_rag mode (default 5) |
| `VLM_FALLBACK_TO_CLIP` | identifier | Fall back to CLIP result on VLM failure (default true) |
| `VLM_BATCH_CONCURRENCY` | identifier | Concurrent VLM calls in batch mode (default 2) |
| `FUZZY_MATCH_THRESHOLD` | studio | RapidFuzz match threshold (0-100, default 80) |
| `LOG_LEVEL` | both | Logging level (INFO, DEBUG, etc.) |
| `STUDIO_LOG_FILE` | studio | Application log file path |
| `IDENTIFIER_LOG_FILE` | identifier | Identifier service log file path |

## Database

MySQL 8.0 with 4 tables. Schema in `sql/user_provided_ddl.sql`, seed data in `sql/user_provided_dml.sql`. Auto-initialized by Docker.

- `manufacturers` → `vehicle_models` (1:N, cascade delete)
- `analyzed_vehicles` references both (SET NULL on delete). All migration ALTER TABLEs merged into DDL — columns include: `original_image_path`, `source`, `client_uuid`, `processing_stage`, `yolo_detections`, `selected_bbox`.
- `training_dataset` stores verified data linked to Qdrant via `qdrant_id` (7 columns; embedding_vector removed — Qdrant is source of truth)
- Migration files (`sql/migration_*.sql`) have been consolidated into `sql/user_provided_ddl.sql` — apply DDL only for fresh installs.

## Language

Project documentation and code comments are in Korean. User-facing UI text is Korean. Variable names and API paths are in English.

## MCP & Knowledge Base Usage (Qdrant)

This repository utilizes a Qdrant-based MCP server to manage and retrieve long-term project context.

### 1. Dynamic Environment Discovery
- **Setup Identification**: Before indexing or searching, verify the active Qdrant collection name via environment variables or `/mcp` config.
- **Project Mapping**: Analyze the root directory to identify core source folders (e.g., `studio/`, `src/`, `identifier/`). Do not assume fixed paths.

### 2. Search & Retrieval Strategy
- **Knowledge-First Approach**: For complex logic or architectural questions, proactively search the vector DB to ensure consistency with existing patterns.
- **Context Management**: Use search results to supplement the session context rather than loading entire large files manually.

### 3. Stability-Focused Indexing (Anti-500 Error)
- **Batch Processing**: To prevent API 500 errors, avoid indexing the entire repository at once. Index in small batches (e.g., 5-10 files or one sub-directory at a time).
- **Incremental Sync**: After code changes, re-index only the modified files to keep the knowledge base fresh without wasting tokens.
- **Command**: "Sync the modified files in [collection-name] collection, 5 files at a time."

### 4. Data Hygiene
- **Exclusion**: Strictly ignore `.gitignore` and `.claudeignore` targets. Never index `.env`, `logs/`, or `data/` directories.
- **Prioritization**: Focus on high-value files: `.md` docs, core business logic, API/DB schemas, and complex utility functions.
