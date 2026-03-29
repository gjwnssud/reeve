# Reeve — AI 기반 차량 제조사/모델 자동 식별 시스템

CCTV·카메라 영상에서 차량을 감지하고, CLIP 임베딩 + 벡터 검색 + VLM 재판정으로 제조사와 모델을 자동 식별합니다.

---

## 시스템 구성

| 서비스 | 포트 | 역할 |
|--------|------|------|
| **Studio** | 8000 | 데이터 관리, 분석, 학습 데이터 추출, 파인튜닝 오케스트레이션 |
| **Identifier** | 8001 | 프로덕션 차량 식별 API (동기 + 비동기 배치) |
| **LLaMA-Factory** | 7860 | VLM 파인튜닝 WebUI |

---

## 아키텍처

### 데이터 흐름

```
이미지 업로드
    │
    ▼
YOLO26 차량 감지 → BBox 선택
    │
    ▼
Vision API 분석 (OpenAI GPT-5.2 / Gemini 2.5 Flash / Ollama)
    │
    ▼
RapidFuzz 매칭 → manufacturers / vehicle_models (MySQL)
    │
    ▼
관리자 검토 & 승인
    │
    ▼
CLIP-ViT-B/32 임베딩 (512d) → Qdrant 저장
    │
    ▼
Identifier 서비스 (벡터 검색 + 투표 + VLM 재판정)
```

### 식별 알고리즘

1. **YOLO26** — 차량 감지 및 크롭
2. **CLIP** — 512d 벡터 임베딩 생성
3. **Qdrant top-K 검색** — (manufacturer_id, model_id) 쌍으로 투표 집계
4. **신뢰도 판정** — `identified` / `uncertain` / `unidentified`
5. **VLM 재판정** (visual_rag 모드) — Qwen3-VL:8b 최종 판정

**동작 모드** (`IDENTIFIER_MODE`):
- `clip_only` — CLIP + 투표만 사용 (기본)
- `visual_rag` — CLIP 후보 → Qwen3-VL 재판정
- `vlm_only` — VLM 단독 판정

**안전장치**:
- 투표 집중도: 승자 득표율이 top-K의 30% 미만이면 `uncertain`
- YOLO 미감지: 차량이 감지되지 않으면 결과를 `uncertain`으로 하향

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 언어 | Python 3.12 |
| API 프레임워크 | FastAPI + Uvicorn |
| AI / Vision | OpenAI API, Gemini API, CLIP, YOLO26, Ollama (Qwen3-VL) |
| 임베딩 | CLIP-ViT-B/32 (512d), sentence-transformers |
| 파인튜닝 | LLaMA-Factory (QLoRA 4bit → LoRA merge → GGUF → Ollama) |
| 관계형 DB | MySQL 8.0 (SQLAlchemy + aiomysql) |
| 벡터 DB | Qdrant |
| 비동기 처리 | Celery 5 + Redis 7 |
| 스케줄러 | APScheduler |
| 컨테이너 | Docker / Docker Compose |

---

## 빠른 시작

### 사전 준비

`docker/.env` 파일 생성 (`.env.example` 참고):

```env
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
MYSQL_PASSWORD=your_password
QDRANT_HOST=qdrant
EMBEDDING_DEVICE=cuda   # Mac은 cpu
```

### 개발 환경 시작

```bash
# Linux / Windows (NVIDIA GPU)
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml up -d

# macOS (CPU 모드)
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml up -d
```

### 프로덕션 시작

```bash
cd docker
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

### 로컬 실행 (Docker 없이)

```bash
uvicorn studio.main:app --reload --port 8000
uvicorn identifier.main:app --reload --port 8001
celery -A identifier.celery_app worker --loglevel=info
```

---

## API 주요 엔드포인트

### Studio (8000)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/` | 분석 UI (analyze_v2.html) |
| `GET` | `/admin-ui` | 관리자 UI (DB관리 + 학습데이터추출) |
| `GET` | `/finetune-ui` | 파인튜닝 관리 UI |
| `POST` | `/api/upload` | 이미지 업로드 (DB 레코드 생성) |
| `POST` | `/api/detect-vehicle` | YOLO 차량 감지 |
| `POST` | `/api/analyze-vehicle-stream` | Vision API 분석 (SSE 스트리밍) |
| `POST` | `/api/sync-to-qdrant` | 승인된 데이터 → Qdrant 동기화 |

