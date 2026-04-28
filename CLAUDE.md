# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Reeve** is an AI-powered vehicle manufacturer and model auto-classification system. A monorepo of three FastAPI microservices (+ React/Vite 프론트엔드 pnpm 워크스페이스) backed by MySQL, Redis, and Ollama. Qdrant 의존성 없음(v2.1에서 제거).

## Development Commands

### Running Services

```bash
# Mac (Apple Silicon) — Ollama/Trainer 네이티브 + 나머지 Docker
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.mac.yml up -d

# Linux/Windows (NVIDIA GPU) — 전체 Docker
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.gpu.yml up -d

# SSL overlay (자체 서명 인증서) — 위 명령어에 추가
# 인증서 생성: ./docker/gen-cert.sh <SERVER_IP>
# -f docker/docker-compose.ssl.yml 를 끝에 추가
```

### Deployment Packaging

```bash
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows]
```

## Architecture

Three microservices communicate over a shared Docker network. 두 개의 React SPA(`studio/static`, `identifier/static`)가 각 서비스의 `/static/`에 서빙됨.

| Service | Port | Purpose |
|---------|------|---------|
| `studio` | 8000 | Web UI, admin CRUD, image upload, vision pre-analysis |
| `identifier` | 8001 | ML pipeline: YOLO → EfficientNetV2-M (→ low_confidence, no VLM fallback) or vlm_only |
| `trainer` | 8002 | EfficientNet / VLM fine-tuning |
| `redis` | 6379 | Celery broker/backend (24h 결과 TTL) |
| `ollama` | 11434 | Qwen3-VL 로컬 VLM (vlm_only 또는 Studio `ollama` 백엔드에서 사용) |
| `mysql` | 3306 | 제조사·모델·분석 이력·학습 데이터 |

---

## Studio Service (`studio/`)

### 역할
- 이미지 업로드 → Vision API 분석 → 검수 → 학습 데이터 적재
- 제조사·모델·분석결과·학습데이터 CRUD (SQLAlchemy + MySQL)
- APScheduler로 오래된 분석 결과 자동 삭제 (기본 30일, `CLEANUP_HOUR=3`)

