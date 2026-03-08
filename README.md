# Reeve

차량 이미지에서 제조사와 모델을 자동 식별하는 시스템.

OpenAI Vision API로 차량을 1차 분석하고, 검수된 데이터를 벡터DB(Qdrant)에 CLIP 임베딩으로 축적하여 이미지 유사도 기반으로 판별하는 구조. 파인튜닝된 VLM(Ollama)을 활용한 재랭킹 모드도 지원.

---

## 아키텍처

```
┌──────────────┐     ┌──────────────────────────────────────────────┐
│   Frontend   │     │       Studio Service (개발/관리용 :8000)       │
│              │     │                                              │
│  analyze_v2  │────▶│  /api/*       차량 분석 API (DB-First)        │
│  admin UI    │────▶│  /admin/*     기준데이터 관리 / 검수 API       │
│  finetune UI │────▶│  /finetune/*  학습데이터 Export / 배포커맨드   │
│              │     │                                              │
└──────────────┘     │  Services:                                   │
                     │  ├─ openai_vision  Vision API 이미지 분석     │
                     │  ├─ matcher        코드매칭 + Fuzzy매칭        │
                     │  ├─ embedding      CLIP 이미지 임베딩          │
                     │  ├─ vectordb       Qdrant 벡터 검색           │
                     │  ├─ vehicle_detector  YOLO26 차량 감지        │
                     │  └─ llm_local      로컬 VLM (폐쇄망 옵션)     │
                     │                                              │
                     │  Tasks:                                      │
                     │  └─ cleanup  데이터 라이프사이클 관리          │
                     │     (APScheduler, 매일 자동 정리)             │
                     │                                              │
                     └──────────┬─────────────────┬────────────────┘
                                │                 │
                     ┌──────────▼──────┐  ┌───────▼────────┐
                     │   MySQL 8.0     │  │ Qdrant (latest)│
                     │                 │  │                │
                     │  manufacturers  │  │  training_     │
                     │  vehicle_models │  │    images      │
                     │  analyzed_      │  │  (CLIP 512d)   │
                     │    vehicles     │  │                │
                     │  training_      │  └───────┬────────┘
                     │    dataset      │          │
                     └─────────────────┘  ┌───────▼────────────────────────┐
                                          │  Identifier Service :8001      │
                                          │                                │
                                          │  CLIP 임베딩 + 투표 알고리즘    │
                                          │  배치/비동기 처리               │
                                          │  VLM 재랭킹 (visual_rag 모드)  │
                                          │                                │
                                          │  ┌──────┐ ┌───────┐ ┌───────┐ │
                                          │  │Redis │ │Celery │ │Ollama │ │
                                          │  │(큐)  │ │Worker │ │(VLM)  │ │
                                          │  └──────┘ └───────┘ └───────┘ │
                                          └────────────────────────────────┘
```

---

## 서비스 구성

| 서비스 | 포트 | 역할 | 의존성 |
|--------|------|------|--------|
| **Studio** | 8000 | 개발/관리 — OpenAI Vision 분석, 기준데이터 CRUD, 검수, 벡터DB 동기화, 학습데이터 Export | MySQL, Qdrant |
| **Identifier** | 8001 | 납품용 판별 — CLIP 임베딩 + Qdrant 유사도 검색 + 가중 투표, 동기/비동기 처리, VLM 지원 | Qdrant, Redis, (Ollama) |
| **Redis** | 6379 | Celery 브로커 + 결과 저장 (24시간) | — |
| **Celery Worker** | — | 비동기 배치 처리 워커 | Qdrant, Redis |
| **Ollama** | 11434 | 로컬 VLM 서버 — Qwen3-VL (운영: Docker+NVIDIA GPU, Mac 개발: Docker CPU 모드) | — |
| **LLaMA-Factory** | 7860 | VLM 파인튜닝 WebUI — QLoRA 4bit 학습 (운영: Docker+NVIDIA GPU, Mac 개발: Docker CPU) | — |

- Identifier는 MySQL에 접속하지 않음. 제조사/모델명은 Qdrant payload에 비정규화하여 저장.
- Studio에서 검수 승인한 데이터가 Qdrant에 축적되면, Identifier가 해당 벡터를 활용하여 판별.
- Identifier 판별 모드: `clip_only`(기본) / `visual_rag`(CLIP+VLM) / `vlm_only`.

---

## 핵심 워크플로우

### 1. 차량 이미지 분석 (Studio)

```
POST /api/upload — 파일 업로드 (DB-First)
  ↓
파일 검증 + data/uploads/YYYY-MM-DD/ 저장
  ↓
analyzed_vehicles 레코드 생성 (processing_stage='uploaded')
  ↓
POST /api/detect-vehicle — YOLO26 차량 감지 → 바운딩 박스 반환
  ↓
프론트에서 bbox 선택/편집
  ↓
POST /api/analyze-vehicle-stream — SSE 스트리밍 분석
  ↓
선택 bbox 크롭 → data/crops/YYYY-MM-DD/ 저장
  ↓
OpenAI Vision API (gpt-4o) → JSON 파싱 (manufacturer_code, model_code, confidence)
  ↓
기준 DB 매칭 (코드 정확매칭 → Fuzzy매칭 → 자동등록)
  ↓
analyzed_vehicles 업데이트 (is_verified=false, processing_stage='analysis_complete')
```

### 2. 관리자 검수 및 벡터DB 축적 (Studio)

