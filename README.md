# Reeve

AI 기반 차량 제조사·모델 자동 식별 시스템.

CCTV·사진 이미지에서 차량을 YOLO26m으로 탐지하고, 파인튜닝된 EfficientNetV2-M 분류기로 제조사와 모델을 식별합니다. 필요 시 Qwen3-VL(Ollama) VLM-only 모드로도 전환할 수 있습니다.

---

## 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│  클라이언트 (브라우저)                                           │
│  Studio SPA (:8000/static)  │  Identifier SPA (:8001/static)   │
└────────────┬────────────────────────────┬────────────────────────┘
             │                            │
┌────────────▼──────────┐   ┌────────────▼──────────┐
│  Studio :8000          │   │  Identifier :8001      │
│  FastAPI               │   │  FastAPI + Celery      │
│  Vision 사전 분석       │   │  YOLO → EfficientNet  │
│  검수 관리 CRUD         │   │  or VLM-only 판별      │
│  파인튜닝 조율           │   │  배치·비동기 처리       │
└──────┬─────┬─────┬────┘   └──────────┬────────────┘
       │     │     │                    │
    MySQL  Redis  Trainer:8002        Redis
               (Celery  EfficientNet  (broker)
               broker)  파인튜닝
```

| 서비스 | 포트 | 역할 |
|--------|------|------|
| `studio` | 8000 | 관리 UI, 이미지 업로드·분석, 검수, 파인튜닝 조율 |
| `identifier` | 8001 | ML 판별 파이프라인 (동기·배치·비동기) |
| `trainer` | 8002 | EfficientNet / VLM 파인튜닝 API |
| `mysql` | 3306 | 제조사·모델·분석 이력·학습 데이터 |
| `redis` | 6379 | Celery 브로커/백엔드 |
| `ollama` | 11434 | Qwen3-VL 로컬 VLM (vlm_only 모드 또는 Studio ollama 백엔드) |

---

## 빠른 시작

### 1. 환경 설정

```bash
cp docker/.env.example docker/.env
# docker/.env 를 열어 ★ 항목 편집
#   OPENAI_API_KEY=...
#   MYSQL_PASSWORD=...
```

### 2. 서비스 기동

**Mac (Apple Silicon) — Ollama/Trainer 네이티브, 나머지 Docker**

```bash
# Ollama 네이티브 실행
ollama serve &
ollama pull qwen3-vl:8b

# Trainer 네이티브 실행 (별도 터미널)
cd <project-root>
TRAINER_BACKEND=efficientnet uvicorn trainer.main:app --port 8002

# 나머지 Docker
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.dev.yml \
               -f docker/docker-compose.mac.yml up -d
```

**Linux/Windows (NVIDIA GPU) — 전체 Docker**

```bash
docker compose -f docker/docker-compose.yml \
               -f docker/docker-compose.dev.yml \
               -f docker/docker-compose.gpu.yml up -d
```

**SSL 추가** (위 명령어 끝에 추가)

```bash
./docker/gen-cert.sh <SERVER_IP>
# 끝에 -f docker/docker-compose.ssl.yml 추가
```

### 3. 접속

- Studio 관리 UI: `http://localhost:8000/static/`
- Identifier SPA: `http://localhost:8001/static/`
- Studio API 문서: `http://localhost:8000/docs` (개발 환경)

---

## 주요 기능

### Studio 관리 UI

| 메뉴 | 기능 |
|------|------|
| 기준 데이터 | 제조사·모델 등록·수정 |
| 분석 | 이미지 업로드 → YOLO 탐지 → Vision 분석 (파일/로컬폴더/서버폴더 탭) |
| 차량 데이터 관리 | 분석 결과 검수 (승인/보류/반려/재개), 일괄 처리 |
| 파인튜닝 | 학습 데이터 export → EfficientNet 학습 시작·모니터링 |
| 학습 이력 | Run 목록·상세·클래스 정확도 추이 비교 |

### 분석 탭

- **파일 업로드**: 단건 또는 다중 파일 선택 → 즉시 업로드(DB 레코드 생성) → YOLO 감지 → Vision 분석 SSE 스트리밍
- **로컬 폴더 감시**: 지정한 로컬 폴더의 이미지를 자동으로 처리 (업로드 세마포어 50, 분석 세마포어 8)
- **서버 폴더 감시**: NAS 등 서버 디렉토리를 3초 폴링으로 감시 → 신규 파일 복사 후 파이프라인 실행

### Identifier 판별 API

```bash
# 단건 동기 판별
curl -X POST http://localhost:8001/identify \
  -F "file=@car.jpg"

# SSE 스트리밍 판별
curl -X POST http://localhost:8001/identify/stream \
  -F "file=@car.jpg" -H "Accept: text/event-stream"

# 배치 판별 (최대 100개)
curl -X POST http://localhost:8001/identify/batch \
  -F "files=@car1.jpg" -F "files=@car2.jpg"

# 비동기 판별
curl -X POST http://localhost:8001/async/identify \
  -F "file=@car.jpg"
# → {"task_id": "..."}

curl http://localhost:8001/async/result/{task_id}
```

판별 결과 `status` 값:
| 값 | 의미 |
|----|------|
| `identified` | 신뢰도 ≥ 임계값 (기본 0.80), 제조사·모델 확정 |
| `low_confidence` | 신뢰도 미달 — 사람이 확인 필요 |
| `no_vehicle` | 차량 탐지 실패 |
| `error` | 처리 오류 |

---

## Vision 분석 백엔드

Studio가 이미지를 사전 분석하는 데 사용하는 AI 백엔드를 `.env`에서 선택합니다.

