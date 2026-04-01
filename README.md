# Reeve

AI 기반 차량 제조사·모델 자동 식별 시스템.

CCTV·사진 이미지에서 차량을 탐지하고, EfficientNet 임베딩 + Qdrant 벡터 검색 + 파인튜닝된 Qwen3-VL을 조합해 제조사와 모델을 자동으로 식별합니다.

---

## 아키텍처

```
사용자 이미지
    ↓
Studio (8000) — 업로드, OpenAI/Ollama 비전 분석, 관리 UI
    ↓
Identifier (8001) — YOLO 탐지 → EfficientNet 임베딩 → Qdrant 검색 → 투표
    ↓
MySQL (결과 저장) + Qdrant (벡터 저장)
    ↓
Trainer (8002) — EfficientNet / LLM 파인튜닝 (LlamaFactory or MLX)
```

| 서비스 | 포트 | 역할 |
|--------|------|------|
| Studio | 8000 | 관리 UI, 데이터 라벨링, OpenAI Vision 분석, 파인튜닝 오케스트레이션 |
| Identifier | 8001 | 차량 식별 (동기/비동기), YOLO 탐지, EfficientNet 임베딩 |
| Trainer | 8002 | 모델 파인튜닝, LoRA 병합, GGUF 내보내기 |
| Qdrant | 6333 | 차량 이미지 임베딩(1280차원) 저장·검색 |
| Redis | 6379 | Celery 브로커, 비동기 결과 저장 (24h TTL) |
| Ollama | 11434 | Qwen3-VL:8b 로컬 VLM 서빙 |
| MySQL | 3306 | 제조사, 모델, 분석 이력 저장 (개발 환경) |

**식별 파이프라인 (Identifier, efficientnet 모드 기준):**
1. **YOLO26** — 차량 바운딩 박스 탐지 및 크롭
2. **EfficientNetV2-M** — 1280차원 특징 벡터 추출 후 분류
3. 신뢰도 ≥ 0.9 → 즉시 반환
4. 신뢰도 < 0.9 → **Qwen3-VL:8b** 폴백 추론

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
| `QDRANT_HOST` | `qdrant` | Qdrant 호스트 |
| `QDRANT_PORT` | `6333` | Qdrant 포트 |
| `EMBEDDING_DEVICE` | `cuda` | 임베딩 연산 장치 (`cuda` / `cpu`) |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |

### Studio (포트 8000)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `OPENAI_MODEL` | `gpt-5-mini` | OpenAI 비전 모델 |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini 교차 검증 모델 |
| `FUZZY_MATCH_THRESHOLD` | `80` | 퍼지 매칭 임계값 |
| `CONFIDENCE_THRESHOLD` | `0.8` | 식별 신뢰도 임계값 |
| `ANALYZED_VEHICLES_RETENTION_DAYS` | `30` | 분석 결과 보존 기간 (일) |

### Identifier (포트 8001)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `IDENTIFIER_MODE` | `efficientnet` | 식별 모드 (`efficientnet` / `visual_rag` / `vlm_only`) |
| `VLM_MODEL_NAME` | `qwen3-vl:8b` | Ollama VLM 모델명 |
| `IDENTIFIER_TOP_K` | `10` | Qdrant 후보 검색 수 |
| `IDENTIFIER_CONFIDENCE_THRESHOLD` | `0.80` | 식별 신뢰도 임계값 |
| `IDENTIFIER_MAX_BATCH_FILES` | `100` | 배치 최대 파일 수 |
| `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` | `104857600` | 배치 최대 업로드 크기 (100MB) |

---

## API

### Identifier (8001)

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| GET | `/health` | 서비스 상태 확인 |
| POST | `/detect` | YOLO 차량 탐지 (바운딩 박스 반환) |
| POST | `/identify` | 단일 이미지 동기 식별 |
| POST | `/async/identify` | 단일 이미지 비동기 식별 |
| POST | `/async/identify/batch` | 배치 비동기 식별 (최대 100장, 100MB) |
| GET | `/async/result/{task_id}` | 비동기 결과 조회 |

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

status 해석: `identified` — 신뢰할 수 있는 결과 / `low_confidence` — 후보 있음, 수동 확인 필요 / `no_match` — 유사 학습 데이터 없음

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

- `GET /` — 메인 분석 UI
- `GET /admin-ui` — 관리/리뷰 UI
- `GET /analyze-ui` — 차량 분석 UI (YOLO 탐지 + SSE 스트리밍)
- `GET /finetune-ui` — 파인튜닝 관리 UI
- `POST /api/analyze/vehicle` — OpenAI Vision 분석
- `POST /admin/analyze-batch` — 배치 분석

### Trainer (8002)

- `POST /train/start` — 파인튜닝 시작
- `GET /train/status` — 학습 진행 상태 (epoch, loss)
- `POST /train/stop` — 학습 중단
- `POST /train/export` — LoRA 병합 및 GGUF 내보내기
- `GET /hw-profile` — 하드웨어 감지 및 최적 파라미터 제안

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
- Qdrant 재인덱싱: `python3 .claude/index_qdrant.py --clear`
- 학습 데이터 결과: [docs/학습데이터결과서.md](docs/학습데이터결과서.md)
- 시스템 아키텍처 다이어그램: [docs/architecture.svg](docs/architecture.svg)
