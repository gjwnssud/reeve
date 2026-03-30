# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Reeve는 AI 기반 차량 제조사/모델 자동 식별 시스템으로, 세 개의 독립적인 FastAPI 서비스로 구성됩니다.

- **Studio (port 8000)** — 개발/관리 서비스. OpenAI Vision / Gemini Vision으로 차량 분석, MySQL로 구조화 데이터 저장, Qdrant에 학습 데이터 동기화.
- **Identifier (port 8001)** — 프로덕션 식별 서비스. MySQL 없음. CLIP 임베딩 + Qdrant 벡터 검색 + Qwen3-VL로 차량 식별. 동기/비동기(Celery) 지원.
- **Trainer (port 8002)** — 파인튜닝 서비스. `TRAINER_BACKEND=llamafactory` (Linux/Windows NVIDIA) 또는 `TRAINER_BACKEND=mlx` (Mac Apple Silicon 네이티브). Studio의 `/finetune/train/*` 호출을 수신.

## Commands

```bash
# 개발 환경 시작 - Linux/Windows (NVIDIA GPU)
cd docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d

# 개발 환경 시작 - Mac (네이티브 ollama + trainer, 나머지 Docker)
# .venv 가상환경 준비 (최초 1회)
python3 -m venv .venv
.venv/bin/pip install mlx-lm mlx-vlm fastapi "uvicorn[standard]" pydantic-settings pyyaml psutil httpx

ollama serve &                                                              # 네이티브 ollama
TRAINER_BACKEND=mlx .venv/bin/uvicorn trainer.main:app --port 8002 &      # 네이티브 MLX trainer
cd docker && docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml up -d

# 프로덕션 시작 (qdrant + identifier + redis + celery-worker + ollama + trainer)
cd docker && docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

# 로컬 실행 (가상환경 기준)
.venv/bin/uvicorn studio.main:app --reload --port 8000
.venv/bin/uvicorn identifier.main:app --reload --port 8001
.venv/bin/uvicorn trainer.main:app --reload --port 8002
celery -A identifier.celery_app worker --loglevel=info

# 테스트
pytest
pytest -k test_name
pytest --asyncio-mode=auto

# 배포 패키지 생성
./deploy/package.sh dev-linux    # Linux GPU 개발 패키지
./deploy/package.sh dev-windows  # Windows GPU 개발 패키지
./deploy/package.sh dev-mac      # Mac Apple Silicon 개발 패키지 (MLX)
./deploy/package.sh prod-linux   # Linux 운영 패키지 (Identifier 전용)
./deploy/package.sh all          # 전체 패키지
```

## Architecture

### 데이터 흐름

```
이미지 업로드 → YOLO 차량 감지 → BBox 선택 → Vision API 분석 (OpenAI/Gemini)
→ RapidFuzz 매칭 (manufacturers/vehicle_models DB) → 관리자 검토/승인
→ CLIP 임베딩 생성 → Qdrant 저장 → Identifier 서비스가 벡터 검색으로 차량 식별
```

### 식별 알고리즘 (`identifier/identifier.py`)

1. YOLO26으로 차량 감지 및 크롭
2. CLIP-ViT-B/32로 512d 임베딩 생성
3. Qdrant top-K 검색 + (manufacturer_id, model_id) 쌍으로 투표 집계
4. 신뢰도 판정: `identified` / `uncertain` / `unidentified`
5. `visual_rag` 모드: Qwen3-VL로 최종 재판정

**3가지 동작 모드** (`IDENTIFIER_MODE`): `clip_only` (기본) / `visual_rag` / `vlm_only`

**안전장치**: vote_concentration (승자 득표율 ≥ 30%), YOLO 미감지 시 `uncertain` 강제 하향

### 주요 설계 결정

- **Identifier는 MySQL-free.** 제조사/모델 이름은 Qdrant payload에 비정규화 저장 (`manufacturer_korean`, `manufacturer_english`, `model_korean`, `model_english`).
- **단일 Qdrant 컬렉션** (`training_images`, 512d). 추가 컬렉션 없음.
- **DB-First 업로드**: `POST /api/upload` → DB 레코드 생성 (stage: `uploaded`) → `POST /api/detect-vehicle` → `POST /api/analyze-vehicle-stream` (SSE). 파일 수신과 분석을 분리.
- **워커 자동 계산**: `workers = cpu_count // IDENTIFIER_TORCH_THREADS`. `.env`에 `IDENTIFIER_TORCH_THREADS`만 설정하면 `start.sh`가 계산.
- **파일 삭제 정책**: 레코드 삭제 시 crop 이미지 + 원본 업로드 파일 함께 삭제.
- **Vision 백엔드 추상화** (`studio/services/vision_backend.py`): OpenAI / Gemini / Ollama를 통합 인터페이스로 제공.
- **Trainer 서비스 분리** (`trainer/`): 파인튜닝 로직을 Studio에서 분리. `TRAINER_BACKEND=mlx` (Mac, mlx-lm 네이티브) 또는 `llamafactory` (Linux/Windows Docker). Studio는 HTTP 프록시로 호출.