```
리뷰 큐 조회 (/admin/review-queue)
  ↓
결과 확인 → 필요시 제조사/모델 수정
  ↓
승인 (is_verified = true)
  ↓
CLIP 이미지 임베딩 생성
  ↓
training_dataset 저장 + Qdrant training_images 컬렉션에 추가
  (payload에 제조사/모델 이름 포함)
  ↓
축적된 데이터로 Identifier 판별 정확도 향상
```

### 3. 차량 판별 (Identifier)

**동기 처리 (즉시 결과 반환):**
```
판별 이미지 업로드 (/identify 또는 /identify/batch)
  ↓
YOLO26으로 차량 감지 + 크롭 (배치: 전체 이미지 한번에)
  ↓
CLIP 임베딩 생성 (배치: 동시 인코딩)
  ↓
Qdrant training_images 검색 (배치: 병렬 검색)
  ↓
(제조사, 모델) 쌍별 가중 투표 집계
  ↓
적응형 신뢰도 계산 → 보정 필터 적용 → 판별 결과 반환
```

**판별 보정 필터:**
1. **투표 집중도 (Vote Concentration):** Top-K 결과에서 winner의 득표 비율이 임계값(기본 30%) 미만이면 `uncertain`으로 다운그레이드. 미학습 차량은 Top-K가 여러 차종으로 분산되어 집중도가 낮음.
2. **YOLO 미감지 패널티:** 차량 자동 감지 실패 시 전체 이미지(배경 포함)로 임베딩하므로 유사도가 높아도 `identified` 반환을 차단.

**비동기 처리 (CCTV 업체 대량 처리용):**
```
이미지 업로드 (/async/identify 또는 /async/identify/batch)
  ↓
즉시 task_id 반환 (<10ms)
  ↓
Redis 큐에 적재
  ↓
Celery Worker가 배치 처리
  ↓
결과를 Redis에 저장 (24시간)
  ↓
GET /async/result/{task_id}로 폴링하여 결과 조회
```

### 4. 데이터 라이프사이클 관리 (Studio)

```
APScheduler 스케줄러 시작 (앱 시작 시)
  ↓
매일 설정된 시간(기본 3시)에 cleanup 작업 실행
  ↓
cutoff_date = 현재 - RETENTION_DAYS(기본 30일) 계산
  ↓
조건: is_verified=false AND created_at < cutoff_date
  ↓
대상 레코드 조회 (미검수 + 오래된 데이터만)
  ↓
이미지 파일 삭제 (data/crops/*.jpg)
  ↓
DB 레코드 삭제 (analyzed_vehicles)
  ↓
테이블 크기 관리 → 쿼리 성능 유지
```

---

## 프로젝트 구조

```
reeve/
├── studio/                             # Studio 서비스 (개발/관리용)
│   ├── main.py                      #   FastAPI 앱 진입점 + APScheduler 통합
│   ├── config.py                    #   환경변수 설정 (Pydantic Settings)
│   ├── api/
│   │   ├── admin.py                 #   관리자 API (기준데이터 CRUD, 검수, 벡터DB 동기화)
│   │   │                            #     - N+1 쿼리 최적화 (joinedload)
│   │   │                            #     - Incremental sync (qdrant_id 기반)
│   │   │                            #     - 커서 기반 페이지네이션
│   │   ├── analyze.py               #   분석 API (이미지 분석, 차량 감지, SSE 스트리밍)
│   │   └── finetune.py              #   파인튜닝 API (학습데이터 Export, 배포 커맨드 생성)
│   ├── models/
│   │   ├── database.py              #   DB 연결 및 세션 관리
│   │   ├── manufacturer.py          #   제조사 ORM 모델
│   │   ├── vehicle_model.py         #   차량 모델 ORM 모델
│   │   ├── analyzed_vehicle.py      #   분석 결과 ORM 모델
│   │   └── training_dataset.py      #   학습 데이터 ORM 모델 (7 컬럼)
│   ├── services/
│   │   ├── openai_vision.py         #   OpenAI gpt-4o Vision API 연동
│   │   ├── matcher.py               #   코드매칭 + RapidFuzz 퍼지매칭
│   │   ├── embedding.py             #   CLIP 이미지 임베딩 (clip-ViT-B-32, 512d)
│   │   ├── vectordb.py              #   Qdrant 벡터DB (training_images 컬렉션)
│   │   ├── vehicle_detector.py      #   YOLO26 차량 감지
│   │   ├── image_utils.py           #   이미지 처리 유틸리티
│   │   └── llm_local.py             #   로컬 Vision LLM 서비스 (폐쇄망 환경용)
│   ├── tasks/
│   │   └── cleanup.py               #   데이터 라이프사이클 관리
│   │                                #     - cleanup_old_analyzed_vehicles()
│   │                                #     - get_cleanup_stats()
│   └── static/                      #   프론트엔드 UI
│       ├── index.html               #     관리자 UI (기초DB관리 탭 + 학습데이터추출 탭)
│       ├── analyze_v2.html          #     분석 UI — 메인 페이지 (/)
│       ├── finetune.html            #     파인튜닝 관리 UI (학습데이터 Export + 배포 커맨드)
│       ├── css/styles.css
│       └── js/
│           ├── app.js               #     관리자 UI 스크립트
│           └── analyze_v2.js        #     분석 UI 스크립트
├── identifier/                        # Identifier 서비스 (납품용 판별)
│   ├── main.py                      #   FastAPI 앱 진입점 (동기 + 비동기, OpenAPI 문서)
│   ├── config.py                    #   환경변수 설정 (Pydantic Settings)
│   ├── identifier.py                #   CLIP 유사도 + 투표 기반 차량 판별 (배치, 집중도/YOLO 보정)
│   ├── celery_app.py                #   Celery 앱 설정 (Redis 브로커)
│   ├── tasks.py                     #   Celery 태스크 (단일/배치 비동기 처리)
│   ├── start.sh                     #   uvicorn 시작 스크립트 (workers 자동 계산)
│   ├── start_worker.sh              #   Celery worker 시작 스크립트
│   └── static/
│       └── index.html               #   판별 UI
├── docker/
│   ├── docker-compose.yml           # 운영 베이스 (qdrant + identifier + redis + celery-worker + ollama + llamafactory, NVIDIA GPU)
│   ├── Dockerfile                   # Studio 컨테이너 이미지
│   ├── Dockerfile.identifier        # Identifier + Celery Worker 이미지
│   ├── studio/
│   │   ├── mac/                     # Mac 개발 환경 (ollama + llamafactory CPU 모드, mysql + studio 추가)
│   │   │   ├── docker-compose.mac.yml
│   │   │   └── setup.sh / start.sh / stop.sh
│   │   ├── linux/                   # Linux 개발 환경 (ollama + llamafactory NVIDIA GPU, mysql + studio 추가)
│   │   │   ├── docker-compose.linux.yml
│   │   │   └── setup.sh / start.sh / stop.sh
│   │   └── windows/                 # Windows 개발 환경 (ollama + llamafactory NVIDIA GPU, mysql + studio 추가)
│   │       ├── docker-compose.windows.yml
│   │       └── setup.bat / start.bat / stop.bat
│   └── identifier/
│       ├── linux/                   # 납품용 standalone — Linux (NVIDIA GPU)
│       │   ├── docker-compose.yml
│       │   ├── .env.example
│       │   └── setup.sh / start.sh / stop.sh
│       └── windows/                 # 납품용 standalone — Windows (NVIDIA GPU, Docker Desktop)
│           ├── docker-compose.yml
│           ├── .env.example
│           └── setup.bat / start.bat / stop.bat
├── deploy/                          # 납품 패키지 생성 스크립트
│   ├── package.sh                   #   Mac/Linux에서 실행 — OS별 패키지 아카이빙
│   └── package.bat                  #   Windows에서 실행 — OS별 패키지 아카이빙
├── docs/
│   └── ASYNC_USAGE.md               # 비동기 API 사용 가이드 (Python 클라이언트 예제 포함)
├── sql/
│   ├── user_provided_ddl.sql        # 테이블 DDL (training_dataset 단순화)
│   └── user_provided_dml.sql        # 초기 제조사/모델 데이터
├── data/                            # 런타임 데이터 (gitignored)
│   ├── uploads/YYYY-MM-DD/          #   업로드된 원본 이미지 (날짜별 분리)
│   ├── crops/YYYY-MM-DD/            #   크롭된 분석 이미지 (날짜별 분리)
│   └── temp/                        #   임시 파일 (차량 감지용, 처리 후 삭제)
├── logs/                            # 애플리케이션 로그 (RotatingFileHandler)
├── requirements.txt                 # Studio 의존성 (+ apscheduler)
├── requirements-identifier.txt      # Identifier 의존성 (celery, redis 포함)
└── .env.example                     # 환경변수 템플릿
```