### Identifier (8001)

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/identify` | 동기 단일 이미지 식별 |
| `POST` | `/identify/batch` | 동기 배치 (최대 100개 / 100MB) |
| `POST` | `/async/identify` | 비동기 단일 이미지 (task_id 반환) |
| `POST` | `/async/identify/batch` | 비동기 배치 (task_id 반환) |
| `GET` | `/async/result/{task_id}` | 비동기 결과 폴링 |
| `GET` | `/docs` | OpenAPI 문서 (CCTV 연동 가이드 포함) |

### 비동기 처리 흐름

```
POST /async/identify → task_id 즉시 반환 (<10ms)
    │
    ▼ (Redis 큐)
Celery Worker 처리 (자동 3회 재시도)
    │
    ▼ (Redis 저장, 24h TTL)
GET /async/result/{task_id} → PENDING / STARTED / SUCCESS / FAILURE
```

---

## 데이터베이스

MySQL 8.0, 4개 테이블:

```
manufacturers (제조사)
    └── vehicle_models (차량 모델, 1:N cascade delete)
            └── analyzed_vehicles (분석 결과, SET NULL on delete)
                        └── training_dataset (학습 데이터, Qdrant qdrant_id 연결)
```

- 스키마: `sql/user_provided_ddl.sql`
- 시드 데이터: `sql/user_provided_dml.sql`
- Docker 초기화 시 자동 적용

---

## 설정 (주요 환경변수)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDENTIFIER_MODE` | `clip_only` | 식별 모드 |
| `IDENTIFIER_TOP_K` | `10` | Qdrant 검색 결과 수 |
| `IDENTIFIER_VOTE_THRESHOLD` | `3` | 최소 득표 수 |
| `IDENTIFIER_CONFIDENCE_THRESHOLD` | `0.80` | 최소 신뢰도 점수 |
| `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD` | `0.3` | 승자 최소 득표율 |
| `VLM_MODEL_NAME` | `qwen3-vl:8b` | Ollama VLM 모델명 |
| `FUZZY_MATCH_THRESHOLD` | `80` | RapidFuzz 매칭 임계값 |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` 또는 `cuda` |
| `CLEANUP_ENABLED` | `true` | 미검증 레코드 자동 정리 |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | `30` | 미검증 레코드 보존 기간 |

---

## 파인튜닝 파이프라인

1. Studio `/finetune-ui`에서 학습 데이터 Export
   - `data/finetune/vehicle_train.json`, `vehicle_val.json` 생성 (LLaMA-Factory sharegpt 형식)
2. LLaMA-Factory WebUI (port 7860)에서 QLoRA 4bit 학습
3. LoRA merge → GGUF 변환 → Ollama 배포
4. `VLM_MODEL_NAME`을 배포된 모델명으로 업데이트

---

## 개발 참고

- **Identifier는 MySQL 불필요.** 제조사/모델 이름은 Qdrant payload에서 직접 조회.
- **워커 수 자동 계산**: `IDENTIFIER_TORCH_THREADS`만 설정하면 `start.sh`가 `workers = cpu_count // IDENTIFIER_TORCH_THREADS`로 계산.
- **날짜별 파일 저장**: `data/uploads/YYYY-MM-DD/`, `data/crops/YYYY-MM-DD/`
- **Vision 백엔드 추상화**: `studio/services/vision_backend.py`에서 OpenAI / Gemini / Ollama 통합 관리.
- **Qdrant 중복 방지**: 동기화 시 유사도 0.92 이상이면 자동 스킵.

---

## 문서

- [`docs/ASYNC_USAGE.md`](docs/ASYNC_USAGE.md) — 비동기 API 상세 사용 가이드
- [`docs/별첨2_AI솔루션_세부설명자료.md`](docs/별첨2_AI솔루션_세부설명자료.md) — AI 솔루션 기술 상세 설명
- `GET /docs` (Identifier) — OpenAPI Swagger (CCTV 연동 엔지니어용 가이드 포함)
