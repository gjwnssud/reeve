# 비동기 API 사용 가이드

Celery + Redis 기반 비동기 작업 큐로 대량 이미지 처리를 효율적으로 수행합니다.

## 아키텍처

```
CCTV 업체 → FastAPI (즉시 task_id 반환)
                ↓
           Redis 큐에 적재
                ↓
       Celery Worker가 배치 처리
                ↓
       결과를 Redis에 저장 (24시간)
                ↓
CCTV 업체 → GET /async/result/{task_id}
```

## API 엔드포인트

### 1. 단일 이미지 비동기 판별

```bash
POST /async/identify
Content-Type: multipart/form-data

file: <image file>
```

**응답:**
```json
{
  "task_id": "abc123...",
  "status": "PENDING",
  "message": "작업이 큐에 등록되었습니다."
}
```

### 2. 배치 비동기 판별

```bash
POST /async/identify/batch
Content-Type: multipart/form-data

files: <image file 1>
files: <image file 2>
...
```

**제한:**
- 최대 파일 수: 100개
- 최대 전체 크기: 100MB

**응답:**
```json
{
  "task_id": "def456...",
  "status": "PENDING",
  "message": "50개 이미지가 큐에 등록되었습니다."
}
```

### 3. 작업 결과 조회

```bash
GET /async/result/{task_id}
```

**응답 (처리 중):**
```json
{
  "task_id": "abc123...",
  "status": "STARTED"
}
```

**응답 (완료):**
```json
{
  "task_id": "abc123...",
  "status": "SUCCESS",
  "result": {
    "status": "identified",
    "manufacturer_korean": "현대",
    "model_korean": "아반떼",
    "confidence": 0.95,
    ...
  }
}
```

**응답 (실패):**
```json
{
  "task_id": "abc123...",
  "status": "FAILURE",
  "error": "에러 메시지"
}
```

## Python 클라이언트 예제

### 단일 이미지

```python
import httpx
import time

# 1. 작업 등록
with open("car.jpg", "rb") as f:
    response = httpx.post(
        "http://localhost:8001/async/identify",
        files={"file": f}
    )
task_id = response.json()["task_id"]

# 2. 결과 폴링
while True:
    result = httpx.get(
        f"http://localhost:8001/async/result/{task_id}"
    ).json()

    if result["status"] == "SUCCESS":
        print(result["result"])
        break
    elif result["status"] == "FAILURE":
        print(f"Error: {result['error']}")
        break

    time.sleep(1)  # 1초마다 체크
```

### 배치 이미지

```python
import httpx
import time

# 1. 배치 작업 등록
files = [
    ("files", ("car1.jpg", open("car1.jpg", "rb"), "image/jpeg")),
    ("files", ("car2.jpg", open("car2.jpg", "rb"), "image/jpeg")),
]

response = httpx.post(
    "http://localhost:8001/async/identify/batch",
    files=files
)
task_id = response.json()["task_id"]

# 2. 결과 폴링
while True:
    result = httpx.get(
        f"http://localhost:8001/async/result/{task_id}"
    ).json()

    if result["status"] == "SUCCESS":
        batch_result = result["result"]
        print(f"Total: {batch_result['total']}")
        print(f"Success: {batch_result['success_count']}")

        for item in batch_result["items"]:
            if item["error"]:
                print(f"{item['image_path']}: ERROR - {item['error']}")
            else:
                r = item["result"]
                print(f"{item['image_path']}: {r['manufacturer_korean']} {r['model_korean']}")
        break
    elif result["status"] == "FAILURE":
        print(f"Error: {result['error']}")
        break

    time.sleep(2)  # 2초마다 체크
```

## 서비스 실행

### Docker Compose (권장)

```bash
# Mac 환경 (CPU 모드)
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml up -d

# Linux / Windows 환경 (NVIDIA GPU)
cd docker
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 로그 확인
docker compose -f docker-compose.yml logs -f celery-worker
```

### 로컬 개발

```bash
# 1. Redis 실행
redis-server

# 2. FastAPI 실행
uvicorn identifier.main:app --reload --port 8001

# 3. Celery Worker 실행 (별도 터미널)
celery -A identifier.celery_app worker --loglevel=info
```

## 설정

### .env

```env
# Redis
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# Celery
CELERY_TASK_TIME_LIMIT=600           # 10분 타임아웃
CELERY_TASK_SOFT_TIME_LIMIT=540      # 9분 소프트 타임아웃
CELERY_MAX_RETRIES=3                 # 최대 재시도 횟수
```

## 성능 특성

| 항목 | 동기 API | 비동기 API |
|------|----------|-----------|
| 응답 시간 | 100-360ms | **즉시 (<10ms)** |
| 동시 처리 | workers 제한 | **큐 무제한** |
| 재시도 | 없음 | **자동 3회** |
| 결과 추적 | 없음 | **task_id 추적** |
| 급격한 트래픽 | 부하 | **큐 버퍼링** |

## 주의사항

1. **결과 만료**: 결과는 24시간 후 자동 삭제
2. **파일 정리**: 임시 파일은 작업 완료/실패 시 자동 삭제
3. **재시도**: 실패 시 exponential backoff로 3회 재시도
4. **타임아웃**: 10분 이상 걸리는 작업은 실패 처리

## 모니터링

### Celery Flower (선택)

```bash
pip install flower
celery -A identifier.celery_app flower

# 웹 UI: http://localhost:5555
```

## 장애 처리

### Worker 재시작

```bash
docker compose -f docker-compose.yml restart celery-worker
```

### Redis 데이터 삭제

```bash
docker compose -f docker-compose.yml exec redis redis-cli FLUSHDB
```