---

## 실행 방법

### 사전 요구사항

| 환경 | 필수 |
|------|------|
| 공통 | Docker Desktop (Mac/Windows) 또는 Docker Engine (Linux) |
| Studio — Mac | Docker Desktop |
| Studio — Windows | Docker Desktop + NVIDIA Container Toolkit (WSL2) |
| Identifier — Linux | Docker Engine + NVIDIA Container Toolkit |
| Identifier — Windows | Docker Desktop + NVIDIA Container Toolkit (WSL2) |
| 공통 | OpenAI API Key (Studio 서비스용) |

### 1. Studio 개발 환경

#### Mac (ollama + llamafactory CPU 모드)

```bash
# 최초 1회 — .env 생성 + 이미지 빌드
cd docker
./studio/mac/setup.sh

# 이후 시작 / 중지
./studio/mac/start.sh
./studio/mac/stop.sh
```

`.env` 필수 수정 항목:

```env
OPENAI_API_KEY=sk-your-api-key-here
MYSQL_ROOT_PASSWORD=your_root_password
MYSQL_PASSWORD=your_password
```

#### Windows (ollama + llamafactory NVIDIA GPU)

```bat
REM 최초 1회 — .env 생성 + 이미지 빌드
cd docker
studio\windows\setup.bat

REM 이후 시작 / 중지
studio\windows\start.bat
studio\windows\stop.bat
```

#### Linux (ollama + llamafactory NVIDIA GPU)

```bash
# 최초 1회 — .env 생성 + 이미지 빌드
cd docker
./studio/linux/setup.sh

# 이후 시작 / 중지
./studio/linux/start.sh
./studio/linux/stop.sh
```

### 2. Studio 서비스 목록

| 서비스 | 컨테이너 | 포트 | Mac | Linux | Windows |
|--------|----------|------|-----|-------|---------|
| studio | reeve-studio | 8000 | ✅ | ✅ | ✅ |
| mysql | reeve-mysql | 3306 | ✅ | ✅ | ✅ |
| qdrant | reeve-qdrant | 6333, 6334 | ✅ | ✅ | ✅ |
| identifier | reeve-identifier | 8001 | ✅ | ✅ | ✅ |
| redis | reeve-redis | 6379 | ✅ | ✅ | ✅ |
| celery-worker | reeve-celery-worker | — | ✅ | ✅ | ✅ |
| ollama | reeve-ollama | 11434 | CPU 모드 | NVIDIA GPU | NVIDIA GPU |
| llamafactory | reeve-llamafactory | 7860 | CPU 모드 | NVIDIA GPU | NVIDIA GPU |