### Docker Compose 구조

| 파일 | 용도 |
|------|------|
| `docker-compose.yml` | 프로덕션 베이스 (qdrant, identifier, redis, celery-worker, ollama, trainer) |
| `docker-compose.dev.yml` | 개발 오버라이드 (mysql, studio 추가, 소스 bind-mount) |
| `docker-compose.gpu.yml` | NVIDIA GPU 설정 |
| `docker-compose.mac.yml` | macOS 오버라이드 (ollama/trainer 비활성화 → 네이티브 실행, studio Docker로 복원) |

`.env` 파일 위치: `docker/.env`

### 비동기 처리 패턴

FastAPI → Redis 큐 → Celery Worker → 결과 Redis 저장 (24h TTL)

- `/async/identify` — 단일 이미지 비동기
- `/async/identify/batch` — 최대 100개 파일 / 100MB
- `/async/result/{task_id}` — 결과 폴링 (PENDING → STARTED → SUCCESS/FAILURE)

### Studio UI 라우팅

- `GET /` / `GET /analyze-ui` → `analyze_v2.html` (분석 메인)
- `GET /admin-ui` → `index.html` (기초DB관리 탭 + 학습데이터추출 탭)
- `GET /finetune-ui` → `finetune.html` (파인튜닝 관리)

### 자동 정리 스케줄러 (`studio/tasks/cleanup.py`)

매일 `CLEANUP_HOUR`시에 `is_verified=false`이고 `ANALYZED_VEHICLES_RETENTION_DAYS`일 초과된 레코드 + 이미지 자동 삭제.

## Database (MySQL 8.0)

4개 테이블: `manufacturers` → `vehicle_models` (1:N, cascade delete), `analyzed_vehicles` (양쪽 SET NULL on delete), `training_dataset` (Qdrant `qdrant_id`로 연결).

스키마: `sql/user_provided_ddl.sql`, 시드: `sql/user_provided_dml.sql` (Docker 초기화 자동 적용)

## Configuration

세 서비스 모두 Pydantic Settings로 `docker/.env` 로드.

주요 변수:

| 변수 | 서비스 | 설명 |
|------|--------|------|
| `IDENTIFIER_MODE` | identifier | `clip_only` / `visual_rag` / `vlm_only` |
| `IDENTIFIER_TOP_K` | identifier | Qdrant 검색 결과 수 (default 10) |
| `IDENTIFIER_VOTE_THRESHOLD` | identifier | 최소 득표 수 (default 3) |
| `IDENTIFIER_CONFIDENCE_THRESHOLD` | identifier | 최소 신뢰도 (default 0.80) |
| `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD` | identifier | 승자 최소 득표율 (default 0.3) |
| `VLM_MODEL_NAME` | identifier | Ollama 모델명 (default qwen3-vl:8b) |
| `FUZZY_MATCH_THRESHOLD` | studio | RapidFuzz 매칭 임계값 (default 80) |
| `CLEANUP_ENABLED` | studio | 자동 정리 활성화 (default true) |
| `EMBEDDING_DEVICE` | both | `cpu` 또는 `cuda` |
| `TRAINER_BACKEND` | trainer | `llamafactory` (Linux/Windows) / `mlx` (Mac 네이티브) |
| `TRAINER_URL` | studio | Trainer 서비스 URL (default http://localhost:8002) |
| `TRAINER_DATA_DIR` | trainer | 학습 데이터 디렉토리 (default data/finetune) |
| `TRAINER_OUTPUT_DIR` | trainer | 체크포인트 출력 디렉토리 (default output) |
| `OLLAMA_BASE_URL` | trainer | Ollama URL (default http://localhost:11434) |
| `IDENTIFIER_URL` | trainer | Identifier URL (default http://localhost:8001), 파인튜닝 완료 후 핫리로드 알림용 |
| `GGUF_CONVERTER_PATH` | trainer | llama.cpp의 convert_hf_to_gguf.py 절대 경로 (미설정 시 GGUF 자동변환 비활성) |

## Language

코드 주석과 프로젝트 문서는 한국어. UI 텍스트는 한국어. 변수명과 API 경로는 영어.

## MCP & Knowledge Base (Qdrant)

```bash
# 전체 재인덱싱
python3 .claude/index_qdrant.py --clear
```

- 검색 시 `limit` 3~5로 제한 (컨텍스트 오버플로우 방지)
- `.env`, `logs/`, `data/` 는 인덱싱 제외
