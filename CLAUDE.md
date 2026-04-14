# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Reeve** is an AI-powered vehicle manufacturer and model auto-classification system. A monorepo of three FastAPI microservices backed by MySQL, Qdrant (vector DB), Redis, and Ollama.

## Development Commands

### Running Services

```bash
# Mac (Apple Silicon) — Ollama/Trainer 네이티브 + 나머지 Docker
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.mac.yml up -d

# Linux/Windows (NVIDIA GPU) — 전체 Docker
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d
```

### Reindexing the Qdrant Knowledge Base

```bash
python3 .claude/index_qdrant.py --clear
```

### Deployment Packaging

```bash
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows]
```

## Architecture

Three microservices communicate over a shared Docker network:

| Service | Port | Purpose |
|---------|------|---------|
| `studio` | 8000 | Web UI, admin CRUD, image upload, vision pre-analysis |
| `identifier` | 8001 | ML pipeline: YOLO → EfficientNetV2-M → VLM fallback |
| `trainer` | 8002 | EfficientNet / VLM fine-tuning |

---

## Studio Service (`studio/`)

### 역할
- 이미지 업로드 → Vision API 분석 → 검수 → 학습 데이터 적재
- 제조사·모델·분석결과·학습데이터 CRUD (SQLAlchemy + MySQL)
- APScheduler로 오래된 분석 결과 자동 삭제 (기본 30일, `CLEANUP_HOUR=3`)

### API 엔드포인트
- `POST /api/analyze/vehicle` — 이미지 분석 (OpenAI/Gemini/Ollama Vision)
- `GET/POST /admin/manufacturers` — 제조사 CRUD
- `GET/POST /admin/vehicle-models` — 차량 모델 CRUD
- `GET /admin/analyzed-vehicles` — 분석 결과 목록/검수 큐
- `PATCH /admin/analyzed-vehicles/{id}/verify` — 검수 승인 → TrainingDataset 적재
- `POST /finetune/export-efficientnet` — EfficientNet 학습용 CSV export (스레드풀 실행)
- `POST /finetune/export` — VLM 학습용 ShareGPT JSON export
- `POST /finetune/train/start` — Trainer 학습 시작 프록시
- `GET /finetune/train/status` / `GET /finetune/train/raw-log` — 학습 상태 조회
- `GET /finetune/evaluate` — Before/After 정확도 평가
- `GET /health` — 헬스체크

### 주요 파일
- `studio/main.py` — 앱 진입점, 라이프사이클, cleanup 스케줄러
- `studio/api/analyze.py` — 차량 분석 API
- `studio/api/admin.py` — 기준데이터·검수 관리
- `studio/api/finetune.py` — export/학습/평가 API
- `studio/services/openai_vision.py` — OpenAI Vision 래퍼 (현재 모델: `gpt-5-mini`)
- `studio/services/matcher.py` — 퍼지 매칭 (DB 차종 매핑)
- `studio/models/` — SQLAlchemy 모델
- `studio/tasks/cleanup.py` — APScheduler 자동 정리

### 데이터 모델
| 모델 | 역할 |
|------|------|
| `Manufacturer` | 제조사 (id, code, korean_name, english_name, is_domestic) |
| `VehicleModel` | 차량 모델 (id, code, manufacturer_id, korean_name, english_name) |
| `AnalyzedVehicle` | 분석 결과 (image_path, raw_result, matched_manufacturer_id, is_verified, processing_stage, yolo_detections, selected_bbox) |
| `TrainingDataset` | 검증된 학습 이미지 (image_path unique, manufacturer_id, model_id, qdrant_id) |