### 3. Identifier 납품 환경 (Linux, NVIDIA GPU)

고객사 납품 시 OS에 맞는 `docker/identifier/linux/` 또는 `docker/identifier/windows/` 폴더를 전달합니다.

**Linux:**
```bash
cd docker/identifier/linux
./setup.sh    # 이미지 로드 + Qdrant 스냅샷 복원 + Ollama 모델 등록 (최초 1회)
./start.sh
./stop.sh
```

**Windows:**
```bat
cd docker\identifier\windows
setup.bat     REM 이미지 로드 + Qdrant 스냅샷 복원 + Ollama 모델 등록 (최초 1회)
start.bat
stop.bat
```

납품 패키지 구성:

```
docker/identifier/linux/
├── docker-compose.yml
├── .env.example
├── setup.sh / start.sh / stop.sh
├── snapshots/
│   └── training_images_*.snapshot   # Studio에서 export한 Qdrant 스냅샷
└── models/
    ├── Modelfile
    └── vehicle-vlm-v1.gguf          # 파인튜닝된 모델
```

납품용 서비스 목록:

| 서비스 | 컨테이너 | 포트 | 설명 |
|--------|----------|------|------|
| qdrant | reeve-qdrant | 6333, 6334 | 학습 벡터DB |
| identifier | reeve-identifier | 8001 | 차량 판별 API |
| redis | reeve-redis | 6379 | Celery 브로커 |
| celery-worker | reeve-celery-worker | — | 비동기 배치 처리 |
| ollama | reeve-ollama | 11434 | 파인튜닝 VLM (NVIDIA GPU) |

### 4. 접속 URL (Studio 개발 환경)

| URL | 설명 |
|-----|------|
| http://localhost:8000/ | 분석 UI — 메인 (차량감지 + SSE) |
| http://localhost:8000/admin-ui | 관리자 UI (기초DB관리 / 학습데이터추출 탭) |
| http://localhost:8000/docs | Studio Swagger API 문서 |
| http://localhost:8001/ | 판별 UI |
| http://localhost:8001/docs | Identifier Swagger API 문서 |
| http://localhost:6333/dashboard | Qdrant 대시보드 |
| http://localhost:7860 | LLaMA-Factory WebUI (파인튜닝) |
| http://localhost:11434 | Ollama API |

---

## API 엔드포인트

### Studio 시스템 (`/`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/` | 분석 UI (analyze_v2.html) |
| GET | `/admin-ui` | 관리자 UI (index.html) |
| GET | `/analyze-ui` | 분석 UI (analyze_v2.html, 동일) |
| GET | `/health` | 헬스체크 (DB, Qdrant 연결 상태) |

### 분석 API — Studio (`/api`)

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/upload` | 파일 업로드 → DB 레코드 생성 (DB-First, processing_stage='uploaded') |
| POST | `/api/detect-vehicle` | YOLO26 차량 감지 (바운딩 박스 반환) |
| POST | `/api/analyze-vehicle-stream` | SSE 스트리밍 분석 (bbox 크롭 → gpt-4o → DB 저장) |
| POST | `/api/analyze/vehicle` | 단순 분석 (업로드+분석 통합, 레거시 호환) |
| GET | `/api/vehicle/{id}` | 분석 결과 조회 |
| GET | `/api/pending-records` | 미검수 레코드 페이지네이션 조회 |
| GET | `/api/analyze-feed` | 실시간 분석 피드 SSE (3초 간격 업데이트) |

### 관리자 API — Studio (`/admin`)

**기준 데이터 관리**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin/manufacturers` | 제조사 목록 (is_domestic 필터, 페이지네이션) |
| GET | `/admin/manufacturers/{id}` | 제조사 상세 |
| POST | `/admin/manufacturers` | 제조사 등록 (code 중복 체크) |
| GET | `/admin/vehicle-models` | 차량 모델 목록 (manufacturer_id 필터) |
| GET | `/admin/vehicle-models/{id}` | 차량 모델 상세 |
| POST | `/admin/vehicle-models` | 차량 모델 등록 |

**검수**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/admin/review-queue` | 미검수 목록 (커서 기반 페이지네이션) |
| GET | `/admin/analyzed-vehicles-pending` | 미검수 레코드 전체 목록 |
| PATCH | `/admin/review/{id}` | 제조사/모델 수정 |
| PUT | `/admin/review/{id}` | 승인/거부 (승인 시 CLIP 임베딩 + Qdrant 저장) |
| POST | `/admin/review/{id}` | 벡터DB 직접 저장 (training_dataset + Qdrant) |
| POST | `/admin/review/batch-save-all` | 미검수 전체 일괄 저장 (SSE 스트리밍, 커서 페이지네이션) |
| DELETE | `/admin/review/{id}` | 분석 결과 삭제 (크롭 + 원본 이미지 파일 + DB 레코드) |
| DELETE | `/admin/review-delete-all` | 미검수 전체 일괄 삭제 (단일 SQL, 이미지 파일 포함) |

**분석/동기화**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/admin/analyze/{id}` | 단일 이미지 재분석 (Vision API 재호출) |
| POST | `/admin/analyze-batch` | 디렉토리 이미지 일괄 분석 |
| POST | `/admin/sync-vectordb` | 벡터DB Incremental 동기화 (qdrant_id IS NULL 레코드만) |
| GET | `/admin/vectordb-stats` | 벡터DB 통계 (총 벡터 수, 컬렉션 상태) |
| GET | `/admin/db-stats` | DB 통계 및 자동 정리 대상 미리보기 |

