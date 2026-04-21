# Reeve

AI 기반 차량 제조사·모델 자동 식별 시스템.

CCTV·사진 이미지에서 차량을 YOLO26으로 탐지하고, 파인튜닝된 EfficientNetV2-M 분류기로 제조사와 모델을 식별합니다. 필요 시 Qwen3-VL(Ollama) VLM-only 모드로도 전환할 수 있습니다.

---

## 아키텍처

```
사용자 이미지
    ↓
Studio (8000) — 업로드, OpenAI/Gemini/Ollama 비전 분석, 관리 UI, 파인튜닝 오케스트레이션
    ↓
Identifier (8001) — YOLO 탐지 → EfficientNetV2-M 분류 (또는 vlm_only)
    ↓
MySQL (기준 데이터·분석 결과·학습 데이터 저장)
    ↓
Trainer (8002) — EfficientNetV2-M / VLM(Qwen3-VL) 파인튜닝
```

| 서비스 | 포트 | 역할 |
|--------|------|------|
| Studio | 8000 | 관리 UI(React SPA), 데이터 라벨링, OpenAI Vision 분석, 파인튜닝 오케스트레이션 |
| Identifier | 8001 | 차량 식별(동기/비동기), YOLO 탐지, EfficientNet 분류 |
| Trainer | 8002 | 모델 파인튜닝(EfficientNet/MLX), 학습 오케스트레이션 |
| Redis | 6379 | Celery 브로커, 비동기 결과 저장 (24h TTL) |
| Ollama | 11434 | Qwen3-VL:8b 로컬 VLM 서빙 (`vlm_only` 모드 또는 Studio `ollama` 백엔드에서 사용) |
| MySQL | 3306 | 제조사·모델·분석 이력·학습 데이터 저장 (개발 환경 기본 포함) |

**식별 파이프라인 (Identifier, efficientnet 모드):**
1. **YOLO26** — 차량 바운딩 박스 탐지 및 크롭
2. **EfficientNetV2-M** — 크롭 이미지에서 softmax 분류
3. 신뢰도 ≥ `CLASSIFIER_CONFIDENCE_THRESHOLD`(기본 0.80) → `identified`
4. 임계값 미달 → `low_confidence` (VLM 폴백 없음)

식별 모드는 `IDENTIFIER_MODE` 환경변수로 전환합니다: `efficientnet`(기본) / `vlm_only`.

> Qdrant 의존성은 제거되었습니다(v2.1). 과거 `visual_rag` 모드 및 임베딩 기반 검색은 더 이상 사용되지 않습니다.

---

## 시작하기

### 사전 요구사항

- Docker & Docker Compose
- (Linux/Windows) NVIDIA GPU + CUDA 드라이버
- (Mac) Apple Silicon (M1 이상) — Ollama·Trainer는 네이티브 실행
- (프론트엔드 개발 시) Node.js 20+ & pnpm 9+

### 환경 설정

```bash
cp docker/.env.example docker/.env
# docker/.env 파일을 열어 필수 값 입력
```

**필수 설정:**

| 변수 | 설명 |
|------|------|
| `MYSQL_ROOT_PASSWORD` | MySQL root 비밀번호 |
| `MYSQL_PASSWORD` | 애플리케이션 DB 비밀번호 |
| `OPENAI_API_KEY` | OpenAI API 키 (비전 분석용, `VISION_BACKEND=openai` 시) |
| `GEMINI_API_KEY` | Gemini API 키 (교차 검증 — 선택 사항) |
| `EMBEDDING_DEVICE` | `cuda` (Linux/Windows GPU) 또는 `cpu` (Mac) |

### 실행

**Linux/Windows (NVIDIA GPU):**
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up -d
```

**Mac (Apple Silicon):**
```bash
# Ollama와 Trainer는 네이티브로 실행
ollama serve &
TRAINER_BACKEND=efficientnet uvicorn trainer.main:app --port 8002 &   # efficientnet 모드
# 또는 TRAINER_BACKEND=mlx (vlm_only 모드일 때)

docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.mac.yml up -d
```

서비스 접속:
- Studio UI: http://localhost:8000
- Identifier API: http://localhost:8001
- Trainer API: http://localhost:8002

---

## 프론트엔드 (React + Vite)

`frontend/` — pnpm workspace 모노레포. Studio와 Identifier 두 개의 React SPA를 포함합니다.

```
frontend/
├── apps/
│   ├── studio/       # Studio UI (포트 5173, 빌드 결과: /static/ → Docker 이미지 내 /app/static/)
│   └── identifier/   # Identifier UI (포트 5174, 빌드 결과: /static/ → Docker 이미지 내 /app/static/)
└── packages/
    ├── shared/       # API 클라이언트, 타입(openapi-typescript 자동 생성), 훅
    ├── ui/           # shadcn/ui 컴포넌트 + BboxCanvas 등 공용 composites
    └── config/       # tsconfig / tailwind / eslint / prettier 공유 설정
```

**개발:**
```bash
cd frontend
pnpm install

pnpm dev:studio        # http://localhost:5173 (→ http://studio:8000 프록시)
pnpm dev:identifier    # http://localhost:5174 (→ http://identifier:8001 프록시)

pnpm gen:types         # FastAPI OpenAPI → TS 타입 재생성
pnpm build:all         # 두 앱 빌드 → 각 앱 루트의 /static/
pnpm typecheck         # 전체 워크스페이스 타입 체크
```

Docker 이미지(`Dockerfile`, `Dockerfile.identifier`)는 멀티스테이지 빌드로 프론트엔드를 자동으로 번들링합니다.

> **SPA 라우팅**: `StaticFiles` 마운트 대신 커스텀 라우트를 사용하므로 `/static/analyze` 등 URL 직접 진입이 정상 동작합니다.

---

## 주요 환경 변수

### 공통

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `EMBEDDING_DEVICE` | `cpu` | 연산 장치 (`cuda` / `cpu`) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |
| `STUDIO_PORT` | `8000` | Studio 호스트 포트 (컨테이너 내부 포트는 항상 8000) |
| `IDENTIFIER_PORT` | `8001` | Identifier 호스트 포트 |
| `TRAINER_PORT` | `8002` | Trainer 호스트 포트 |
| `OLLAMA_PORT` | `11434` | Ollama 호스트 포트 |
| `MYSQL_PORT` | `3306` | MySQL 호스트 포트 |
| `REDIS_PORT` | `6379` | Redis 호스트 포트 |

### Studio (포트 8000)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `VISION_BACKEND` | `openai` | 비전 백엔드 (`openai` / `ollama`) |
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI 비전 모델 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 교차 검증 모델 (선택) |
| `STUDIO_VLM_MODEL` | `qwen3-vl:8b` | Ollama 백엔드 VLM |
| `FUZZY_MATCH_THRESHOLD` | `80` | 모델명 퍼지 매칭 임계값 (0~100) |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | `30` | 분석 결과 보존 기간 (일) |
| `CLEANUP_HOUR` | `3` | 자동 정리 실행 시각 |
| `SERVER_WATCH_BASE_DIR` | `/mnt/` | 서버 폴더 감시 허용 기본 경로 (이 경로 하위만 접근 가능) |

### Identifier (포트 8001)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDENTIFIER_MODE` | `efficientnet` | 식별 모드 (`efficientnet` / `vlm_only`) |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.80` | `identified` 판정 최소 신뢰도 |
| `CLASSIFIER_LOW_CONFIDENCE_THRESHOLD` | `0.40` | 로그 구분용 (실제 분기에는 영향 없음) |
| `VLM_MODEL_NAME` | `qwen3-vl:8b` | Ollama VLM 모델명 (`vlm_only` 모드 시) |
| `VLM_TIMEOUT` | `30.0` | VLM 추론 타임아웃 (초) |
| `IDENTIFIER_YOLO_CONFIDENCE` | `0.25` | YOLO 탐지 신뢰도 |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | `true` | torch.compile (ARM에서는 false로 override) |
| `IDENTIFIER_MAX_BATCH_FILES` | `100` | 배치 최대 파일 수 |
| `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` | `104857600` | 배치 최대 업로드 크기 (100MB) |

### Trainer (포트 8002)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TRAINER_BACKEND` | `efficientnet` | `efficientnet` (Linux/Windows NVIDIA) / `mlx` (Mac Apple Silicon) |