### API 엔드포인트
- `POST /api/analyze/vehicle` — 이미지 분석 (OpenAI/Gemini/Ollama Vision)
- `POST /api/detect-vehicle` — YOLO 탐지만 수행
- `POST /api/analyze-vehicle-stream` — SSE 스트리밍 분석 (단계별 진행)
- `GET/POST /admin/manufacturers` — 제조사 CRUD
- `GET/POST /admin/vehicle-models` — 차량 모델 CRUD
- `GET /admin/analyzed-vehicles` — 분석 결과 목록 (status/review_status/page/sort 필터)
- `GET /admin/analyzed-vehicles-counts` — 탭별 카운트 (pending/on_hold/approved/rejected/uploaded/yolo_failed)
- `GET /admin/review-queue` — 검수 큐 (pending 항목)
- `PATCH /admin/review/{id}` — 분석 결과 수정 (approved 상태이면 TrainingDataset도 즉시 upsert)
- `POST /admin/review/{id}` — 검수 승인 → TrainingDataset 적재 + `review_status='approved'`
- `POST /admin/review/{id}/hold` — 검수 보류 → TrainingDataset 제거 + `review_status='on_hold'`
- `POST /admin/review/{id}/reject` — 검수 반려 → TrainingDataset 제거 + `review_status='rejected'`
- `POST /admin/review/{id}/reopen` — 검수 재개 → `review_status='pending'` (approved였으면 TrainingDataset도 제거)
- `POST /admin/review/batch-action` — 일괄 검수 액션 (SSE 스트리밍, approve/hold/reject)
- `POST /admin/review/batch-save-all` — pending 전체 일괄 승인 (SSE 스트리밍)
- `DELETE /admin/review-delete-all` — 미검수(pending+on_hold+rejected) 전체 삭제
- `DELETE /admin/review/{id}` — 단건 삭제
- `POST /admin/analyze/{id}` — 단건 재분석 (Vision API 재호출 후 결과 갱신)
- `POST /admin/analyze-batch` — 배치 분석
- `GET /admin/reload-efficientnet` — Identifier EfficientNet 핫리로드 프록시
- `GET /admin/db-stats` — DB 통계 (제조사·모델·학습 데이터 수)
- `POST /admin/cleanup-now` — 오래된 분석 결과 즉시 정리
- `POST /finetune/export-efficientnet` — EfficientNet 학습용 CSV export (스레드풀 실행)
- `POST /finetune/export` — VLM 학습용 ShareGPT JSON export
- `POST /finetune/train/start` — Trainer 학습 시작 프록시
- `GET /finetune/train/status` / `GET /finetune/train/raw-log` / `GET /finetune/train/logs` — 학습 상태·로그 조회
- `GET /finetune/evaluate` — Before/After 정확도 평가
- `GET /finetune/hw-profile` — 하드웨어 권장 파라미터
- `GET /api/server-files` — 서버 디렉토리 이미지 파일 목록 (`SERVER_WATCH_BASE_DIR` 하위만 허용)
- `POST /api/server-files/register` — 서버 경로 파일을 `data/uploads/`로 복사 후 AnalyzedVehicle 등록 (`/api/upload`와 동일 응답)
- `GET /api/server-files/image` — 서버 경로 이미지 파일 제공 (프리뷰용)
- `GET /health` — 헬스체크
- SPA: `/` → `/static/` 리다이렉트, `/{any}` → `static/index.html` catch-all (모든 API 라우터 등록 후 마운트)

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
| `AnalyzedVehicle` | 분석 결과 (image_path, raw_result, matched_manufacturer_id, is_verified, review_status, review_reason, verified_by, verified_at, notes, processing_stage, yolo_detections, selected_bbox, source, client_uuid) |
| `TrainingDataset` | 검증된 학습 이미지 (image_path unique, manufacturer_id, model_id) |

**`AnalyzedVehicle` 검수 상태 (`review_status`)**
| 값 | 의미 | `is_verified` |
|----|------|---------------|
| `pending` | 검수 대기 (기본값) | false |
| `approved` | 검수완료 — TrainingDataset 적재됨 | true |
| `on_hold` | 보류 — 추가 검토 필요 | false |
| `rejected` | 반려 — 부적합 판정 | false |

`is_verified`는 `approved` 여부를 빠르게 판단하는 Boolean 인덱스 역할로 `review_status`와 병행 유지됨 (export/일괄삭제 쿼리에서 활용).

**`processing_stage` 흐름**
`uploaded` → `yolo_detected` → `analysis_complete`

### Studio 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `VISION_BACKEND` | openai | `openai` \| `ollama` |
| `OPENAI_MODEL` | gpt-5.4-mini | OpenAI Vision 모델 |
| `GEMINI_MODEL` | gemini-2.5-flash | Gemini 모델 (교차 검증용) |
| `STUDIO_VLM_MODEL` | qwen3-vl:8b | ollama 백엔드 VLM |
| `FUZZY_MATCH_THRESHOLD` | 80 | 모델명 퍼지 매칭 임계값 (0~100) |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | 30 | 분석 결과 보관 기간 (일) |
| `CLEANUP_HOUR` | 3 | 자동 정리 실행 시각 |
| `SERVER_WATCH_BASE_DIR` | /mnt/ | 서버 폴더 감시 허용 기본 경로 (이 경로 하위만 접근 가능) |

---

## Identifier Service (`identifier/`)

### 판별 모드 (IDENTIFIER_MODE)