**데이터 관리**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/admin/cleanup-now` | 오래된 미검수 데이터 수동 정리 (즉시 실행) |

### 파인튜닝 API — Studio (`/finetune`)

| Method | Path | 설명 |
|--------|------|------|
| GET | `/finetune/stats` | 학습 데이터 통계 (총 레코드 수, 제조사별 분포) |
| GET | `/finetune/export/preview` | Export 미리보기 (필터 기준 총 건수 + 페이지 수) |
| POST | `/finetune/export` | Export 실행 → `data/finetune/` 에 저장 (sharegpt 형식, 페이징 지원) |
| GET | `/finetune/deploy/cmd` | 체크포인트 → Ollama 배포 커맨드 목록 생성 |

### 판별 API — Identifier (`:8001`)

**동기 처리**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/health` | 서비스 상태 (CLIP 모델, Qdrant 연결, 학습 데이터 수) |
| POST | `/detect` | YOLO26 차량 감지만 (바운딩 박스 반환) |
| POST | `/identify` | 이미지 업로드 → CLIP 임베딩 → 투표 → 판별 결과 |
| POST | `/identify/batch` | 배치 판별 (최대 100개, 100MB) — YOLO/CLIP/Qdrant 배치 처리 |

**비동기 처리 (Celery)**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/async/identify` | 단일 이미지 비동기 판별 → task_id 즉시 반환 |
| POST | `/async/identify/batch` | 배치 비동기 판별 → task_id 즉시 반환 |
| GET | `/async/result/{task_id}` | 작업 결과 조회 (PENDING/STARTED/SUCCESS/FAILURE) |

> 비동기 API 상세 사용법: `docs/ASYNC_USAGE.md`

---

## DB 스키마

```
manufacturers (제조사)
├── id, code(UK), english_name, korean_name, is_domestic
│
├──< vehicle_models (차량 모델)
│   └── id, code, manufacturer_id(FK), manufacturer_code, english_name, korean_name
│
├──< analyzed_vehicles (분석 결과)
│   └── id, image_path, original_image_path, source, client_uuid
│       raw_result(JSON), manufacturer, model, year
│       matched_manufacturer_id(FK), matched_model_id(FK)
│       confidence_score, is_verified, verified_by, verified_at, notes
│       processing_stage, yolo_detections(JSON), selected_bbox(JSON)
│
└──< training_dataset (학습 데이터) ⚡ 단순화: 9개 → 7개 컬럼
    └── id, image_path(UK), manufacturer_id(FK), model_id(FK)
        qdrant_id, created_at, updated_at
```

### training_dataset 최적화

**제거된 컬럼:**
- `embedding_vector` (JSON, 512 floats) → Qdrant에만 저장 (중복 제거)
- `extra_metadata` (JSON) → Qdrant payload로 이동
- `analyzed_vehicle_id` (FK) → 역정규화 제거

**효과:**
- 행당 크기: ~9KB → ~0.5KB (94% 절약)
- 1000만 건 기준: ~85GB 절약
- Qdrant를 Single Source of Truth로 사용

---

## 벡터DB (Qdrant)

| 컬렉션 | 벡터 차원 | 임베딩 모델 | 용도 |
|---------|-----------|------------|------|
| training_images | 512 | clip-ViT-B-32 | 학습 이미지 유사도 검색 |

payload에 제조사/모델 이름을 비정규화하여 저장 (`manufacturer_korean`, `manufacturer_english`, `model_korean`, `model_english`). Identifier 서비스가 MySQL 없이 판별 결과를 반환할 수 있도록 하기 위함.

---

## 성능 최적화

### 1. YOLO26n 업그레이드

**변경:** YOLOv8m → YOLO26n (`ultralytics>=8.4.0`)

| 항목 | YOLOv8m | YOLO26n |
|------|---------|---------|
| 모델 크기 | 50MB | 6MB |
| CPU 추론 | 기준 | **43% 향상** |
| 아키텍처 | NMS 포함 | NMS-free |

### 2. Identifier 배치 처리

단일 요청 10개 → 배치 요청 1개 비교:

| 단계 | 단일×10 | 배치×10 | 절약 |
|------|---------|---------|------|
| YOLO | 10회 개별 실행 | 1회 배치 실행 | ~60% |
| CLIP | 10회 개별 인코딩 | 1회 배치 인코딩 | ~50% |
| Qdrant | 10회 개별 검색 | 1회 배치 검색 | ~70% |

### 3. uvicorn 멀티 워커 자동 계산

```
workers = CPU 코어 수(논리) ÷ IDENTIFIER_TORCH_THREADS
예) 128코어(HT) ÷ 8스레드 = 16 workers
예) 8코어(개발) ÷ 8스레드 = 1 worker (자동)
```

`.env`에 `IDENTIFIER_TORCH_THREADS`만 지정하면 start.sh에서 자동 계산.

### 4. CLIP 모델 최적화

- `torch.set_num_threads(N)` — PyTorch 연산 스레드 제한
- `torch.compile()` — JIT 컴파일 (PyTorch 2.0+, 10-20% 향상)
- 입력 이미지 최대 800px 리사이즈 (CLIP 내부: 224×224)

### 5. 비동기 큐 (Celery + Redis)

| 항목 | 동기 API | 비동기 API |
|------|----------|-----------|
| 응답 시간 | 처리 완료까지 대기 | **즉시 (<10ms)** |
| 동시 처리 | workers 수 제한 | **큐 무제한** |
| 재시도 | 없음 | **자동 3회 (exponential backoff)** |
| 결과 보관 | 없음 | **24시간 (Redis)** |
| 급격한 트래픽 | 부하 집중 | **큐 버퍼링** |

### 6. N+1 쿼리 제거 (Studio)

```python
# Before (N+1 쿼리)
for data in batch:
    mfr = db.query(Manufacturer).filter(...).first()  # N번 쿼리

