# Reeve

AI 기반 차량 제조사·모델 자동 식별 시스템.

CCTV·사진 이미지에서 차량을 탐지하고, 파인튜닝된 EfficientNetV2-M 분류기와 Qwen3-VL을 조합해 제조사와 모델을 자동으로 식별합니다.

---

## 아키텍처

```
사용자 이미지
    ↓
Studio (8000) — 업로드, OpenAI/Ollama 비전 분석, 관리 UI
    ↓
Identifier (8001) — YOLO 탐지 → EfficientNetV2-M 분류
    ↓
MySQL (결과 저장)
    ↓
Trainer (8002) — EfficientNet / LLM 파인튜닝 (LlamaFactory or MLX)
```

| 서비스 | 포트 | 역할 |
|--------|------|------|
| Studio | 8000 | 관리 UI, 데이터 라벨링, OpenAI Vision 분석, 파인튜닝 오케스트레이션 |
| Identifier | 8001 | 차량 식별 (동기/비동기), YOLO 탐지, EfficientNet 분류 |
| Trainer | 8002 | 모델 파인튜닝, LoRA 병합, GGUF 내보내기 |
| Redis | 6379 | Celery 브로커, 비동기 결과 저장 (24h TTL) |
| Ollama | 11434 | Qwen3-VL:8b 로컬 VLM 서빙 |
| MySQL | 3306 | 제조사, 모델, 분석 이력 저장 (개발 환경) |

**식별 파이프라인 (Identifier, efficientnet 모드 기준):**
1. **YOLO26** — 차량 바운딩 박스 탐지 및 크롭
2. **EfficientNetV2-M** — 1280차원 특징 벡터 추출 후 softmax 분류
3. 신뢰도 ≥ `CLASSIFIER_CONFIDENCE_THRESHOLD`(기본 0.80) → `identified` 반환
4. 임계값 미달 → `low_confidence` 반환 (VLM 폴백 없음)

식별 모드는 `IDENTIFIER_MODE` 환경변수로 전환: `efficientnet`(기본) / `vlm_only`.

---

## 시작하기

### 사전 요구사항

- Docker & Docker Compose
- (Linux/Windows) NVIDIA GPU + CUDA 드라이버
- (Mac) Apple Silicon (M1 이상)

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
| `OPENAI_API_KEY` | OpenAI API 키 (비전 분석용) |
| `GEMINI_API_KEY` | Gemini API 키 (교차 검증용) |
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
TRAINER_BACKEND=mlx uvicorn trainer.main:app --port 8002 &

docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml -f docker/docker-compose.mac.yml up -d
```

서비스 접속:
- Studio UI: http://localhost:8000
- Identifier API: http://localhost:8001
- Trainer API: http://localhost:8002

---

## 주요 환경 변수

### 공통

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `EMBEDDING_DEVICE` | `cpu` | 임베딩 연산 장치 (`cuda` / `cpu`) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |

### Studio (포트 8000)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `VISION_BACKEND` | `openai` | 비전 백엔드 (`openai` / `ollama`) |
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI 비전 모델 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 교차 검증 모델 |
| `STUDIO_VLM_MODEL` | `qwen3-vl:8b` | Ollama 백엔드 VLM |
| `FUZZY_MATCH_THRESHOLD` | `80` | 퍼지 매칭 임계값 |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | `30` | 분석 결과 보존 기간 (일) |
| `CLEANUP_HOUR` | `3` | 자동 정리 실행 시각 |

### Identifier (포트 8001)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDENTIFIER_MODE` | `efficientnet` | 식별 모드 (`efficientnet` / `vlm_only`) |
| `CLASSIFIER_CONFIDENCE_THRESHOLD` | `0.80` | EfficientNet `identified` 판정 최소 신뢰도 |
| `CLASSIFIER_LOW_CONFIDENCE_THRESHOLD` | `0.40` | 로그 구분용 하한 신뢰도 (실제 분기에는 영향 없음) |
| `VLM_MODEL_NAME` | `qwen3-vl:8b` | Ollama VLM 모델명 (`vlm_only` 모드에서 사용) |
| `VLM_TIMEOUT` | `30.0` | VLM 추론 타임아웃 (초) |
| `IDENTIFIER_YOLO_CONFIDENCE` | `0.25` | YOLO 탐지 신뢰도 |
| `IDENTIFIER_ENABLE_TORCH_COMPILE` | `true` | torch.compile 활성화 (ARM에서는 false) |
| `IDENTIFIER_MAX_BATCH_FILES` | `100` | 배치 최대 파일 수 |
| `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` | `104857600` | 배치 최대 업로드 크기 (100MB) |