### Studio 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `VISION_BACKEND` | openai | `openai` \| `ollama` |
| `OPENAI_MODEL` | gpt-5-mini | OpenAI Vision 모델 |
| `GEMINI_MODEL` | gemini-2.5-flash | Gemini 모델 (교차 검증용) |
| `STUDIO_VLM_MODEL` | qwen3-vl:8b | ollama 백엔드 VLM |
| `FUZZY_MATCH_THRESHOLD` | 80 | 모델명 퍼지 매칭 임계값 (0~100) |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | 30 | 분석 결과 보관 기간 (일) |
| `CLEANUP_HOUR` | 3 | 자동 정리 실행 시각 |

---

## Identifier Service (`identifier/`)

### 판별 모드 (IDENTIFIER_MODE)

| 모드 | 동작 | 특징 |
|------|------|------|
| `efficientnet` (기본) | EfficientNet 분류 → confidence 미달 시 VLM 폴백 | 빠름, 높은 정확도 |
| `visual_rag` | EfficientNet 임베딩 → Qdrant 후보 → VLM 최종 판별 | 최고 정확도 |
| `vlm_only` | YOLO 크롭 → VLM만 사용 | 느림 |
| `embedding_only` | EfficientNet 임베딩 + Qdrant 투표 (레거시) | 중간 |

### efficientnet 모드 파이프라인

```
이미지 입력
  → [YOLO26] 차량 탐지 → bbox 추출
  → [EfficientNetV2-M] 크롭 이미지 → 1280d 특징 → softmax 분류
  → classifier_confidence_threshold 판단
      ├─ threshold 이상: "identified" 반환
      └─ threshold 미만: [Qwen3-VL:8b] VLM 폴백
  → IdentificationResult 반환 (status, manufacturer, model, confidence, top_k_details)
```

### 분류기 신뢰도 임계값 (identifier/identifier.py:440-447)
```
CLASSIFIER_CONFIDENCE_THRESHOLD > 0 → 해당 값을 'identified' 임계값으로 사용
CLASSIFIER_CONFIDENCE_THRESHOLD = 0 (기본) → IDENTIFIER_CONFIDENCE_THRESHOLD (0.80) 폴백
CLASSIFIER_LOW_CONFIDENCE_THRESHOLD (기본 0.40) → 이 값 미만이면 VLM 폴백,
                                                   이상이면 low_confidence 반환
```

### API 엔드포인트
- `POST /identify` — 단건 동기 판별
- `POST /identify/batch` — 배치 동기 판별 (최대 100개, 100MB)
- `POST /async/identify` — 단건 비동기 판별 → task_id 반환
- `POST /async/identify/batch` — 배치 비동기 → task_id 반환
- `GET /async/result/{task_id}` — 비동기 결과 조회
- `POST /detect` — YOLO 차량 탐지만 수행
- `POST /admin/reload-efficientnet` — EfficientNet 모델 핫리로드
- `GET /health` — 헬스체크 (IDENTIFIER_MODE 포함)

### 주요 파일
- `identifier/identifier.py` — 핵심 판별 로직 (VehicleIdentifier 클래스)
- `identifier/efficientnet_classifier.py` — EfficientNetV2-M 래퍼 (분류 + 임베딩)
- `identifier/vlm_service.py` — Ollama VLM 서비스
- `identifier/tasks.py` — Celery 비동기 작업
- `identifier/config.py` — 전체 설정값

### Identifier 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `IDENTIFIER_MODE` | efficientnet | 판별 모드 |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | 0.0 | identified 임계값 (0이면 `IDENTIFIER_CONFIDENCE_THRESHOLD` 폴백) |
| `CLASSIFIER_LOW_CONFIDENCE_THRESHOLD` | 0.40 | VLM 폴백 여부 결정 임계값 |
| `IDENTIFIER_TOP_K` | 10 | Qdrant 검색 Top-K |
| `IDENTIFIER_CONFIDENCE_THRESHOLD` | 0.80 | 최종 판별 신뢰도 임계값 |
| `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD` | 0.3 | 투표 집중도 임계값 |
| `IDENTIFIER_YOLO_CONFIDENCE` | 0.25 | YOLO 탐지 신뢰도 |
| `VLM_MODEL_NAME` | qwen3-vl:8b | Ollama VLM 모델 |
| `VLM_TIMEOUT` | 30.0 | VLM 타임아웃 (초) |
| `EMBEDDING_DEVICE` | cpu | cuda \| cpu |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | true | ARM에서는 false로 override |