# After (JOIN)
batch = db.query(Model).options(
    joinedload(Model.manufacturer),
    joinedload(Model.model)
).all()  # 1번 쿼리
```

**효과:** 배치당 200개 → 1개 쿼리 (-99.5%)

### 7. Incremental Sync (Studio)

```python
batch = db.query(TrainingDataset).filter(
    TrainingDataset.id > last_id,
    TrainingDataset.qdrant_id.is_(None)  # 미동기화만
).limit(BATCH_SIZE).all()
```

**효과:** sync-vectordb 재실행 시 310시간 → 0초

### 8. 커서 기반 페이지네이션 (Studio)

`OFFSET/LIMIT` 대신 `WHERE id > last_id`로 일정한 쿼리 성능 보장.

---

## 환경변수

`.env.example` 참조. 섹션별 구성:

**공통 (Common):**
- `QDRANT_HOST`, `QDRANT_PORT`, `EMBEDDING_DEVICE`
- `MAX_UPLOAD_SIZE`, `ALLOWED_EXTENSIONS`
- `LOG_LEVEL`, `STUDIO_LOG_FILE`, `IDENTIFIER_LOG_FILE`

**Studio:**
- `STUDIO_PORT`, `ENVIRONMENT`
- `MYSQL_*` (연결 정보)
- `OPENAI_API_KEY`
- `FUZZY_MATCH_THRESHOLD`, `CONFIDENCE_THRESHOLD`
- `ANALYZED_VEHICLES_RETENTION_DAYS`, `CLEANUP_ENABLED`, `CLEANUP_HOUR`

**Identifier:**
- `IDENTIFIER_PORT` — 기본 8001
- `IDENTIFIER_TOP_K` — Qdrant 검색 결과 수 (기본 10)
- `IDENTIFIER_CONFIDENCE_THRESHOLD` — 최소 신뢰도 (기본 0.80)
- `IDENTIFIER_MIN_SIMILARITY` — 최소 코사인 유사도 (기본 0.3)
- `IDENTIFIER_VOTE_THRESHOLD` — 신뢰 판별을 위한 최소 투표 수 (기본 3)
- `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD` — Top-K 중 winner 득표 비율 임계값 (기본 0.3 = 30%)
- `IDENTIFIER_VEHICLE_DETECTION` — YOLO 차량 감지 활성화 (기본 true)
- `IDENTIFIER_REQUIRE_VEHICLE_DETECTION` — YOLO 미감지 시 identified 반환 차단 (기본 false, YOLO 패널티와 별개)
- `IDENTIFIER_YOLO_CONFIDENCE` — YOLO 탐지 신뢰도 임계값 (기본 0.25)
- `IDENTIFIER_CROP_PADDING` — bbox 주변 여백 픽셀 (기본 10)
- `IDENTIFIER_TORCH_THREADS` — PyTorch 스레드 수 (workers 자동 계산에 사용)
- `IDENTIFIER_BATCH_SIZE` — 내부 배치 처리 크기 (기본 32)
- `IDENTIFIER_MAX_BATCH_FILES` — 배치 API 최대 파일 수 (기본 100)
- `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` — 배치 API 최대 전체 크기 (기본 100MB)
- `IDENTIFIER_ENABLE_TORCH_COMPILE` — torch.compile JIT 활성화 (기본 true)

**Identifier VLM:**
- `IDENTIFIER_MODE` — `clip_only` / `visual_rag` / `vlm_only` (기본: clip_only)
- `OLLAMA_BASE_URL` — Ollama 서버 주소 (기본: http://localhost:11434)
- `VLM_MODEL_NAME` — Ollama 모델명 (기본: vehicle-vlm-v1)
- `VLM_TIMEOUT` — VLM 요청 타임아웃 초 (기본: 30)
- `VLM_MAX_CANDIDATES` — visual_rag 모드 VLM에 전달할 후보 수 (기본: 5)
- `VLM_FALLBACK_TO_CLIP` — VLM 실패 시 CLIP 결과로 폴백 (기본: true)
- `VLM_BATCH_CONCURRENCY` — 배치 처리 시 VLM 동시 호출 수 (기본: 2)

**Redis / Celery:**
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB`
- `CELERY_TASK_TIME_LIMIT` — 태스크 최대 실행 시간 (기본 600초)
- `CELERY_TASK_SOFT_TIME_LIMIT` — 소프트 타임아웃, 정상 종료 신호 (기본 540초)
- `CELERY_MAX_RETRIES` — 실패 시 재시도 횟수 (기본 3)

---

## 리소스 제한 (Docker)

| 서비스 | CPU | Memory | 비고 |
|--------|-----|--------|------|
| studio | 2.0 cores (min 0.5) | 2GB (min 512MB) | 개발 환경 전용 |
| mysql | 2.0 cores (min 0.5) | 2GB (min 512MB) | 개발 환경 전용 |
| qdrant | 1.0 core (min 0.25) | 2GB (min 256MB) | 운영/개발 공통 |
| identifier | 2.0 cores (min 0.5) | 2GB (min 1GB) | 운영/개발 공통 |
| redis | 0.5 core | 512MB | 운영/개발 공통 |
| celery-worker | 4.0 cores (min 2.0) | 4GB (min 2GB) | 운영/개발 공통 |
| ollama | — (NVIDIA GPU) | 16GB | 운영: NVIDIA GPU; Mac: CPU 8GB |
| llamafactory | — (NVIDIA GPU) | 32GB | 운영: NVIDIA GPU; Mac: CPU 8GB |

