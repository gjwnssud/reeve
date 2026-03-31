# 별첨2 — AI솔루션 세부 설명자료 (Reeve)

---

## AI 솔루션명

**Reeve** — AI 기반 차량 제조사/모델 자동 식별 시스템

---

## AI 솔루션 종류

- [x] **설치형 AI 솔루션** (기업 자체 웹 서비스 솔루션)

---

## AI 솔루션 활용 분야

**①컴퓨터비전** — 이미지 Detection (YOLO 기반 차량 탐지) + Classification (EfficientNet-B3 임베딩 + 파인튜닝된 Qwen3-VL 기반 차량 제조사/모델 식별)

---

## 데이터 보유·수집 현황

| 데이터 종류 | 데이터 개수 | 데이터 상세 내용 |
|------------|------------|----------------|
| 차량 이미지 데이터 (학습용) | Qdrant `training_images` 컬렉션 내 보유 벡터 수 기준 | 관리자 검수 완료된 차량 이미지. 제조사·모델 레이블 포함. EfficientNet-B3 1536d 임베딩으로 변환하여 저장 |
| 차량 제조사/모델 메타데이터 | MySQL `manufacturers`, `vehicle_models` 테이블 | 제조사 코드·한/영 명칭, 모델 코드·한/영 명칭, 국산/수입 구분 |
| 분석 원본 이미지 | MySQL `analyzed_vehicles` 테이블 연계 | CCTV·촬영 이미지. OpenAI Vision 분석 결과 및 YOLO bbox 좌표 포함 |
| 파인튜닝 학습 데이터 | `data/finetune/` 디렉터리 | LLaMA-Factory ShareGPT 형식 JSON (`vehicle_train.json`, `vehicle_val.json`). 검수 완료 데이터에서 자동 생성 |

---

## 사용 프레임워크

| 구분 | 프레임워크 / 라이브러리 | 버전 | 용도 |
|------|------------------------|------|------|
| 딥러닝 | **PyTorch** | 2.6.0 | EfficientNet-B3 추론, torch.compile JIT 최적화 |
| 이미지 임베딩 | **timm / EfficientNet-B3** | — | EfficientNet-B3 1536d 벡터 추출 |
| 객체 탐지 | **Ultralytics YOLO26** | ≥8.4.0 | 차량 Bounding Box 탐지·크롭 |
| Vision LLM | **Ollama + Qwen3-VL:8b** | latest | 파인튜닝 모델 로컬 서빙, 최종 차량 판정 |
| LLM 파인튜닝 | **LLaMA-Factory** | latest | QLoRA 4bit 파인튜닝 → LoRA Merge → GGUF 변환 |
| Vision API | **OpenAI gpt-5.2** | — | 초기 차량 분석 (Studio 전용) |
| 벡터 DB | **Qdrant** | latest | 코사인 유사도 벡터 검색, on-disk 저장 |
| API 서버 | **FastAPI** | 0.115.12 | REST API, SSE 스트리밍, OpenAPI 문서 |
| 비동기 큐 | **Celery + Redis** | — | 배치 식별 비동기 처리, 결과 24h 보관 |
| DB ORM | **SQLAlchemy** | 2.0.36 | MySQL 8.0 연동 (sync + async 엔진) |
| 퍼지 매칭 | **RapidFuzz** | 3.14.3 | 차량 코드 DB 매칭 (threshold 80) |

---

## 사용 아키텍처

**Foundation Model 기반 + 파인튜닝된 VLM(Qwen3-VL) 최종 판정 커스텀 아키텍처 (`visual_rag` 모드)**

> ※ 사용된 Foundation Model
> - **EfficientNet-B3** — timm, ImageNet 사전학습, 이미지 임베딩
> - **YOLO26** — Ultralytics, COCO 사전학습, 차량 탐지
> - **Qwen3-VL:8b** — Qwen 사전학습 기반, LLaMA-Factory QLoRA 파인튜닝 후 Ollama 배포, **최종 차량 판정**

