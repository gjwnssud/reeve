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

# Vite dev server (선택적) — --profile vite 추가 또는 호스트에서 직접 실행
# 호스트 직접 실행 (frontend/ 루트에서):
pnpm dev:studio      # 5173
pnpm dev:identifier  # 5174
```

### Deployment Packaging

```bash
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows|all]
```

## Architecture

세 개의 마이크로서비스가 공유 Docker 네트워크로 통신. 두 개의 React SPA(`studio/static`, `identifier/static`)가 각 서비스의 `/static/`에 서빙됨.

| Service | Port | Purpose |
|---------|------|---------|
| `studio` | 8000 | Web UI, 관리 CRUD, 이미지 업로드, Vision 사전 분석 |
| `identifier` | 8001 | ML 파이프라인: YOLO → EfficientNetV2-M (또는 vlm_only) |
| `trainer` | 8002 | EfficientNet / VLM 파인튜닝 |
| `redis` | 6379 | Celery broker/backend (24h 결과 TTL) |
| `ollama` | 11434 | Qwen3-VL 로컬 VLM |
| `mysql` | 3306 | 제조사·모델·분석 이력·학습 데이터 |

---

## Studio Service (`studio/`)

### 역할
- DB-First 업로드: 파일 선택 즉시 `AnalyzedVehicle` 레코드 생성 → YOLO 감지 → SSE 스트리밍 분석 → 검수 → 학습 데이터 적재
- 제조사·모델·분석결과·학습데이터 CRUD (SQLAlchemy + MySQL)
- Vision 백엔드 추상화: OpenAI / Ollama / 교차 검증(OpenAI+Gemini) / 자체 추론 API
- APScheduler로 오래된 분석 결과 자동 삭제 (기본 30일, `CLEANUP_HOUR=3`)

### Vision 백엔드 모드

| 모드 | 동작 | 조건 |
|------|------|------|
| `openai` (단독) | OpenAI Vision API만 사용 | `OPENAI_API_KEY`만 설정 |
| `openai` (교차 검증) | OpenAI + Gemini 병렬 호출 → 두 결과 일치 시 성공 | `OPENAI_API_KEY` + `GEMINI_API_KEY` 모두 설정 |
| `ollama` | Qwen3-VL Ollama 로컬 VLM | `VISION_BACKEND=ollama` |
| `local_inference` | 자체 추론 API (`POST /infer`) — YOLO+분류 통합 | `VISION_BACKEND=local_inference` |

> `local_inference` 모드: 자체 API가 YOLO+분류를 모두 수행하므로 Studio는 별도 YOLO crop을 돌리지 않고 원본 이미지를 그대로 전달한다. 응답의 bbox를 `selected_bbox`로 사용. 제조사·모델은 한글명으로 반환되며 matcher 자동 삽입을 통해 DB에 저장됨.

### API 엔드포인트

**분석 (`/api/`)**
- `GET /api/config` — 프론트엔드 런타임 설정 조회 (`vision_backend`)
- `POST /api/upload` — 파일 즉시 업로드 → `AnalyzedVehicle` 레코드 생성 (DB-First)
- `POST /api/detect-vehicle` — YOLO 탐지만 수행 (`file` 또는 `analyzed_id`)
- `POST /api/analyze-vehicle-stream` — SSE 스트리밍 분석 (`analyzed_id` + `bbox`)
- `GET /api/pending-records` — 레코드 페이지네이션 (`source`, `client_uuid`, `failure_only` 필터)
- `GET /api/analyze-feed` — 실시간 업데이트 피드 (SSE, 3초 폴링)
- `GET /api/server-files` — 서버 디렉토리 이미지 목록 (`SERVER_WATCH_BASE_DIR` 하위만)
- `POST /api/server-files/register` — 서버 파일 복사 → `AnalyzedVehicle` 등록
- `GET /api/server-files/image` — 서버 파일 프리뷰 (보안: base_dir 하위만 허용)

**관리 (`/admin/`)**
- `GET/POST /admin/manufacturers` — 제조사 CRUD (탭 필터 지원)
- `GET/POST /admin/vehicle-models` — 차량 모델 CRUD (탭 필터 지원)
- `GET /admin/analyzed-vehicles` — 분석 결과 목록 (`status/review_status/manufacturer_id/model_id/min_confidence/max_confidence/sort`)
- `GET /admin/analyzed-vehicles-counts` — 탭별 카운트 + 신뢰도 통계
- `GET /admin/review-queue` — 검수 큐 (pending)
- `PATCH /admin/review/{id}` — 분석 결과 수정 (approved 상태면 TrainingDataset 즉시 upsert)
- `POST /admin/review/{id}` — 검수 승인 → TrainingDataset 적재 + `review_status='approved'`
- `POST /admin/review/{id}/hold` — 보류 → TrainingDataset 제거
- `POST /admin/review/{id}/reject` — 반려 → TrainingDataset 제거
- `POST /admin/review/{id}/reopen` — 재개 → `review_status='pending'`
- `POST /admin/review/batch-action` — 일괄 액션 (SSE, approve/hold/reject)
- `POST /admin/review/batch-save-all` — pending 전체 일괄 승인 (SSE)
- `DELETE /admin/review-delete-all` — 미검수(pending+on_hold+rejected) 전체 삭제
- `DELETE /admin/review/{id}` — 단건 삭제
- `POST /admin/analyze/{id}` — 단건 재분석
- `GET /admin/db-stats` — DB 통계
- `POST /admin/cleanup-now` — 오래된 분석 결과 즉시 정리
- `POST /admin/reload-efficientnet` — Identifier EfficientNet 핫리로드 프록시

**파인튜닝 (`/finetune/`)**
- `GET /finetune/mode` — Trainer 백엔드 모드 조회
- `GET /finetune/hw-profile` — 하드웨어 권장 파라미터
- `GET /finetune/freeze-epochs` — freeze epoch 권장값
- `GET /finetune/stats` — 학습 데이터 통계
- `GET /finetune/export/preview` — export 미리보기
- `POST /finetune/export` — VLM 학습용 ShareGPT JSON export
- `POST /finetune/export-efficientnet` — EfficientNet CSV export (스레드풀 실행)
- `GET /finetune/deploy/cmd` — 배포 커맨드 힌트
- `POST /finetune/train/start` — 학습 시작 프록시
- `GET /finetune/train/status` / `raw-log` / `logs` — 학습 상태·로그
- `GET /finetune/train/deploy-config` — 배포 설정
- `GET /finetune/train/runs` / `runs/{run_id}` / `runs/{run_id}/class-history` — 학습 이력
- `DELETE /finetune/train/runs/{run_id}` — 학습 이력 삭제
- `POST /finetune/train/export` — 체크포인트 export
- `GET /finetune/evaluate` — Before/After 정확도 평가

- `GET /health` — 헬스체크
- SPA: `/` → `/static/` 리다이렉트, `/static/{path}` → 파일 반환 or `index.html` (path traversal 방지)

### 주요 파일
- `studio/main.py` — 앱 진입점, 라이프사이클, cleanup 스케줄러, SPA 라우팅
- `studio/config.py` — pydantic-settings 기반 전역 설정
- `studio/api/analyze.py` — 업로드·감지·SSE 분석·서버폴더 엔드포인트
- `studio/api/admin.py` — 기준데이터·검수 관리
- `studio/api/finetune.py` — export/학습/평가 API (`export-efficientnet`은 `run_in_executor` + 독립 DB 세션)
- `studio/services/vision_backend.py` — Vision 백엔드 팩토리 (`DualVisionService` 포함)
- `studio/services/openai_vision.py` — OpenAI Vision 래퍼 (TokenBucket rate limiter 내장)
- `studio/services/gemini_vision.py` — Gemini Vision 래퍼 (교차 검증용)
- `studio/services/local_inference_vision.py` — 자체 추론 API 래퍼
- `studio/services/ollama_vision.py` — Ollama VLM 래퍼
- `studio/services/matcher.py` — 퍼지 매칭 (DB 차종 매핑, `auto_insert=True`)
- `studio/services/vehicle_detector.py` — YOLO26 감지 래퍼
- `studio/services/crop_utils.py` — 이미지 크롭 유틸
- `studio/models/` — SQLAlchemy 모델
- `studio/tasks/cleanup.py` — APScheduler 자동 정리

### 데이터 모델
| 모델 | 역할 |
|------|------|
| `Manufacturer` | 제조사 (id, code, korean_name, english_name, is_domestic) |
| `VehicleModel` | 차량 모델 (id, code, manufacturer_id, korean_name, english_name) |
| `AnalyzedVehicle` | 분석 결과 (image_path, original_image_path, raw_result, manufacturer, model, matched_manufacturer_id, matched_model_id, confidence_score, is_verified, review_status, review_reason, verified_by, verified_at, notes, processing_stage, yolo_detections, selected_bbox, source, client_uuid) |
| `TrainingDataset` | 검증된 학습 이미지 (image_path unique, manufacturer_id, model_id) |

**`AnalyzedVehicle` 검수 상태 (`review_status`)**
| 값 | 의미 | `is_verified` |
|----|------|---------------|
| `pending` | 검수 대기 (기본값) | false |
| `approved` | 검수완료 — TrainingDataset 적재됨 | true |
| `on_hold` | 보류 — 추가 검토 필요 | false |
| `rejected` | 반려 — 부적합 판정 | false |

`is_verified`는 `approved` 여부를 빠르게 판단하는 Boolean 인덱스 역할로 `review_status`와 병행 유지됨.

**`processing_stage` 흐름**
```
uploaded → yolo_detected → analysis_complete
               ↘ no_vehicle  (탐지 실패: vehicles=[] 또는 local_inference unknown)