---

## API

### Identifier (8001)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/health` | 서비스 상태 확인 (EfficientNet/YOLO 로드 상태) |
| POST | `/detect` | YOLO 차량 탐지 (바운딩 박스 반환) |
| POST | `/identify` | 단일 이미지 동기 식별 |
| POST | `/identify/stream` | SSE 스트리밍 식별 (단계별 진행) |
| POST | `/identify/batch` | 배치 동기 식별 (최대 100장, 100MB) |
| POST | `/async/identify` | 단일 이미지 비동기 식별 |
| POST | `/async/identify/batch` | 배치 비동기 식별 |
| GET | `/async/result/{task_id}` | 비동기 결과 조회 |
| POST | `/admin/reload-efficientnet` | EfficientNet 모델 핫리로드 |
| POST | `/admin/reload-vlm` | VLM 모델 핫리로드 |

**식별 응답 예시:**
```json
{
  "status": "identified",
  "manufacturer_korean": "현대",
  "manufacturer_english": "Hyundai",
  "model_korean": "아반떼",
  "model_english": "Avante",
  "confidence": 0.95,
  "detection": { "bbox": [120, 48, 860, 612], "confidence": 0.98, "class_name": "car" }
}
```

`status` 해석:
- `identified` — 신뢰할 수 있는 결과
- `low_confidence` — 후보는 있지만 확신 부족 (수동 확인 권장)
- `no_match` — 분류기 미로드 또는 예외
- `yolo_failed` — 차량이 감지되지 않음

### 비동기 처리 흐름

```
POST /async/identify → { "task_id": "abc-123" }  (즉시 반환, <10ms)
         ↓
Redis 큐 → Celery Worker 처리
         ↓
GET /async/result/{task_id} → { "status": "SUCCESS", "result": {...} }
```

결과는 Redis에 24시간 보관됩니다. 자세한 내용은 [docs/ASYNC_USAGE.md](docs/ASYNC_USAGE.md) 참조.

### Studio (8000)

**UI (React SPA)** — 모든 페이지는 `/static/` 하위에 서빙됩니다.
- `/` → `/static/` 리다이렉트
- `/static/analyze` — 차량 분석 (파일/폴더 업로드 + YOLO 탐지 + SSE 스트리밍)
- `/static/admin` — 분석 결과 검수 큐 및 승인
- `/static/basic-data` — 제조사·모델 기준 데이터 CRUD
- `/static/finetune` — 파인튜닝 관리 (데이터 export → 학습 → 배포)

**분석 / 관리 API**
- `POST /api/analyze/vehicle` — Vision 분석
- `POST /api/detect-vehicle` — YOLO 탐지만 수행
- `POST /api/analyze-vehicle-stream` — SSE 스트리밍 분석
- `GET/POST /admin/manufacturers` / `/admin/vehicle-models` — 기준 데이터 CRUD
- `GET /admin/analyzed-vehicles` — 분석 결과 목록
- `PATCH /admin/analyzed-vehicles/{id}/verify` — 검수 승인 → `TrainingDataset` 적재
- `POST /admin/analyze-batch` — 배치 분석