### Qdrant 컬렉션
- 컬렉션명: `training_images`
- 벡터 차원: 1280 (EfficientNetV2-M 특징)
- 유사도: Cosine
- payload: `image_path`, `manufacturer_id`, `model_id`, `manufacturer_korean`, `model_korean`

---

## Trainer Service (`trainer/`)

### 백엔드 선택 (TRAINER_BACKEND)
| 백엔드 | 플랫폼 | 용도 |
|--------|--------|------|
| `efficientnet` | 전체 (MPS/CUDA/CPU) | EfficientNetV2-M 이미지 분류 파인튜닝 |
| `mlx` | Mac Apple Silicon | VLM (Qwen3-VL) 파인튜닝 |
| `llamafactory` | Linux/Windows GPU | VLM (Qwen3-VL) 파인튜닝 |

### EfficientNet 학습 파이프라인
1. Studio `/finetune/export-efficientnet` → CSV 생성 (`data/finetune/train/chunk_*.csv`)
2. Trainer `POST /train/start` → 학습 스크립트 생성 후 nohup 백그라운드 실행
3. 학습 완료 → `data/models/efficientnet/efficientnetv2_m_finetuned.pth` 저장
4. Identifier `POST /admin/reload-efficientnet` 핫리로드

### 학습 스크립트 동작 (efficientnet_trainer.py)
- **모델**: `tf_efficientnetv2_m.in21k_ft_in1k` + Dropout(0.3) + Linear(1280, num_classes)
- **입력 해상도**: 480×480
- **Data Augmentation**: RandomResizedCrop + TrivialAugmentWide + RandomErasing (학습), Resize+CenterCrop (검증)
- **CutMix/MixUp**: 배치 레벨, `use_mixup` 파라미터로 활성화 (고사양 플랫폼 자동 활성)
- **손실 함수**: CrossEntropyLoss (label_smoothing=0.1, 클래스 가중치 sqrt 보정)
- **옵티마이저**: AdamW (freeze 구간: head만, unfreeze 구간: head + backbone 별도 LR)
- **스케줄러**: OneCycleLR (freeze/unfreeze 전환 시 재생성, Gradient Accumulation 반영)
- **Mixed Precision**: CUDA bf16(sm_80+)/fp16+GradScaler, MPS fp16 autocast, CPU fp32
- **channels_last**: CUDA/MPS에서 컨볼루션 메모리 레이아웃 최적화
- **torch.compile**: DGX Spark `max-autotune`, 일반 CUDA `reduce-overhead`
- **Gradient Accumulation**: `gradient_accumulation` 파라미터, effective batch size 통일 (기본 32~64)
- **EMA**: `use_ema` 파라미터, decay=0.999, 검증/저장 시 EMA 모델 사용
- **Early Stopping**: `early_stopping_patience` 파라미터 (기본 3 epoch)
- **Per-Class 정확도**: worst 5 클래스 추적, JSONL 로그에 `worst_classes` 필드 기록
- **Gradient clipping**: max_norm=1.0
- **Best model 저장**: val_acc 기준 (EMA 적용 시 EMA state_dict), 최종 모델에 복사
- **생성 파일 위치**: `logs/trainer/efficientnet/efficientnet_train.py` ← Studio hot-reload 감시 디렉토리 밖이어야 함 (Dockerfile: `--reload-dir /app/studio`)