```

`yolo_failed` 탭 조건: `processing_stage == 'no_vehicle'` OR (`processing_stage == 'yolo_detected'` AND `yolo_detections`가 없거나 빈 배열)

### Studio 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `VISION_BACKEND` | `openai` | `openai` \| `ollama` \| `local_inference` |
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI Vision 모델 |
| `OPENAI_RPM` | `500` | OpenAI 분당 요청 수 (Tier 1 기준) |
| `OPENAI_TPM` | `500000` | OpenAI 분당 토큰 수 (Tier 1 기준) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 교차 검증 모델 |
| `STUDIO_VLM_MODEL` | `qwen3-vl:8b` | Ollama 백엔드 VLM 모델 |
| `STUDIO_VLM_TIMEOUT` | `60` | Ollama VLM 타임아웃 (초) |
| `LOCAL_INFERENCE_URL` | `http://1.214.219.58:8100` | 자체 추론 API base URL |
| `LOCAL_INFERENCE_TIMEOUT` | `30` | 자체 추론 API 타임아웃 (초) |
| `FUZZY_MATCH_THRESHOLD` | `80` | 퍼지 매칭 임계값 (0~100) |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | `30` | 분석 결과 보관 기간 (일) |
| `CLEANUP_HOUR` | `3` | 자동 정리 실행 시각 |
| `SERVER_WATCH_BASE_DIR` | `/mnt/` | 서버 폴더 감시 허용 기본 경로 |