| 모드 | 동작 | 특징 |
|------|------|------|
| `efficientnet` (기본) | EfficientNet 분류 → confidence 미달 시 low_confidence (VLM 폴백 없음) | 빠름, 높은 정확도 |
| `vlm_only` | YOLO 크롭 → VLM만 사용, 실패 시 low_confidence | 느림, 파인튜닝 데이터 부족 시 유용 |

### efficientnet 모드 파이프라인

```
이미지 입력
  → [YOLO26] 차량 탐지 → bbox 추출
  → [EfficientNetV2-M] 크롭 이미지 → 1280d 특징 → softmax 분류
  → classifier_confidence_threshold 판단
      ├─ threshold 이상: "identified" 반환
      └─ threshold 미만: "low_confidence" 반환 (VLM 폴백 없음)
  → IdentificationResult 반환 (status, manufacturer, model, confidence)
```

### 분류기 신뢰도 임계값
```
confidence ≥ CLASSIFIER_CONFIDENCE_THRESHOLD (기본 0.80) → identified
그 미만 → low_confidence 반환

CLASSIFIER_LOW_CONFIDENCE_THRESHOLD (기본 0.40): 로그 메시지 구분용
  ≥ 0.40: "분류기 신뢰도 중간" 로그
  < 0.40: "분류기 신뢰도 부족" 로그
  (실제 반환 status는 동일하게 low_confidence)
```

### API 엔드포인트
- `POST /identify` — 단건 동기 판별
- `POST /identify/stream` — SSE 스트리밍 판별 (단계별 진행: detect → classify → done)
- `POST /identify/batch` — 배치 동기 판별 (최대 100개, 100MB)
- `POST /async/identify` — 단건 비동기 판별 → task_id 반환
- `POST /async/identify/batch` — 배치 비동기 → task_id 반환
- `GET /async/result/{task_id}` — 비동기 결과 조회
- `POST /detect` — YOLO 차량 탐지만 수행
- `POST /admin/reload-efficientnet` — EfficientNet 모델 핫리로드
- `POST /admin/reload-vlm` — VLM 모델 핫리로드 (`vlm_only` 모드)
- `GET /health` — 헬스체크 (IDENTIFIER_MODE 포함)
- SPA: `/` → `index.html`, `/{any}` → `static/index.html` catch-all (API 라우터 등록 이후)

### 주요 파일
- `identifier/identifier.py` — 핵심 판별 로직 (VehicleIdentifier 클래스)
- `identifier/efficientnet_classifier.py` — EfficientNetV2-M 래퍼 (분류 + 임베딩)
- `identifier/vlm_service.py` — Ollama VLM 서비스 (`vlm_only` 모드 전용)
- `identifier/tasks.py` — Celery 비동기 작업
- `identifier/config.py` — 전체 설정값

### Identifier 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `IDENTIFIER_MODE` | efficientnet | 판별 모드 (`efficientnet` \| `vlm_only`) |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | 0.80 | `identified` 판정 최소 신뢰도 |
| `CLASSIFIER_LOW_CONFIDENCE_THRESHOLD` | 0.40 | 로그 tier 구분용 (실제 분기에 영향 없음) |
| `IDENTIFIER_YOLO_CONFIDENCE` | 0.25 | YOLO 탐지 신뢰도 |
| `VLM_MODEL_NAME` | qwen3-vl:8b | Ollama VLM 모델 (`vlm_only` 모드에서 사용) |
| `VLM_TIMEOUT` | 30.0 | VLM 타임아웃 (초) |
| `EMBEDDING_DEVICE` | cpu | cuda \| cpu |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | true | ARM에서는 false로 override |

---

## Trainer Service (`trainer/`)

### 백엔드 선택 (TRAINER_BACKEND)
| 백엔드 | 플랫폼 | 용도 |
|--------|--------|------|
| `efficientnet` | 전체 (Docker: Linux/Windows, CUDA/CPU) | EfficientNetV2-M 이미지 분류 파인튜닝 |
| `mlx` | Mac Apple Silicon (네이티브) | VLM (Qwen3-VL) 파인튜닝 |