---

## 데이터 라이프사이클 관리

**목적:** 미검수 상태로 오래 방치된 데이터 자동 삭제

**동작:**
- APScheduler로 매일 설정된 시간(기본 3시)에 실행
- 삭제 조건: `is_verified=false AND created_at < (현재 - RETENTION_DAYS)`
- 이미지 파일도 함께 삭제 (`data/crops/YYYY-MM-DD/`, `data/uploads/YYYY-MM-DD/`)

**설정 (.env):**
```bash
ANALYZED_VEHICLES_RETENTION_DAYS=30  # 보관 기간 (일)
CLEANUP_ENABLED=true                 # 자동 정리 활성화
CLEANUP_HOUR=3                       # 실행 시간 (0-23)
```

**수동 실행:**
```bash
curl -X POST http://localhost:8000/admin/cleanup-now
```

---

## 향후 확장 (데이터 1000만 건 이상 시)

### 1. Partitioning (created_at 기준)
```sql
ALTER TABLE training_dataset PARTITION BY RANGE (YEAR(created_at)) (
    PARTITION p2024 VALUES LESS THAN (2025),
    PARTITION p2025 VALUES LESS THAN (2026),
    ...
);
```

### 2. Read Replica
- Master: 쓰기 (batch-save-all)
- Replica: 읽기 (sync-vectordb, stats)

### 3. Retention Policy 강화
- training_dataset도 2년 이상 데이터 아카이브
- 테이블 크기 제한으로 성능 유지

---

## 주요 업데이트 이력

### 2026-03-09

**배포 패키지 구조 정비 및 환경변수 통합**

- **`docker/studio/linux/` 추가**: Linux NVIDIA GPU 환경 Studio 개발 패키지 (setup.sh / start.sh / stop.sh + docker-compose.linux.yml)
- **`deploy/package.sh` / `deploy/package.bat` 추가**: OS별 납품 패키지 아카이빙 스크립트. studio-mac/linux/windows 및 identifier-linux/windows 패키지를 deploy/ 하위에 생성. Identifier 패키지는 Docker 이미지 tar.gz + Qdrant 스냅샷 + Ollama 모델 포함
- **`.env.example` 전면 보완**: Identifier 섹션에 누락된 설정 일괄 추가 — `IDENTIFIER_MODE`, `OLLAMA_BASE_URL`, `VLM_*` (전체), `IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD`, `IDENTIFIER_CROP_PADDING`, `IDENTIFIER_VEHICLE_DETECTION`, 성능 설정(`IDENTIFIER_TORCH_THREADS` 등), Redis/Celery 설정 완전 포함
- **`docker/identifier/{linux,windows}/.env.example` 동기화**: `IDENTIFIER_PORT`, `IDENTIFIER_VEHICLE_DETECTION`, `IDENTIFIER_CROP_PADDING`, `VLM_MAX_CANDIDATES`, `VLM_BATCH_CONCURRENCY`, `IDENTIFIER_MAX_BATCH_UPLOAD_SIZE` 추가
- **전체 bind mount 전환**: docker-compose 파일에서 named volume 제거 → `../data/*` 상대 경로 bind mount로 통일 (개발/납품 환경 모두 데이터 위치 명시)
- **Ollama Docker 전환**: Mac 개발 환경에서도 ollama를 Docker CPU 모드로 실행 (기존 네이티브 ollama 의존성 제거). `docker-compose.override.yml` 삭제 → OS별 override 파일로 완전 분리

### 2026-03-08

**파인튜닝 파이프라인 개선 — LLaMA-Factory WebUI 전용 + QLoRA 4bit**

- **finetune.py train 엔드포인트 제거**: `/train/start`, `/train/stop`, `/train/status`, `/train/logs` 삭제. 학습은 LLaMA-Factory WebUI(port 7860)에서 전담
- **Export 방식 변경**: 파일 다운로드 → `data/finetune/` 디렉토리에 직접 저장. `vehicle_train.json`, `vehicle_val.json` (sharegpt 배열 형식) + `dataset_info.json` (LLaMA-Factory 메타데이터) 자동 생성 → WebUI에서 데이터셋 수동 등록 불필요
- **deploy/cmd에 LoRA 병합 단계 추가**: QLoRA 체크포인트는 base model과 병합 후 GGUF 변환 필요. `llamafactory-cli export`로 병합 → GGUF → Ollama 6단계 커맨드 생성
- **LLaMA-Factory Docker 개발 환경 추가**: Mac/Windows 개발 환경에서 Docker로 llamafactory 실행 가능. Mac은 CPU 모드(NVIDIA 제외, 8G RAM), Windows는 NVIDIA GPU 사용
- **QLoRA 4bit 학습 방향 확정**: RTX 4060(8GB VRAM)에서 Qwen3-VL-8B 파인튜닝 가능. WebUI에서 `Quantization bit: 4` 설정
- **SQL 마이그레이션 DDL 통합**: `migration_add_processing_stage.sql`, `migration_add_source_client_uuid.sql`의 ALTER TABLE을 `user_provided_ddl.sql` CREATE TABLE에 병합. 별도 마이그레이션 파일 불필요
- **Export 프롬프트 정렬**: `finetune.py` Export 학습 데이터 프롬프트를 `vlm_service.py`의 `_build_freeform_prompt()` 형식과 통일 (JSON 출력 형식, reasoning 필드 제거). 학습-추론 프롬프트 일관성 확보
- **`scripts/` 디렉토리 삭제**: `scripts/export_training_data.py` (컬럼명 오류, 구식 프롬프트 형식) 삭제. `POST /finetune/export`로 완전 대체