---

## Identifier Service (`identifier/`)

### 판별 모드 (IDENTIFIER_MODE)

| 모드 | 동작 | 특징 |
|------|------|------|
| `efficientnet` (기본) | EfficientNet 분류 → confidence 미달 시 `low_confidence` (VLM 폴백 없음) | 빠름, 높은 정확도 |
| `vlm_only` | YOLO 크롭 → VLM만 사용, 실패 시 `low_confidence` | 느림, 파인튜닝 데이터 부족 시 유용 |

### efficientnet 모드 파이프라인

```
이미지 입력
  → [YOLO26m] 차량 탐지 → bbox 추출
  → [EfficientNetV2-M] 크롭 이미지 → softmax 분류
  → CLASSIFIER_CONFIDENCE_THRESHOLD 판단
      ├─ ≥ threshold (기본 0.80): "identified" 반환
      └─ < threshold: "low_confidence" 반환 (VLM 폴백 없음)
  → IdentificationResult 반환 (status, manufacturer, model, confidence)
```

### 분류기 신뢰도 임계값
```
confidence ≥ CLASSIFIER_CONFIDENCE_THRESHOLD (기본 0.80) → identified
그 미만 → low_confidence

CLASSIFIER_LOW_CONFIDENCE_THRESHOLD (기본 0.40): 로그 메시지 구분용
  ≥ 0.40: "분류기 신뢰도 중간"
  < 0.40: "분류기 신뢰도 부족"
  (실제 반환 status는 동일하게 low_confidence)
```