**서버 폴더 감시 API**
- `GET /api/server-files?path=...` — 서버 디렉토리 이미지 파일 목록 (`SERVER_WATCH_BASE_DIR` 하위만 허용)
- `POST /api/server-files/register` — 서버 경로 파일을 `data/uploads/`로 복사 후 등록 (`/api/upload`와 동일 응답)
- `GET /api/server-files/image?path=...` — 서버 경로 이미지 파일 제공 (UI 프리뷰용)

**파인튜닝 (Trainer 프록시)**
- `POST /finetune/export-efficientnet` — EfficientNet 학습용 CSV export (스레드풀 실행)
- `POST /finetune/export` — VLM 학습용 ShareGPT JSON export
- `POST /finetune/train/start` / `GET /finetune/train/status` / `POST /finetune/train/stop`
- `GET /finetune/train/logs` / `GET /finetune/train/raw-log`
- `GET /finetune/evaluate` — Before/After 정확도 평가
- `GET /finetune/hw-profile` — 하드웨어 권장 파라미터

### Trainer (8002)

- `POST /train/start` — 파인튜닝 시작 (`learning_rate`, `num_epochs`, `batch_size`, `freeze_epochs`, `gradient_accumulation`, `use_ema`, `use_mixup`, `num_workers`, `early_stopping_patience`, `max_per_class` …)
- `GET /train/status` — 진행 상태 (current_steps, total_steps, epoch, loss, val_acc)
- `POST /train/stop` — 학습 중단
- `GET /train/logs` — JSONL 로그 (tail)
- `GET /train/raw-log` — 원시 로그 (tail)
- `GET /train/deploy-config` — 핫리로드 경로 정보
- `POST /train/export` — LoRA 병합 (VLM 백엔드)
- `GET /model-info` — 현재 EfficientNet 모델 클래스 수
- `GET /hw-profile` — 하드웨어 감지 및 최적 파라미터 제안
- `GET /deploy/cmd` / `POST /deploy/ollama` — GGUF 변환 + Ollama 배포 헬퍼

---

## 배포 패키지 생성

```bash
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows|all]
```

프로덕션 패키지는 MySQL 컨테이너를 포함하지 않으며, 외부 DB 연결을 사용합니다.

---

## 개발 환경 참고

- **소스 자동 재시작**: Studio는 `--reload-dir /app/studio`로 실행되어 `logs/` 변경은 무시합니다 (Trainer 로그 생성 시 Studio 재시작 방지).
- **Uvicorn 워커 수**: `identifier/start.sh`가 CPU 코어 수 기반으로 자동 계산합니다.
- **멀티아키텍처 Docker**: `Dockerfile.identifier`는 Linux/Windows(NVIDIA GPU) 용으로 `nvcr.io/nvidia/pytorch` 기반(amd64·arm64 CUDA 모두 지원). Mac Apple Silicon 용은 `Dockerfile.identifier.mac`(CPU torch, `python:3.12-slim`)이 별도로 존재하며 `docker-compose.mac.yml`에서 자동 선택됩니다.
- **파인튜닝 모델 공유**: `data/models/efficientnet/`가 Trainer와 Identifier 간 바인드 마운트로 공유됩니다 (핫리로드 지원).
- **정적 파일 빌드 위치**: Vite 빌드 결과물은 각 서비스 디렉터리(`studio/static/`) 대신 프로젝트 루트의 `/static/`으로 출력됩니다. Docker 이미지에서 `/app/static/`으로 복사되며, 개발 환경 바인드 마운트와 충돌하지 않습니다.
- **evaluate API**: Studio 컨테이너에서 Identifier를 호출할 때 `IDENTIFIER_URL=http://identifier:8001`이 반드시 설정되어야 합니다(`docker-compose.dev.yml` 참조).
- 학습 데이터 결과: [docs/학습데이터결과서.md](docs/학습데이터결과서.md)
- 시스템 아키텍처 다이어그램: [docs/architecture.svg](docs/architecture.svg)