> `llamafactory` 백엔드 제거 — arm64 미지원 + efficientnet으로 통합

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
- `GET /train/runs` — 학습 이력 목록 (run_id, start_time, val_acc, num_classes …)
- `GET /train/runs/{run_id}` — 학습 이력 단건 상세 (epoch별 loss·val_acc)
- `GET /train/runs/{run_id}/class-history` — 클래스별 정확도 추이
- `DELETE /train/runs/{run_id}` — 학습 이력 삭제
- `GET /train/deploy-config` — 배포 대상·경로 설정 조회
- `POST /train/export` — 학습 결과(Checkpoint/ONNX 등) export
- `GET /model-info` — 현재 모델/백엔드 정보
- `GET /deploy/cmd` — Identifier 측 배포 명령 힌트
- `POST /deploy/ollama` — VLM 백엔드일 때 Ollama 모델 배포
- `GET /hw-profile` — 하드웨어 감지 + 권장 파라미터
- `GET /health` — 헬스체크

---

## Frontend (`frontend/`)

pnpm 워크스페이스 모노레포 (Node ≥ 20, pnpm 9.15.0). 두 개의 React+Vite SPA가 각 백엔드의 `/static/`으로 빌드된다.

### 구조
```
frontend/
├── apps/
│   ├── studio/         # @reeve/studio — Vite dev: 5173, build → /static/ (Docker: /app/static/)
│   └── identifier/     # @reeve/identifier — Vite dev: 5174, build → /static/ (Docker: /app/static/)
├── packages/
│   ├── shared/         # API 타입(openapi-typescript 생성), 공용 훅·유틸
│   ├── ui/             # shadcn/ui 기반 공통 UI 컴포넌트
│   └── config/         # eslint/tsconfig/tailwind 공통 설정
└── scripts/gen-types.ts  # FastAPI OpenAPI → TypeScript 타입 생성
```

### 스크립트 (frontend/ 루트에서)
| 명령 | 설명 |
|------|------|
| `pnpm dev:studio` | Studio SPA dev server (5173, `STUDIO_BACKEND_URL` → 기본 `http://studio:8000`) |
| `pnpm dev:identifier` | Identifier SPA dev server (5174, `IDENTIFIER_BACKEND_URL`) |
| `pnpm build:studio` / `pnpm build:identifier` / `pnpm build:all` | 정적 산출물 빌드 |
| `pnpm gen:types` | 백엔드 OpenAPI로 타입 재생성 (PR에서 `gen:types:check`로 drift 검증) |
| `pnpm typecheck` / `pnpm lint` / `pnpm format` | 전 워크스페이스 일괄 실행 |

### 스택
- React 18 + React Router + TypeScript (strict) + Vite (SWC)
- TanStack Query / TanStack Table, Zustand 상태 관리
- Tailwind + shadcn/ui
- Vite `base: "/static/"`, 빌드 산출물은 각 서비스의 `/app/static/`에 위치
- **SPA 라우팅**: `StaticFiles` 마운트 대신 커스텀 `GET /static/{path}` 라우트 — 파일이 있으면 파일 반환, 없으면 `index.html` 반환. URL 직접 진입(새로고침) 정상 동작
- **FolderTab 배치 처리**: 업로드 세마포어(50) / 분석 세마포어(8) 분리. 업로드 완료 즉시 원본 파일 삭제(`readwrite` 권한), AbortController로 중단 시 진행 중 작업 즉시 종료. 성공 이미지는 학습 데이터 자동 승인 후 UI에서 제거
- **ServerFolderTab (서버 폴더 감시)**: 3초 폴링으로 서버 디렉토리(`/mnt/nas/yyMMdd` 형태)의 신규 이미지 감지. 발견된 파일은 `data/uploads/`로 복사 후 기존 detect → analyze stream → save 파이프라인 그대로 실행. 원본 NAS 파일 삭제 없음. 경로 접근은 `SERVER_WATCH_BASE_DIR` 하위로 제한. 처리 통계(전체·감지·감지 실패·분석 완료·분석 오류)는 Zustand store의 `serverStats`로 관리되며 localStorage(`reeve_server_stats_${uuid}`)에 지속 저장 — 새로고침 후에도 유지
- **폴더 감시 이탈 경고**: 탭 전환(AnalyzePage) 및 사이드바 메뉴 클릭(StudioLayout) 시 confirm 다이얼로그, `folderWatchRunning` 상태는 Zustand store로 공유 (로컬 폴더·서버 폴더 모두 적용)
- **Identifier BatchTab**: IntersectionObserver 기반 lazy 썸네일(32K 이미지 대응), 행 클릭 시 상세 다이얼로그
- **학습 이력 대시보드** (`/static/runs`): 학습 run 목록·상세·클래스 정확도 추이 비교. RunListTable / RunDetailView / RunCompareView / ClassTrackingView 컴포넌트로 구성. Trainer `GET /train/runs` API 연동