### 2026-03-07

**파인튜닝 파이프라인 통합 및 VLM 지원**

- **파인튜닝 API** (`studio/api/finetune.py`): 학습 데이터 Export(LLaMA-Factory sharegpt 형식, 페이징), 학습 프로세스 관리(subprocess + SSE 로그), Ollama 배포 커맨드 생성
- **관리자 UI 개편** (`/admin-ui`): "기초DB관리" / "학습데이터추출" 2탭 구조로 통합. 학습데이터추출 탭에서 Export + LLaMA-Factory WebUI 링크 제공
- **메인 페이지 변경**: `GET /` → 이미지 분석 UI (analyze_v2.html)로 매핑
- **Docker에 Ollama + LLaMA-Factory 추가**: 전 환경에서 Docker로 구동. Mac은 CPU 모드, Windows/Linux는 NVIDIA GPU 사용
- **Identifier VLM 지원** (`identifier_mode`): `clip_only` / `visual_rag` / `vlm_only` 선택 가능. Ollama(`qwen3-vl:8b`) 연동
- **Ollama 컨텍스트 최적화**: `num_ctx 4096`으로 메모리 사용량 절감 (128K 기본값 시 ~46GB → ~6GB)
- **Docker Compose 구조 개편**: `docker-compose.override.yml` 제거 → `docker/studio/mac/`, `docker/studio/windows/`, `docker/identifier/linux/` OS별 디렉토리로 분리. `identifier`, `celery-worker`의 `depends_on: ollama` 제거

### 2026-02-22

**Identifier 판별 보정 및 OpenAPI 문서**

- **투표 집중도 보정 (Vote Concentration):** Top-K 결과에서 winner 득표 비율 < 30% 시 `uncertain` 강제. 미학습 차량의 false positive 방지 (`IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD`)
- **YOLO 미감지 패널티:** 차량 자동 감지 실패 시 전체 이미지로 판별한 결과는 `identified` 반환 차단
- **OpenAPI 문서 강화:** 앱 메타데이터(판별 방식, 엔드포인트 가이드, 신뢰도 해석표, 파일 요구사항), 태그 정의(Health/Detection/Identification/Async), 엔드포인트별 상세 설명(처리 흐름, 폴링 가이드라인), Pydantic Field 설명 추가
- **Pydantic 모델 Field 설명:** identifier.py의 모든 응답 모델 필드에 description 추가 — Swagger UI에서 필드별 의미 표시

**분석 UI 개선 및 파일 관리 정책 수정**

- **Stats bar 세분화**: 4개 → 5개 항목 (전체 이미지 / 차량 감지 완료 / 차량 감지 실패 / OpenAI 분석 완료 / OpenAI 분석 실패)
  - status 값 분리: `no_vehicle` (차량 미감지), `detection_error` (API 오류), `analysis_error` (OpenAI 오류)
  - 차량 감지 실패 이미지는 일괄 분석 대상에서 자동 제외
- **일괄 분석 완료 UX**: 분석 완료 시 "새 이미지 업로드하기" 버튼 표시 → 클릭 시 페이지 새로고침
- **날짜별 디렉토리 저장**: `data/uploads/YYYY-MM-DD/`, `data/crops/YYYY-MM-DD/` 구조로 변경
- **전체 일괄 삭제 개선**:
  - `DELETE /admin/review-delete-all` 추가 — 단일 SQL 쿼리로 전체 삭제 (개별 N회 API 호출 → 1회)
  - 개별 삭제 시 크롭 이미지 외 원본 업로드 파일(`raw_result.original_image`)도 함께 삭제
- **Qdrant 버전**: `v1.13.2` → `latest`

### 2026-02-18

**Identifier 성능 최적화**

- **YOLO26n 업그레이드**: YOLOv8m → YOLO26n (43% CPU 속도 향상, 모델 크기 50MB→6MB)
- **배치 처리**: `/identify/batch` 엔드포인트 추가 — YOLO/CLIP/Qdrant 전 단계 배치 실행
- **비동기 큐**: Celery + Redis 기반 비동기 처리 (`/async/identify`, `/async/identify/batch`, `/async/result/{task_id}`)
- **uvicorn 멀티워커**: `IDENTIFIER_TORCH_THREADS` 기반 workers 자동 계산 (`start.sh`)
- **CLIP 최적화**: `torch.compile()`, 이미지 800px 리사이즈, 스레드 제한

### 2026-02-05

**P0: embedding_vector 컬럼 제거 + 대량 쿼리 최적화**
- training_dataset에서 embedding_vector (JSON) 제거 → Qdrant를 Single Source of Truth로
- 커서 기반 페이지네이션 적용 (sync-vectordb, batch-save-all)
- 1000만 건 기준 ~85GB 절약, OOM 방지

**P1.1: 자동 정리 스케줄러**
- APScheduler 통합 (매일 지정 시간 자동 실행)
- 30일 이상 미검수 데이터 자동 삭제
- 환경변수: ANALYZED_VEHICLES_RETENTION_DAYS, CLEANUP_ENABLED, CLEANUP_HOUR

**P1.2: training_dataset 단순화**
- 9개 컬럼 → 7개 컬럼 (extra_metadata, analyzed_vehicle_id 제거)
- 행당 크기: ~9KB → ~0.5KB (94% 절약)

**즉시 적용 최적화**
- N+1 쿼리 제거 (joinedload): 배치당 200개 → 1개 쿼리
- Incremental sync: qdrant_id IS NULL 조건 추가
- sync-vectordb 재실행: 310시간 → 0초