### 동작원리

차량 이미지를 입력받아 **① YOLO26**(사전학습 Foundation Model)이 차량 Bounding Box를 탐지·크롭하고, **② EfficientNet-B3**(사전학습 Foundation Model)로 1536차원 이미지 임베딩을 추출한다. **③ Qdrant** 벡터 DB에서 코사인 유사도 기준 Top-K 검색 후 자체 개발한 집계 레이어가 상위 후보 N개를 선별하여, **④ 파인튜닝된 Qwen3-VL:8b**에 크롭 이미지와 후보 목록을 함께 전달해 최종 차량 제조사/모델을 판정한다.

| 단계 | 구성 요소 | 유형 |
|------|-----------|------|
| ① 차량 탐지 | YOLO26 | Foundation Model (사전학습) |
| ② 임베딩 추출 | EfficientNet-B3 | Foundation Model (사전학습) |
| ③ 후보 검색·집계 | Qdrant Top-K + Voting Layer | 자체 개발 |
| ④ **최종 판정** | **Qwen3-VL:8b (파인튜닝)** | Foundation Model + Fine-tuning |

### 오탐 방지 장치

- YOLO 미탐지 시 `identified` → `uncertain` 자동 하향
- VLM 실패 시 Voting Layer 결과로 자동 폴백 (`VLM_FALLBACK_TO_EMBEDDING=true`)

---

## 학습데이터 결과서 / 테스트데이터 결과서

보유 중인 학습 데이터를 활용하여 아래 지표 기준으로 테스트 결과 작성.

| 평가 지표 | 설명 | 적용 대상 |
|-----------|------|-----------|
| **Accuracy** | 전체 식별 요청 중 정답 비율 | 전체 차량 제조사/모델 분류 |
| **Confidence Score** | VLM 판정 신뢰도 (0.0~1.0, 임계값 0.80) | 개별 식별 결과 |
| **Recall** | 실제 차량 이미지 중 탐지 성공 비율 | YOLO26 차량 탐지 단계 |
| **mAP** (mean Average Precision) | YOLO 탐지 정밀도 평균 | YOLO26 차량 탐지 평가 |
| **Top-K Similarity** | Qdrant 검색 후보의 코사인 유사도 분포 | EfficientNet-B3 임베딩 품질 평가 |

---

## AI 솔루션 세부 설명

| 항목 | 내용 |
|------|------|
| **활용 분야** | CCTV·촬영 이미지에서 차량 제조사/모델 자동 식별 (설치형, 내부망 운영 가능) |
| **핵심 기능** | 단일 이미지 동기 식별 / 배치 최대 100장·100MB 동기 식별 / 비동기(Celery) 처리 및 폴링 |
| **식별 결과 상태** | `identified` (신뢰도 ≥0.80) / `uncertain` (후보 표시) / `no_data` (학습 데이터 없음) |
| **학습 데이터 관리** | Studio 서비스: OpenAI gpt-5.2 초기 분석 → 관리자 검수 → EfficientNet-B3 임베딩 생성 → Qdrant 동기화 |
| **VLM 파인튜닝** | 검수 완료 데이터 → LLaMA-Factory QLoRA 4bit (NVIDIA GPU) → LoRA Merge → GGUF → Ollama 배포 |
| **데이터 수명주기** | APScheduler 매일 03:00 자동 실행: 미검수 + 30일 초과 `analyzed_vehicles` 레코드·이미지 일괄 삭제 |
| **배포 형태** | Docker Compose 설치형. `docker-compose.yml` (프로덕션) + `docker-compose.dev.yml` (개발) 분리 운영 |
| **GPU 지원** | NVIDIA GPU — Ollama VLM 서빙(16GB), LLaMA-Factory 파인튜닝(32GB). CPU 전용 환경에서도 동작 |