---

## Configuration

`docker/.env.example` → `docker/.env` 복사 후 설정:
- `OPENAI_API_KEY` / `GEMINI_API_KEY` — 클라우드 Vision
- `MYSQL_PASSWORD` — DB 비밀번호
- `EMBEDDING_DEVICE` — `cuda` (Linux/Windows) / `cpu` (Mac)
- `IDENTIFIER_MODE` — 판별 모드 (`efficientnet` / `vlm_only`)
- `VISION_BACKEND` — `openai` / `ollama`
- `ANALYZED_VEHICLES_RETENTION_DAYS` — 분석 결과 보관 기간
- `MAX_UPLOAD_SIZE` — 단일 이미지 최대 크기 (바이트, 기본 5MB)
- `ALLOWED_EXTENSIONS` — 허용 확장자 (기본 `jpg,jpeg,png,webp`)

**컨테이너 메모리 한도** (기본값, `.env`에서 재정의 가능):

| 변수 | 기본값 |
|------|--------|
| `STUDIO_MEMORY_LIMIT` | `4G` |
| `IDENTIFIER_MEMORY_LIMIT` | `4G` |
| `TRAINER_MEMORY_LIMIT` | `12G` |
| `MYSQL_MEMORY_LIMIT` | `2G` |
| `OLLAMA_MEMORY_LIMIT` | `8G` |
| `CELERY_MEMORY_LIMIT` | `4G` |
| `REDIS_MEMORY_LIMIT` | `512M` |

> DGX Spark 등 고성능 GPU 환경에서는 `TRAINER_MEMORY_LIMIT=50G` 이상 설정 필요 (기본 12G로는 unfreeze 후 OOM Kill 발생 가능).

**제거된 설정 (Qdrant 제거로 불필요):**
`QDRANT_HOST`, `QDRANT_PORT`, `IDENTIFIER_TOP_K`, `IDENTIFIER_MIN_SIMILARITY`, `IDENTIFIER_VOTE_THRESHOLD`, `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD`, `VLM_FALLBACK_TO_EMBEDDING`

---

## Key File Locations