### 하드웨어별 기본 파라미터
| 환경 | batch | grad_accum | eff_batch | workers | EMA | MixUp | precision |
|------|-------|------------|-----------|---------|-----|-------|-----------|
| DGX Spark (sm_120+/100GB+) | 64 | 1 | 64 | 16 | O | O | bf16 |
| High-end NVIDIA (20GB+) | 32 | 2 | 64 | 8 | O | O | fp16 |
| Mid NVIDIA (8~20GB) | 16 | 4 | 64 | 4 | X | X | fp16 |
| Low NVIDIA (<8GB) | 8 | 8 | 64 | 2 | X | X | fp16 |
| Apple Silicon (MPS) | 16 | 2 | 32 | 2 | O | X | mps fp16 |
| CPU | 4 | 8 | 32 | 0 | X | X | fp32 |

### API 엔드포인트
- `POST /train/start` — 학습 시작 (`learning_rate`, `num_epochs`, `batch_size`, `freeze_epochs`, `max_per_class`, `gradient_accumulation`, `use_ema`, `use_mixup`, `num_workers`, `early_stopping_patience`)
- `GET /train/status` — 진행 상태 (current_steps, total_steps, epoch, loss, val_acc)
- `POST /train/stop` — 학습 중지
- `GET /train/logs` — JSONL 로그 (tail)
- `GET /train/raw-log` — 원시 로그 (tail)
- `GET /hw-profile` — 하드웨어 감지 + 권장 파라미터
- `GET /health` — 헬스체크

---

## Configuration

`docker/.env.example` → `docker/.env` 복사 후 설정:
- `OPENAI_API_KEY` / `GEMINI_API_KEY` — 클라우드 Vision
- `MYSQL_PASSWORD` — DB 비밀번호
- `EMBEDDING_DEVICE` — `cuda` / `cpu`
- `IDENTIFIER_MODE` — 판별 모드
- `VISION_BACKEND` — `openai` / `ollama`
- `ANALYZED_VEHICLES_RETENTION_DAYS` — 분석 결과 보관 기간

---

## Key File Locations

| 파일 | 역할 |
|------|------|
| `studio/main.py` | Studio 진입점 |
| `identifier/main.py` | Identifier 진입점 |
| `trainer/main.py` | Trainer 진입점 |
| `identifier/identifier.py` | 핵심 판별 로직 |
| `identifier/efficientnet_classifier.py` | EfficientNet 래퍼 |
| `trainer/services/efficientnet_trainer.py` | EfficientNet 학습 스크립트 빌더 |
| `studio/api/finetune.py` | export/학습/평가 API (`_export_efficientnet_sync`는 스레드풀 실행, 별도 DB 세션 사용) |
| `studio/models/` | SQLAlchemy 모델 |
| `studio/services/openai_vision.py` | OpenAI Vision 래퍼 |
| `sql/` | DB 스키마 및 시드 데이터 |
| `docker/Dockerfile` | Studio 이미지 (`--reload-dir /app/studio`) |
| `docker/docker-compose.dev.yml` | 개발 오버라이드 (Studio 메모리 4G) |
| `docs/ASYNC_USAGE.md` | 비동기 API 사용 가이드 |

---

## Platform Notes

- **Mac**: Ollama + Trainer를 네이티브 실행, 나머지 Docker. `EMBEDDING_DEVICE=cpu`, `IDENTIFIER_ENABLE_TORCH_COMPILE=false`
- **Linux/Windows**: 전체 Docker, NVIDIA GPU 사용. `EMBEDDING_DEVICE=cuda`
- **Studio hot-reload**: `--reload-dir /app/studio`로 `logs/` 변경을 감시하지 않음 (Trainer 스크립트 생성 시 재시작 방지)
- **Dockerfile.identifier**: multi-arch — `linux/amd64`는 CUDA, `linux/arm64`는 CPU
- **Uvicorn worker count**: `identifier/start.sh`에서 CPU 코어 수 기준 자동 계산
- **export-efficientnet**: `run_in_executor`로 스레드풀 실행 + `SessionLocal()`로 독립 DB 세션 사용 (SQLAlchemy 스레드 안전성)