| `VISION_BACKEND` | 조건 | 동작 |
|------------------|------|------|
| `openai` (단독) | `OPENAI_API_KEY`만 설정 | GPT Vision API 단독 분석 |
| `openai` (교차 검증) | `OPENAI_API_KEY` + `GEMINI_API_KEY` 모두 설정 | OpenAI + Gemini 병렬 호출, 결과 일치 시에만 성공 |
| `ollama` | `VISION_BACKEND=ollama` | 로컬 Qwen3-VL VLM 사용 |
| `local_inference` | `VISION_BACKEND=local_inference` | 자체 추론 API (`POST /infer`) — YOLO+분류 통합 |

---

## 판별 모드 (Identifier)

| `IDENTIFIER_MODE` | 파이프라인 |
|-------------------|-----------|
| `efficientnet` (기본) | YOLO → EfficientNetV2-M → `identified` or `low_confidence` |
| `vlm_only` | YOLO → Qwen3-VL → `identified` or `low_confidence` |

---

## 파인튜닝 워크플로

```
1. Studio → 파인튜닝 → 학습 데이터 export (EfficientNet CSV)
2. Studio → 파인튜닝 → 학습 시작 (Trainer API 프록시)
3. Trainer → EfficientNetV2-M 학습 실행 (nohup 백그라운드)
4. 학습 완료 → data/models/efficientnet/ 에 .pth + class_mapping.json 저장
5. Studio → 파인튜닝 → EfficientNet 핫리로드 (Identifier 재시작 없이 모델 교체)
```

### 파인튜닝 파라미터

| 파라미터 | 설명 |
|----------|------|
| `num_epochs` | 전체 학습 에폭 수 |
| `freeze_epochs` | EfficientNet backbone freeze 에폭 수 |
| `batch_size` | 미니배치 크기 |
| `gradient_accumulation` | 그래디언트 누적 스텝 수 |
| `learning_rate` | 학습률 |
| `use_ema` | EMA (지수 이동 평균) 가중치 사용 |
| `use_mixup` | CutMix/MixUp 데이터 증강 |
| `early_stopping_patience` | 검증 정확도 개선 없을 시 조기 종료 에폭 수 |
| `max_per_class` | 클래스당 최대 학습 이미지 수 |

하드웨어에 최적화된 기본값은 Studio UI의 하드웨어 프로파일 버튼으로 자동 설정됩니다.

---

## 데이터 흐름

```
이미지 업로드
  → AnalyzedVehicle 생성 (processing_stage: uploaded)
  → YOLO 탐지 (→ yolo_detected | no_vehicle)
  → bbox 선택 → Vision 분석 SSE (→ analysis_complete)
  → 검수 (pending → approved / on_hold / rejected)
  → TrainingDataset 적재 (approved 시)
  → EfficientNet 학습 데이터로 사용
```

---

## 배포 패키징

```bash
./deploy/package.sh dev-linux     # Linux 개발 환경 패키지
./deploy/package.sh dev-mac       # Mac 개발 환경 패키지
./deploy/package.sh prod-linux    # Linux 운영 환경 패키지
./deploy/package.sh all           # 전체 패키지 생성
```

---

## 프론트엔드 개발

```bash
cd frontend

# 의존성 설치
pnpm install

# dev server 실행
pnpm dev:studio      # http://localhost:5173
pnpm dev:identifier  # http://localhost:5174

# 빌드
pnpm build:all

# API 타입 재생성 (FastAPI OpenAPI 스키마 → TypeScript)
pnpm gen:types

# 전체 검사
pnpm typecheck && pnpm lint
```

---

## 환경변수 참조

전체 설정 항목은 `docker/.env.example` 참조.

**최소 필수 설정 (`docker/.env`)**

```env
# MySQL
MYSQL_ROOT_PASSWORD=...
MYSQL_PASSWORD=...

# OpenAI Vision (VISION_BACKEND=openai 일 때)
OPENAI_API_KEY=...

# GPU 환경
EMBEDDING_DEVICE=cuda   # Mac이면 cpu
```

**주요 선택 설정**

```env
# Gemini 교차 검증 (설정 시 자동 활성화)
GEMINI_API_KEY=...

# 판별 모드
IDENTIFIER_MODE=efficientnet    # 또는 vlm_only
TRAINER_BACKEND=efficientnet    # IDENTIFIER_MODE와 일치시킬 것

# Vision 백엔드
VISION_BACKEND=openai   # openai | ollama | local_inference

# 메모리 한도 (DGX Spark 등 고성능 환경)
TRAINER_MEMORY_LIMIT=80G
```

---

## 디렉토리 구조

```
reeve/
├── studio/          FastAPI Studio 서비스
│   ├── api/         API 라우터 (analyze, admin, finetune)
│   ├── models/      SQLAlchemy 모델
│   ├── services/    Vision 백엔드·감지·매칭 서비스
│   └── tasks/       APScheduler 정리 작업
├── identifier/      FastAPI Identifier 서비스
├── trainer/         FastAPI Trainer 서비스
│   ├── api/         학습·이력·배포 API
│   └── services/    EfficientNet·MLX·LlamaFactory 트레이너
├── frontend/        React SPA (pnpm 워크스페이스)
│   ├── apps/studio/
│   ├── apps/identifier/
│   └── packages/    shared·ui·config
├── docker/          Docker compose·Dockerfile·env.example
├── sql/             DB 스키마·시드 데이터
├── deploy/          배포 패키징 스크립트
├── data/            런타임 데이터 (uploads·crops·models·mysql·redis)
└── logs/            서비스 로그
```