| 파일 | 역할 |
|------|------|
| `studio/main.py` | Studio 진입점 |
| `identifier/main.py` | Identifier 진입점 |
| `trainer/main.py` | Trainer 진입점 |
| `identifier/identifier.py` | 핵심 판별 로직 |
| `identifier/efficientnet_classifier.py` | EfficientNet 래퍼 |
| `trainer/api/train.py` | Trainer API 라우터 (학습·이력·배포·hw-profile) |
| `trainer/services/efficientnet_trainer.py` | EfficientNet 학습 스크립트 빌더 |
| `studio/api/finetune.py` | export/학습/평가 API (`_export_efficientnet_sync`는 스레드풀 실행, 별도 DB 세션 사용) |
| `studio/models/` | SQLAlchemy 모델 |
| `studio/services/openai_vision.py` | OpenAI Vision 래퍼 |
| `sql/` | DB 스키마 및 시드 데이터 |
| `docker/Dockerfile` | Studio 이미지 (`--reload-dir /app/studio`) |
| `docker/docker-compose.dev.yml` | 개발 오버라이드 (소스 바인드 마운트, hot reload) |
| `docker/docker-compose.gpu.yml` | NVIDIA GPU 리소스 예약 overlay (Linux/Windows에서 추가) |
| `docker/docker-compose.ssl.yml` | SSL 자체 서명 인증서 overlay (`gen-cert.sh`로 인증서 생성 후 적용) |
| `docs/ASYNC_USAGE.md` | 비동기 API 사용 가이드 |
| `frontend/apps/studio/` | Studio React SPA (Vite `base=/static/`, 빌드 → `/static/` → Docker `/app/static/`) |
| `frontend/apps/identifier/` | Identifier React SPA (Vite `base=/static/`, 빌드 → `/static/` → Docker `/app/static/`) |
| `frontend/packages/shared/src/api-types/` | OpenAPI로 자동 생성되는 API 타입 (수정 금지) |
| `frontend/scripts/gen-types.ts` | FastAPI OpenAPI → TypeScript 타입 생성 스크립트 |

---

## Platform Notes

- **Mac**: Ollama + Trainer를 네이티브 실행, 나머지 Docker. `EMBEDDING_DEVICE=cpu`, `IDENTIFIER_ENABLE_TORCH_COMPILE=false`
- **Linux/Windows**: 전체 Docker, NVIDIA GPU 사용. `EMBEDDING_DEVICE=cuda`
- **Studio hot-reload**: `--reload-dir /app/studio`로 `logs/` 변경을 감시하지 않음 (Trainer 스크립트 생성 시 재시작 방지)
- **Dockerfile.identifier**: Linux/Windows(NVIDIA GPU) 전용. `nvcr.io/nvidia/pytorch:25.03-py3` 기반으로 amd64(x86)·arm64(GB10) 모두 CUDA 지원
- **Dockerfile.identifier.mac**: Mac Apple Silicon 전용. `python:3.12-slim` + CPU torch. `docker-compose.mac.yml`에서 자동 선택됨
- **Uvicorn worker count**: `identifier/start.sh`에서 CPU 코어 수 기준 자동 계산
- **export-efficientnet**: `run_in_executor`로 스레드풀 실행 + `SessionLocal()`로 독립 DB 세션 사용 (SQLAlchemy 스레드 안전성)
- **정적 파일 경로**: Vite 빌드 결과가 `/static/`(프로젝트 루트)으로 출력되고 Docker `COPY --from=frontend-builder /workspace/static/ ./static/`으로 `/app/static/`에 복사됨. 개발 환경 바인드 마운트(`../studio:/app/studio`)와 겹치지 않아 익명 볼륨 불필요
- **MySQL lower_case_table_names**: `docker-compose.dev.yml`에 `--lower-case-table-names=1` 적용됨. 플랫폼 간(Mac↔Linux) 데이터 디렉터리 이동 시 기존 데이터 초기화 필요(값 변경은 데이터 재초기화 필수)
- **호스트 포트 동적 할당**: compose 파일의 호스트 포트는 모두 `${VAR:-default}` 패턴 사용. `.env`에서 `STUDIO_PORT`, `IDENTIFIER_PORT`, `TRAINER_PORT`, `OLLAMA_PORT`, `MYSQL_PORT`, `REDIS_PORT` 재정의 가능
- **IDENTIFIER_URL**: Studio 컨테이너에서 `/finetune/evaluate` 호출 시 `http://identifier:8001` 필요. `docker-compose.dev.yml` Studio service에 명시적으로 설정되어 있음 (`.env`의 `localhost:8001`이 덮어쓰지 않도록)