### API 엔드포인트
- `POST /identify` — 단건 동기 판별
- `POST /identify/stream` — SSE 스트리밍 판별 (detect → classify → done)
- `POST /identify/batch` — 배치 동기 판별 (최대 100개, 100MB)
- `POST /async/identify` — 단건 비동기 → task_id 반환
- `POST /async/identify/batch` — 배치 비동기 → task_id 반환
- `GET /async/result/{task_id}` — 비동기 결과 조회
- `POST /detect` — YOLO 차량 탐지만
- `POST /admin/reload-efficientnet` — EfficientNet 핫리로드
- `POST /admin/reload-vlm` — VLM 핫리로드 (`vlm_only` 모드)
- `GET /health` — 헬스체크 (IDENTIFIER_MODE 포함)
- SPA: `/static/{path}` → 파일 반환 or `index.html`

### 주요 파일
- `identifier/identifier.py` — 핵심 판별 로직 (VehicleIdentifier)
- `identifier/efficientnet_classifier.py` — EfficientNetV2-M 래퍼
- `identifier/vlm_service.py` — Ollama VLM (`vlm_only` 모드 전용)
- `identifier/tasks.py` — Celery 비동기 작업
- `identifier/config.py` — 전체 설정값

### Identifier 핵심 설정값
| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `IDENTIFIER_MODE` | `efficientnet` | `efficientnet` \| `vlm_only` |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.80` | `identified` 판정 최소 신뢰도 |
| `CLASSIFIER_LOW_CONFIDENCE_THRESHOLD` | `0.40` | 로그 tier 구분용 (실제 분기에 영향 없음) |
| `IDENTIFIER_YOLO_CONFIDENCE` | `0.25` | YOLO 탐지 신뢰도 |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | `true` | ARM에서는 `false`로 override |
| `VLM_MODEL_NAME` | `qwen3-vl:8b` | Ollama VLM 모델 (`vlm_only` 모드) |
| `VLM_TIMEOUT` | `30.0` | VLM 타임아웃 (초) |
| `EMBEDDING_DEVICE` | `cpu` | `cuda` \| `cpu` |

---

## Trainer Service (`trainer/`)

### 백엔드 선택 (TRAINER_BACKEND)
| 백엔드 | 플랫폼 | 용도 |
|--------|--------|------|
| `efficientnet` | 전체 (Docker: Linux/Windows CUDA/CPU) | EfficientNetV2-M 이미지 분류 파인튜닝 |
| `mlx` | Mac Apple Silicon (네이티브) | Qwen3-VL VLM 파인튜닝 (mlx-lm) |
| `llamafactory` | Linux/Windows (Docker) | VLM 파인튜닝 (LlamaFactory CLI) |

### EfficientNet 학습 파이프라인
1. Studio `POST /finetune/export-efficientnet` → CSV 생성 (`data/finetune/train/chunk_*.csv`)
2. Trainer `POST /train/start` → 학습 스크립트 생성 후 nohup 백그라운드 실행
3. 학습 완료 → `data/models/efficientnet/efficientnetv2_m_finetuned.pth` 저장
4. Identifier `POST /admin/reload-efficientnet` 핫리로드

### 학습 스크립트 특징 (efficientnet_trainer.py)
- **모델**: `tf_efficientnetv2_m.in21k_ft_in1k` + Dropout(0.3) + Linear(1280, num_classes), 입력 480×480
- **Data Augmentation**: RandomResizedCrop + TrivialAugmentWide + RandomErasing (학습), Resize+CenterCrop (검증)
- **CutMix/MixUp**: `use_mixup` 파라미터로 활성화
- **손실 함수**: CrossEntropyLoss (label_smoothing=0.1, 클래스 가중치 sqrt 보정)
- **옵티마이저**: AdamW (freeze/unfreeze 구간별 LR)
- **스케줄러**: OneCycleLR (Gradient Accumulation 반영)
- **Mixed Precision**: CUDA bf16(sm_80+)/fp16+GradScaler, MPS fp16, CPU fp32
- **EMA**: `use_ema` 파라미터, decay=0.999
- **Early Stopping**: `early_stopping_patience` (기본 3)
- **Per-Class 정확도**: worst 5 클래스 추적, JSONL `worst_classes` 필드 기록
- **Run 단위 로그**: `logs/trainer/{output_dir}/runs/{YYYYMMDD_HHMMSS}/` — `run_meta.json`, `trainer_log.jsonl`, `train.log`, `class_mapping.json`, `efficientnet_train.py`

### 하드웨어별 기본 파라미터
| 환경 | batch | grad_accum | eff_batch | workers | EMA | MixUp |
|------|-------|------------|-----------|---------|-----|-------|
| DGX Spark (sm_120+/100GB+) | 64 | 1 | 64 | 16 | O | O |
| High-end NVIDIA (20GB+) | 32 | 2 | 64 | 8 | O | O |
| Mid NVIDIA (8~20GB) | 16 | 4 | 64 | 4 | X | X |
| Low NVIDIA (<8GB) | 8 | 8 | 64 | 2 | X | X |
| Apple Silicon (MPS) | 16 | 2 | 32 | 2 | O | X |
| CPU | 4 | 8 | 32 | 0 | X | X |

### API 엔드포인트
- `GET /hw-profile` — 하드웨어 감지 + 권장 파라미터
- `POST /train/start` / `GET /train/status` / `POST /train/stop` / `GET /train/logs` / `GET /train/raw-log`
- `GET /train/runs` / `GET /train/runs/{run_id}` / `GET /train/runs/{run_id}/class-history`
- `DELETE /train/runs/{run_id}` — 학습 이력 삭제
- `GET /train/deploy-config` / `POST /train/export`
- `GET /model-info` / `GET /deploy/cmd` / `POST /deploy/ollama`
- `GET /health`

---

## Frontend (`frontend/`)

pnpm 워크스페이스 모노레포 (Node ≥ 20, pnpm 9.15.0).

### 구조
```
frontend/
├── apps/
│   ├── studio/       # @reeve/studio — Vite dev: 5173, build → studio/static/
│   └── identifier/   # @reeve/identifier — Vite dev: 5174, build → identifier/static/
├── packages/
│   ├── shared/       # API 타입(openapi-typescript), 공용 훅·유틸·ThemeProvider
│   ├── ui/           # shadcn/ui 기반 공통 UI 컴포넌트
│   └── config/       # eslint/tsconfig/tailwind 공통 설정
└── scripts/gen-types.ts
```

### Studio SPA 페이지 (`/static/`)
| 경로 | 컴포넌트 | 설명 |
|------|----------|------|
| `/basic-data` | `BasicDataPage` | 제조사·모델 기준데이터 관리 |
| `/admin` | `AdminPage` | 분석 결과 검수 |
| `/analyze` | `AnalyzePage` | 이미지 업로드·분석 (파일/로컬폴더/서버폴더 탭) |
| `/finetune` | `FinetunePage` | 파인튜닝 관리 |
| `/runs` | `RunsPage` | 학습 이력 대시보드 |

### Identifier SPA 페이지
- `SingleTab` — 단건 판별
- `BatchTab` — 배치 판별 (IntersectionObserver lazy 썸네일, 최대 32K 이미지)

### 스크립트 (frontend/ 루트)
| 명령 | 설명 |
|------|------|
| `pnpm dev:studio` | Studio dev server (5173) |
| `pnpm dev:identifier` | Identifier dev server (5174) |
| `pnpm build:studio` / `build:identifier` / `build:all` | 빌드 |
| `pnpm gen:types` | OpenAPI → TypeScript 타입 재생성 |
| `pnpm typecheck` / `pnpm lint` / `pnpm format` | 전체 검사 |

### 주요 프론트엔드 특징
- **SPA 라우팅**: `StaticFiles` 마운트 대신 커스텀 `GET /static/{path}` 라우트 — 파일이 있으면 반환, 없으면 `index.html` (딥링크 지원)
- **분석 탭 (AnalyzePage)**:
  - 파일 업로드: 업로드 세마포어(50) / 분석 세마포어(8) 분리. AbortController로 중단 시 즉시 종료
  - 로컬 폴더 감시: 폴더 내 이미지 자동 처리
  - 서버 폴더 감시: 3초 폴링으로 서버 디렉토리 신규 이미지 감지 → `data/uploads/`로 복사 후 파이프라인 실행. 처리 통계는 Zustand `serverStats`로 관리, localStorage(`reeve_server_stats_${uuid}`)에 지속 저장
- **폴더 감시 이탈 경고**: 탭 전환 및 사이드바 메뉴 클릭 시 confirm 다이얼로그. `folderWatchRunning` 상태는 Zustand store로 공유
- **학습 이력 대시보드 (`/runs`)**: RunListTable / RunDetailView / RunCompareView / ClassTrackingView

---

## Configuration

`docker/.env.example` → `docker/.env` 복사 후 설정:

| 항목 | 설명 |
|------|------|
| `OPENAI_API_KEY` | OpenAI Vision API 키 |
| `GEMINI_API_KEY` | Gemini API 키 (설정 시 교차 검증 자동 활성화) |
| `MYSQL_PASSWORD` | DB 비밀번호 |
| `EMBEDDING_DEVICE` | `cuda` (Linux/Windows) / `cpu` (Mac) |
| `IDENTIFIER_MODE` | `efficientnet` / `vlm_only` |
| `VISION_BACKEND` | `openai` / `ollama` / `local_inference` |
| `TRAINER_BACKEND` | `IDENTIFIER_MODE`와 반드시 일치 |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | 분석 결과 보관 기간 |
| `MAX_UPLOAD_SIZE` | 단일 이미지 최대 크기 (바이트, 기본 5MB) |
| `ALLOWED_EXTENSIONS` | 허용 확장자 (기본 `jpg,jpeg,png,webp`) |

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

> DGX Spark 등 고성능 GPU 환경: `TRAINER_MEMORY_LIMIT=50G` 이상 권장 (기본 12G로는 unfreeze 후 OOM Kill 발생)

---

## Key File Locations

| 파일 | 역할 |
|------|------|
| `studio/main.py` | Studio 진입점, SPA 라우팅 |
| `identifier/main.py` | Identifier 진입점 |
| `trainer/main.py` | Trainer 진입점 |
| `studio/api/analyze.py` | 업로드·감지·SSE 분석·서버폴더 API |
| `studio/api/admin.py` | 기준데이터·검수 관리 API |
| `studio/api/finetune.py` | export·학습·평가 API |
| `studio/services/vision_backend.py` | Vision 백엔드 팩토리 (DualVisionService 포함) |
| `studio/services/openai_vision.py` | OpenAI Vision 래퍼 (TokenBucket 내장) |
| `studio/services/gemini_vision.py` | Gemini Vision 래퍼 |
| `studio/services/local_inference_vision.py` | 자체 추론 API 래퍼 |
| `studio/config.py` | Studio 설정 (pydantic-settings) |
| `identifier/identifier.py` | 핵심 판별 로직 (VehicleIdentifier) |
| `identifier/efficientnet_classifier.py` | EfficientNetV2-M 래퍼 |
| `identifier/config.py` | Identifier 설정 |
| `trainer/api/train.py` | Trainer API 라우터 |
| `trainer/services/efficientnet_trainer.py` | EfficientNet 학습 스크립트 빌더 |
| `trainer/config.py` | Trainer 설정 |
| `studio/models/` | SQLAlchemy 모델 |
| `sql/user_provided_ddl.sql` | DB 스키마 |
| `sql/user_provided_dml.sql` | 시드 데이터 |
| `docker/Dockerfile.studio` | Studio 이미지 |
| `docker/Dockerfile.identifier` | Identifier 이미지 (Linux/Windows NVIDIA, `nvcr.io/nvidia/pytorch:25.03-py3`) |
| `docker/Dockerfile.identifier.mac` | Identifier 이미지 (Mac, `python:3.12-slim` CPU) |
| `docker/docker-compose.yml` | 기본 compose |
| `docker/docker-compose.dev.yml` | 개발 오버라이드 (소스 바인드 마운트, MySQL 포함) |
| `docker/docker-compose.mac.yml` | Mac overlay (ollama·trainer 비활성화) |
| `docker/docker-compose.gpu.yml` | NVIDIA GPU 리소스 예약 overlay |
| `docker/docker-compose.ssl.yml` | SSL 자체 서명 인증서 overlay |
| `frontend/apps/studio/` | Studio React SPA |
| `frontend/apps/identifier/` | Identifier React SPA |
| `frontend/packages/shared/src/api-types/` | OpenAPI 자동 생성 타입 (수정 금지) |
| `deploy/package.sh` | 배포 패키지 생성 스크립트 |
| `docs/ASYNC_USAGE.md` | 비동기 API 사용 가이드 |

---

## Platform Notes

- **Mac**: Ollama + Trainer 네이티브 실행 (docker-compose.mac.yml이 ollama·trainer 컨테이너 비활성화). `EMBEDDING_DEVICE=cpu`, `IDENTIFIER_ENABLE_TORCH_COMPILE=false`
- **Linux/Windows**: 전체 Docker, NVIDIA GPU. `EMBEDDING_DEVICE=cuda`
- **Studio hot-reload**: `--reload-dir /app/studio`로 `logs/` 변경을 감시하지 않음 (Trainer 스크립트 생성 시 재시작 방지)
- **Uvicorn worker count**: `identifier/start.sh`에서 CPU 코어 수 기준 자동 계산
- **export-efficientnet**: `run_in_executor` + `SessionLocal()`로 독립 DB 세션 사용 (SQLAlchemy 스레드 안전성)
- **정적 파일 경로**: Vite 빌드 결과 → `studio/static/` or `identifier/static/` → Docker COPY → `/app/static/`
- **MySQL lower_case_table_names**: `docker-compose.dev.yml`에 `--lower-case-table-names=1` 적용. 플랫폼 간 데이터 디렉토리 이동 시 기존 데이터 초기화 필요
- **호스트 포트 동적 할당**: compose 파일의 호스트 포트는 `${VAR:-default}` 패턴. `.env`에서 `STUDIO_PORT`, `IDENTIFIER_PORT`, `TRAINER_PORT`, `OLLAMA_PORT`, `MYSQL_PORT`, `REDIS_PORT` 재정의 가능
- **IDENTIFIER_URL**: Studio `/finetune/evaluate` 호출 시 `http://identifier:8001` 필요. `docker-compose.dev.yml` Studio service에 명시됨
- **Vite dev server**: `--profile vite` 플래그로 컨테이너화 가능, 또는 호스트에서 `pnpm dev:studio` / `pnpm dev:identifier` 직접 실행