### Trainer (포트 8002)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `TRAINER_BACKEND` | (자동) | `efficientnet` / `mlx` (Mac Apple Silicon, VLM) / `llamafactory` (Linux/Windows GPU, VLM) |

---

## API

### Identifier (8001)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/health` | 서비스 상태 확인 |
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
  "yolo_detected": true
}
```

status 해석: `identified` — 신뢰할 수 있는 결과 / `low_confidence` — 후보 있지만 확신 부족, 수동 확인 필요 / `no_match` — 분류기 미로드 또는 예외 발생

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

**UI**
- `GET /` — 메인 분석 UI
- `GET /admin-ui` — 관리/리뷰 UI
- `GET /analyze-ui` — 차량 분석 UI (YOLO 탐지 + SSE 스트리밍)
- `GET /finetune-ui` — 파인튜닝 관리 UI
- `GET /basic-data-ui` — 기준 데이터(제조사·모델) 관리 UI

**분석 / 관리**
- `POST /api/analyze/vehicle` — Vision 분석
- `POST /api/detect-vehicle` — YOLO 탐지만 수행
- `POST /api/analyze-vehicle-stream` — SSE 스트리밍 분석
- `GET/POST /admin/manufacturers` / `/admin/vehicle-models` — 기준 데이터 CRUD
- `GET /admin/analyzed-vehicles` — 분석 결과 목록
- `GET /admin/review-queue` / `PATCH /admin/review/{id}` — 검수 큐 및 승인
- `POST /admin/analyze-batch` — 배치 분석

**파인튜닝 (프록시)**
- `POST /finetune/export-efficientnet` — EfficientNet 학습용 CSV export (스레드풀 실행)
- `POST /finetune/export` — VLM 학습용 ShareGPT JSON export
- `POST /finetune/train/start` / `GET /finetune/train/status` / `POST /finetune/train/stop`
- `GET /finetune/train/logs` / `GET /finetune/train/raw-log`
- `GET /finetune/evaluate` — Before/After 정확도 평가
- `GET /finetune/hw-profile` — 하드웨어 권장 파라미터

### Trainer (8002)

- `POST /train/start` — 파인튜닝 시작 (`learning_rate`, `num_epochs`, `batch_size`, `freeze_epochs`, `gradient_accumulation`, `use_ema`, `use_mixup`, `early_stopping_patience` …)
- `GET /train/status` — 학습 진행 상태 (current_steps, total_steps, epoch, loss, val_acc)
- `POST /train/stop` — 학습 중단
- `GET /train/logs` — JSONL 로그 (tail)
- `GET /train/raw-log` — 원시 로그 (tail)
- `GET /train/deploy-config` — 배포 설정 조회
- `POST /train/export` — LoRA 병합 및 GGUF 내보내기 (VLM 백엔드)
- `GET /model-info` — 현재 모델 정보
- `GET /hw-profile` — 하드웨어 감지 및 최적 파라미터 제안
- `GET /deploy/cmd` / `POST /deploy/ollama` — Ollama 배포 헬퍼

---

## 배포 패키지 생성

```bash
./deploy/package.sh [dev-linux|dev-windows|dev-mac|prod-linux|prod-windows]
```

프로덕션 패키지는 MySQL 컨테이너를 포함하지 않으며, 외부 DB 연결을 사용합니다.

---

## 개발 환경 참고

- 개발 환경에서는 소스 코드가 컨테이너에 bind mount되어 코드 변경 시 자동 재시작됩니다.
- Uvicorn 워커 수는 `identifier/start.sh`에서 CPU 코어 수에 따라 자동 계산됩니다.
- 학습 데이터 결과: [docs/학습데이터결과서.md](docs/학습데이터결과서.md)
- 시스템 아키텍처 다이어그램: [docs/architecture.svg](docs/architecture.svg)
