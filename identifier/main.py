"""
차량 판별 서비스 - FastAPI 애플리케이션
이미지 업로드 → Qdrant 벡터 검색 → 제조사/모델 판별
"""
import asyncio
import gc
import logging
import logging.handlers
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from typing import List, Optional

# PyTorch 스레드 수 설정 (import torch 전에 환경변수로 설정)
from identifier.config import settings
os.environ["OMP_NUM_THREADS"] = str(settings.torch_threads)
os.environ["MKL_NUM_THREADS"] = str(settings.torch_threads)

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import json
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field as PydanticField

from identifier.config import settings
from identifier.identifier import (
    BatchIdentificationResult,
    DetectionResult,
    IdentificationResult,
    VehicleIdentifier,
)
from identifier.tasks import (
    identify_image_task,
    identify_batch_task,
    identify_uploaded_files_task,
)
from celery.result import AsyncResult

# 로깅 설정
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
log_level = getattr(logging, settings.log_level)

log_path = Path(settings.log_file)
log_path.parent.mkdir(parents=True, exist_ok=True)

# force=True: uvicorn이 먼저 root logger를 설정해도 덮어쓰기
logging.basicConfig(
    level=log_level,
    format=log_format,
    force=True,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            log_path, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        ),
    ],
)
# uvicorn 자체 로거가 root로 전파하지 않도록 설정 (중복 방지)
for uv_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    uv_logger = logging.getLogger(uv_logger_name)
    uv_logger.handlers.clear()
    uv_logger.propagate = True
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 앱 라이프사이클
# ──────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """시작 시 EfficientNet-B3 임베딩 모델 + Qdrant 초기화"""
    logger.info("Starting Vehicle Identification Service...")
    logger.info(f"Qdrant: {settings.qdrant_host}:{settings.qdrant_port}")
    logger.info(f"PyTorch threads: {settings.torch_threads}")
    logger.info(f"CPU cores: {os.cpu_count()}")

    identifier = VehicleIdentifier()
    identifier.initialize()
    app.state.identifier = identifier

    logger.info("Service ready.")
    yield
    logger.info("Shutting down Vehicle Identification Service...")


# ──────────────────────────────────────────────
# FastAPI 앱
# ──────────────────────────────────────────────

_DESCRIPTION = """
## 차량 판별 API

CCTV 이미지에서 차량의 **제조사**와 **모델**을 자동으로 판별하는 REST API입니다.

---

### 판별 방식

1. **YOLO26** 모델로 이미지 내 차량 위치를 감지
2. **EfficientNet-B3** 모델로 차량 이미지를 1536차원 벡터로 변환
3. **Qdrant** 벡터 DB에서 학습된 이미지와 코사인 유사도 비교 (Top-K)
4. 하이브리드 가중 투표 알고리즘으로 최종 제조사/모델 결정

---

### 비동기 API 사용 흐름

```
1. POST /async/identify       → { "task_id": "abc-123" } 즉시 수신
2. GET  /async/result/abc-123 → { "status": "STARTED" }  처리 중
3. GET  /async/result/abc-123 → { "status": "SUCCESS", "result": {...} }  완료
```

폴링 권장 간격: **1~2초**

---

### 엔드포인트 안내

| 상황 | 엔드포인트 |
|------|-----------|
| 이미지 1장 판별 | `POST /async/identify` |
| 이미지 여러 장 판별 | `POST /async/identify/batch` |
| 결과 조회 | `GET /async/result/{task_id}` |

---

### 신뢰도(confidence) 해석

| 범위 | 의미 |
|------|------|
| 0.90 이상 | 높은 신뢰도 — `status: identified` |
| 0.80 ~ 0.89 | VLM 판별 통과 — `status: identified` |
| 0.80 미만 | 후보 있음, 확신 부족 — `status: low_confidence`, 수동 확인 권장 |
| 해당 없음 | 유사 데이터 없음 — `status: no_match` |

---

### 파일 요구사항

- **지원 형식**: JPG, JPEG, PNG, WEBP
- **단건 최대 크기**: 5 MB
- **배치 최대 크기**: 100 MB (전체 합산)
- **배치 최대 파일 수**: 100개

### 이미지 품질 권장사항

판별 정확도는 입력 이미지 품질에 직접적인 영향을 받습니다.

**권장**
- 차량 정면이 프레임 중앙에 위치한 근접 촬영
- 제조사 배지(로고), 헤드라이트, 프론트 그릴이 식별 가능한 이미지
- 야간 촬영의 경우 헤드라이트가 켜진 상태

**비권장**
- 차량이 원거리에 위치하거나 프레임 내 차량 비율이 낮은 이미지
- 차량 측면 또는 후면만 촬영된 이미지
- 심한 역광, 과노출, 블러 이미지

> 권장 조건을 충족하지 않는 이미지는 낮은 신뢰도(confidence)로 반환되거나 `low_confidence` 처리될 수 있습니다.
"""

app = FastAPI(
    title="차량 판별 API (Reeve Identifier)",
    description=_DESCRIPTION,
    version="1.0.0",
    contact={
        "name": "Reeve 기술 지원",
    },
    openapi_tags=[
        {
            "name": "Health",
            "description": "서비스 컴포넌트(EfficientNet, YOLO, Qdrant) 상태 확인",
        },
        {
            "name": "Async",
            "description": (
                "**비동기 차량 판별** — 작업을 Celery 큐에 등록하고 `task_id`를 즉시 반환합니다. "
                "`GET /async/result/{task_id}` 폴링으로 결과를 조회하세요."
            ),
        },
    ],
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# ──────────────────────────────────────────────
# 엔드포인트
# ──────────────────────────────────────────────

@app.get("/", tags=["UI"], include_in_schema=False)
async def index():
    """메인 페이지"""
    html_path = Path(__file__).parent / "static" / "index.html"
    if html_path.exists():
        return FileResponse(html_path)
    return JSONResponse(
        status_code=404,
        content={"error": "index.html not found"},
    )


@app.get(
    "/health",
    tags=["Health"],
    summary="서비스 상태 확인",
    response_description="각 컴포넌트의 상태 및 학습 데이터 수",
)
async def health_check():
    """
    EfficientNet-B3 임베딩 모델, YOLO 모델, Qdrant 연결 상태를 한번에 확인합니다.

    모니터링 시스템의 헬스체크 엔드포인트 또는 서비스 점검 용도로 사용하세요.

    **응답 필드**
    - `status`: `healthy` (정상) / `degraded` (Qdrant 오류, 판별 불가) / `unhealthy` (임베딩 모델 미로드, 서비스 불가)
    - `embedding_model`: EfficientNet-B3 모델 로드 상태
    - `yolo_model`: YOLO 모델 로드 상태 (`disabled`이면 차량 감지 없이 전체 이미지로 판별)
    - `qdrant`: Qdrant 연결 상태
    - `training_images_count`: 학습된 이미지 수 (0이면 판별 불가)
    """
    identifier: VehicleIdentifier = app.state.identifier
    return identifier.health_check()


@app.post(
    "/detect",
    response_model=DetectionResult,
    tags=["Detection"],
    include_in_schema=False,
    summary="이미지 내 차량 위치 감지",
    response_description="감지된 차량 목록과 각 차량의 바운딩 박스",
    responses={
        400: {"description": "지원하지 않는 파일 형식이거나 파일 크기가 10MB를 초과한 경우"},
        500: {"description": "차량 감지 처리 중 서버 오류"},
    },
)
async def detect_vehicles(
    file: UploadFile = File(..., description="차량이 포함된 이미지 파일 (JPG/JPEG/PNG/WEBP, 최대 5MB)"),
):
    """
    이미지에서 모든 차량의 위치(바운딩 박스)를 감지하여 반환합니다.

    YOLO26 모델을 사용하며, 감지된 차량은 **면적(area) 큰 순**으로 정렬됩니다.
    응답의 `bbox` 값(`[x1, y1, x2, y2]`)을 `/identify`의 `bbox` 파라미터로 전달하면
    원하는 특정 차량만 선택하여 판별할 수 있습니다.

    **일반적인 사용 흐름 (차량이 여러 대인 경우)**
    1. `POST /detect` 로 이미지 내 모든 차량 목록 조회
    2. 원하는 차량의 `detections[n].bbox` 값 선택
    3. `POST /identify` 에 동일 이미지와 선택한 `bbox` 함께 전송

    > 이미지에 차량이 1대만 있다면 `/detect` 없이 `/identify`만 호출해도 자동 감지됩니다.

    **감지 가능한 차량 종류**: car, motorcycle, bus, truck (COCO 데이터셋 기준)
    """
    # 1. 확장자 검증
    filename = file.filename or "unknown.jpg"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {settings.allowed_extensions}",
        )

    # 2. 파일 크기 검증
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_upload_size // 1024 // 1024}MB를 초과합니다.",
        )

    # 3. 임시 파일에 저장 → 감지 → 삭제
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(content)

        # 블로킹 작업을 스레드풀에서 실행
        identifier: VehicleIdentifier = app.state.identifier
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, identifier.detect_vehicles, tmp_path
        )
        return result

    except Exception as e:
        logger.error(f"Detection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"차량 감지 중 오류가 발생했습니다: {str(e)}",
        )
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@app.post(
    "/identify",
    response_model=IdentificationResult,
    tags=["Identification"],
    include_in_schema=False,
    summary="차량 판별 (단건, 동기식)",
    response_description="판별된 제조사·모델 정보 및 신뢰도",
    responses={
        400: {"description": "지원하지 않는 파일 형식, 크기 초과, 또는 잘못된 bbox 형식"},
        500: {"description": "판별 처리 중 서버 오류"},
    },
)
async def identify_vehicle(
    file: UploadFile = File(..., description="차량 이미지 파일 (JPG/JPEG/PNG/WEBP, 최대 5MB)"),
    bbox: Optional[str] = Form(
        None,
        description=(
            "판별할 차량의 바운딩 박스. `x1,y1,x2,y2` 형식 (픽셀 좌표, 쉼표 구분). "
            "예: `100,50,800,600`. "
            "미입력 시 YOLO26이 자동으로 가장 큰 차량을 감지합니다."
        ),
    ),
):
    """
    이미지를 업로드하면 차량의 **제조사**와 **모델**을 즉시 반환합니다.

    **처리 흐름**
    1. `bbox` 지정 시: 해당 영역을 크롭하여 EfficientNet-B3 임베딩 생성
    2. `bbox` 미지정 시: YOLO26으로 이미지 내 가장 큰 차량 자동 감지 후 크롭
    3. Qdrant 벡터 DB에서 유사 학습 이미지 검색 (Top-K)
    4. 하이브리드 가중 투표로 최종 제조사/모델 결정

    **`status` 필드 해석**

    | 값 | 의미 | 권장 대응 |
    |----|------|----------|
    | `identified` | 판별 성공 | 결과를 그대로 사용 |
    | `low_confidence` | 후보는 있지만 확신 부족 | 수동 확인 또는 고화질 재촬영 |
    | `no_match` | 유사한 학습 데이터 없음 | 관리자에게 학습 데이터 추가 요청 |

    **`bbox` 파라미터 예시**
    - `/detect` 응답의 `detections[0].bbox` 배열을 `"x1,y1,x2,y2"` 문자열로 변환하여 전달
    - 이미지 내 특정 차량을 직접 지정: `"100,50,800,600"`

    > **동기식 처리**: 판별이 완료될 때까지 응답을 대기합니다 (일반적으로 200~500ms).
    > 고부하 환경이나 배치 처리가 필요하면 `/async/identify` 또는 `/identify/batch`를 사용하세요.
    """
    # 1. 확장자 검증
    filename = file.filename or "unknown.jpg"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"지원하지 않는 파일 형식입니다. 허용: {settings.allowed_extensions}",
        )

    # 2. 파일 크기 검증
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"파일 크기가 {settings.max_upload_size // 1024 // 1024}MB를 초과합니다.",
        )

    # 3. bbox 파싱
    bbox_list = None
    if bbox:
        try:
            bbox_list = [int(x.strip()) for x in bbox.split(",")]
            if len(bbox_list) != 4:
                raise ValueError("bbox must have 4 values")
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"잘못된 bbox 형식입니다. 'x1,y1,x2,y2' 형식으로 입력하세요: {e}",
            )

    # 4. 임시 파일에 저장 → 판별 → 삭제
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
    try:
        with os.fdopen(tmp_fd, "wb") as tmp_file:
            tmp_file.write(content)

        # 블로킹 작업을 스레드풀에서 실행
        identifier: VehicleIdentifier = app.state.identifier
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, identifier.identify, tmp_path, bbox_list
        )
        return result

    except HTTPException:
        raise
    except ValueError as e:
        # 차량 감지 실패 등의 검증 오류
        logger.warning(f"Validation error: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Identification failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"판별 중 오류가 발생했습니다: {str(e)}",
        )
    finally:
        # 임시 파일 삭제
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        del content
        gc.collect()


@app.post(
    "/identify/stream",
    tags=["Identification"],
    include_in_schema=False,
    summary="차량 판별 (단건, SSE 스트리밍)",
)
async def identify_stream(
    file: UploadFile = File(...),
    bbox: Optional[str] = Form(None),
):
    """YOLO 감지 → EfficientNet 분류 단계를 SSE로 스트리밍합니다."""
    filename = file.filename or "unknown.jpg"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(400, f"지원하지 않는 파일 형식입니다. 허용: {settings.allowed_extensions}")

    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(400, f"파일 크기가 {settings.max_upload_size // 1024 // 1024}MB를 초과합니다.")

    bbox_list = None
    if bbox:
        try:
            bbox_list = [int(x.strip()) for x in bbox.split(",")]
            if len(bbox_list) != 4:
                raise ValueError("bbox must have 4 values")
        except ValueError as e:
            raise HTTPException(400, f"잘못된 bbox 형식입니다: {e}")

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
    with os.fdopen(tmp_fd, "wb") as tmp_file:
        tmp_file.write(content)

    async def generate():
        identifier: VehicleIdentifier = app.state.identifier
        loop = asyncio.get_event_loop()
        try:
            # Stage 1: YOLO 감지
            yield f"data: {json.dumps({'stage': 'detecting', 'message': '차량 감지 중...'}, ensure_ascii=False)}\n\n"

            detection_result = await loop.run_in_executor(None, identifier.detect_vehicles, tmp_path)

            detect_bbox = bbox_list
            detection_info = None
            if not detect_bbox and detection_result.detections:
                det = detection_result.detections[0]
                detect_bbox = det.bbox
                detection_info = det.model_dump()

            # Stage 2: 분류
            yield f"data: {json.dumps({'stage': 'classifying', 'message': '분류 중...', 'detection': detection_info}, ensure_ascii=False)}\n\n"

            result = await loop.run_in_executor(None, identifier.identify, tmp_path, detect_bbox)
            event = {"stage": "done"}
            event.update(result.model_dump())
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Stream identify failed: {e}", exc_info=True)
            yield f"data: {json.dumps({'stage': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            gc.collect()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post(
    "/identify/batch",
    response_model=BatchIdentificationResult,
    tags=["Identification"],
    include_in_schema=False,
    summary="차량 판별 (배치, 동기식)",
    response_description="업로드 순서대로 정렬된 이미지별 판별 결과",
    responses={
        400: {"description": "파일이 없거나, 파일 수·크기 초과, 또는 지원하지 않는 파일 형식"},
        500: {"description": "배치 처리 중 서버 오류"},
    },
)
async def identify_batch(
    files: List[UploadFile] = File(..., description="차량 이미지 파일 목록 (최대 100개, 합계 100MB 이하)"),
):
    """
    여러 이미지를 한 번에 업로드하여 **배치로 판별**합니다.

    YOLO26 감지 → EfficientNet-B3 임베딩 → Qdrant 검색의 각 단계를 배치로 병렬 처리하므로
    이미지를 1장씩 반복 호출하는 것보다 훨씬 빠릅니다.

    **제한 사항**
    - 최대 파일 수: **100개**
    - 최대 전체 크기: **100 MB** (합계)
    - 파일당 형식: JPG/JPEG/PNG/WEBP

    **응답 구조**
    - `items`: 업로드 순서와 동일한 순서로 이미지별 결과 포함
    - 개별 이미지가 실패해도 나머지 이미지는 정상 처리됨 (`items[n].error` 필드 확인)
    - `processing_time_ms`: 전체 배치 처리 시간 (밀리초)

    > **동기식 처리**: 모든 이미지 처리 완료 후 응답을 반환합니다.
    > 100장 기준 일반적으로 5~30초 소요됩니다.
    > 처리 시간이 길어 타임아웃이 우려되면 `/async/identify/batch`를 사용하세요.
    """
    if not files:
        raise HTTPException(400, "업로드된 파일이 없습니다.")

    if len(files) > settings.max_batch_files:
        raise HTTPException(
            400,
            f"최대 {settings.max_batch_files}개까지 업로드 가능합니다. "
            f"(업로드: {len(files)}개)",
        )

    # 1. 파일 검증 및 임시 저장
    tmp_paths: List[str] = []
    total_size = 0

    try:
        for file in files:
            # 확장자 검증
            filename = file.filename or "unknown.jpg"
            file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if file_ext not in settings.allowed_extensions_list:
                raise HTTPException(
                    400,
                    f"지원하지 않는 파일 형식입니다 ({filename}). "
                    f"허용: {settings.allowed_extensions}",
                )

            # 파일 읽기
            content = await file.read()
            total_size += len(content)

            # 전체 크기 검증
            if total_size > settings.max_batch_upload_size:
                raise HTTPException(
                    400,
                    f"전체 파일 크기가 "
                    f"{settings.max_batch_upload_size // 1024 // 1024}MB를 초과합니다.",
                )

            # 임시 파일 저장
            tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                tmp_file.write(content)
            tmp_paths.append(tmp_path)

        # 2. 배치 처리
        identifier: VehicleIdentifier = app.state.identifier
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, identifier.identify_batch, tmp_paths, settings.batch_size
        )

        # 3. 원본 파일명 복원 (디버깅용)
        for i, item in enumerate(result.items):
            if i < len(files) and files[i].filename:
                item.image_path = files[i].filename

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch identification failed: {e}", exc_info=True)
        raise HTTPException(
            500, f"배치 판별 중 오류가 발생했습니다: {str(e)}"
        )
    finally:
        # 4. 임시 파일 정리
        for tmp_path in tmp_paths:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass




# ──────────────────────────────────────────────
# 비동기 API (Celery 기반)
# ──────────────────────────────────────────────

class AsyncTaskResponse(BaseModel):
    """비동기 작업 제출 응답"""
    task_id: str = PydanticField(description="작업 ID. `GET /async/result/{task_id}` 로 결과 조회")
    status: str = PydanticField(description="초기 상태 (항상 `PENDING`)")
    message: str = PydanticField(description="폴링 방법 안내 메시지")


class TaskStatusResponse(BaseModel):
    """비동기 작업 상태 및 결과"""
    task_id: str = PydanticField(description="작업 ID")
    status: str = PydanticField(
        description=(
            "작업 상태. "
            "`PENDING`: 대기 중 (워커 할당 전), "
            "`STARTED`: 처리 중, "
            "`SUCCESS`: 완료 (`result` 필드 확인), "
            "`FAILURE`: 실패 (`error` 필드 확인)"
        )
    )
    result: Optional[dict] = PydanticField(
        default=None,
        description=(
            "판별 결과 (`status=SUCCESS` 일 때). "
            "단건 요청이면 `IdentificationResult`, 배치 요청이면 `BatchIdentificationResult` 구조"
        )
    )
    error: Optional[str] = PydanticField(default=None, description="오류 메시지 (`status=FAILURE` 일 때)")
    progress: Optional[dict] = PydanticField(default=None, description="진행 상황 (`status=STARTED` 일 때, 선택적)")


@app.post(
    "/async/identify",
    response_model=AsyncTaskResponse,
    tags=["Async"],
    summary="차량 판별 요청 (단건, 비동기식)",
    response_description="즉시 수신되는 task_id. 결과는 GET /async/result/{task_id} 로 조회",
    responses={
        400: {"description": "지원하지 않는 파일 형식 또는 파일 크기 초과"},
        500: {"description": "작업 큐 등록 중 서버 오류"},
    },
)
async def async_identify(
    file: UploadFile = File(..., description="차량 이미지 파일 (JPG/JPEG/PNG/WEBP, 최대 5MB)"),
):
    """
    이미지를 업로드하면 **즉시 `task_id`를 반환**하고, 백그라운드 워커가 판별을 처리합니다.

    결과는 `GET /async/result/{task_id}` 를 **폴링**하여 조회하세요.

    **비동기 방식이 유리한 경우**
    - 여러 클라이언트가 동시에 요청하는 고부하 환경
    - 로드밸런서/게이트웨이의 응답 타임아웃이 짧은 환경 (예: 30초 제한)
    - 처리 결과를 즉시 사용하지 않아도 되는 경우

    **폴링 권장 사항**
    - 간격: **1~2초**
    - `status`가 `SUCCESS` 또는 `FAILURE`가 되면 폴링 중단
    - 결과는 Redis에 **24시간** 보존됩니다

    **전체 흐름 예시**
    ```
    POST /async/identify (이미지 업로드)
    → { "task_id": "abc-123", "status": "PENDING" }

    GET /async/result/abc-123  (1초 후)
    → { "task_id": "abc-123", "status": "STARTED" }

    GET /async/result/abc-123  (2초 후)
    → { "task_id": "abc-123", "status": "SUCCESS", "result": { ... } }
    ```
    """
    # 확장자 검증
    filename = file.filename or "unknown.jpg"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(
            400,
            f"지원하지 않는 파일 형식입니다. 허용: {settings.allowed_extensions}",
        )

    # 파일 크기 검증
    content = await file.read()
    if len(content) > settings.max_upload_size:
        raise HTTPException(
            400,
            f"파일 크기가 {settings.max_upload_size // 1024 // 1024}MB를 초과합니다.",
        )

    # 임시 파일 저장
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
    with os.fdopen(tmp_fd, "wb") as tmp_file:
        tmp_file.write(content)

    # Celery 작업 큐에 등록
    task = identify_image_task.apply_async(args=[tmp_path])

    return AsyncTaskResponse(
        task_id=task.id,
        status="PENDING",
        message="작업이 큐에 등록되었습니다. task_id로 결과를 조회하세요.",
    )


@app.post(
    "/async/identify/batch",
    response_model=AsyncTaskResponse,
    tags=["Async"],
    summary="차량 판별 요청 (배치, 비동기식)",
    response_description="즉시 수신되는 task_id. 결과는 GET /async/result/{task_id} 로 조회",
    responses={
        400: {"description": "파일이 없거나, 파일 수·크기 초과, 또는 지원하지 않는 파일 형식"},
        500: {"description": "작업 큐 등록 중 서버 오류"},
    },
)
async def async_identify_batch(
    files: List[UploadFile] = File(..., description="차량 이미지 파일 목록 (최대 100개, 합계 100MB 이하)"),
):
    """
    여러 이미지를 업로드하면 **즉시 `task_id`를 반환**하고, 백그라운드 워커가 배치 처리합니다.

    결과는 `GET /async/result/{task_id}` 를 **폴링**하여 조회하세요.

    **제한 사항**
    - 최대 파일 수: **100개**
    - 최대 전체 크기: **100 MB** (합계)

    **결과 구조 (`status=SUCCESS` 시)**

    `result` 필드는 `BatchIdentificationResult`와 동일한 구조입니다:
    ```json
    {
      "items": [
        {
          "image_path": "cam01_001.jpg",
          "result": { "status": "identified", "manufacturer_korean": "현대", ... },
          "error": null
        },
        ...
      ],
      "total": 10,
      "success_count": 9,
      "error_count": 1,
      "processing_time_ms": 3200.5
    }
    ```

    > 결과는 Redis에 **24시간** 보존됩니다.
    """
    if not files:
        raise HTTPException(400, "업로드된 파일이 없습니다.")

    if len(files) > settings.max_batch_files:
        raise HTTPException(
            400,
            f"최대 {settings.max_batch_files}개까지 업로드 가능합니다.",
        )

    # 파일 검증 및 임시 저장
    tmp_paths: List[str] = []
    filenames: List[str] = []
    total_size = 0

    try:
        for file in files:
            filename = file.filename or "unknown.jpg"
            file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if file_ext not in settings.allowed_extensions_list:
                # 이미 저장된 파일 정리
                for tmp_path in tmp_paths:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                raise HTTPException(
                    400,
                    f"지원하지 않는 파일 형식입니다 ({filename}).",
                )

            content = await file.read()
            total_size += len(content)

            if total_size > settings.max_batch_upload_size:
                # 이미 저장된 파일 정리
                for tmp_path in tmp_paths:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                raise HTTPException(
                    400,
                    f"전체 파일 크기가 "
                    f"{settings.max_batch_upload_size // 1024 // 1024}MB를 초과합니다.",
                )

            tmp_fd, tmp_path = tempfile.mkstemp(suffix=f".{file_ext}")
            with os.fdopen(tmp_fd, "wb") as tmp_file:
                tmp_file.write(content)
            tmp_paths.append(tmp_path)
            filenames.append(filename)

        # Celery 작업 큐에 등록
        task = identify_uploaded_files_task.apply_async(
            args=[tmp_paths, filenames, settings.batch_size]
        )

        return AsyncTaskResponse(
            task_id=task.id,
            status="PENDING",
            message=f"{len(files)}개 이미지가 큐에 등록되었습니다. task_id로 결과를 조회하세요.",
        )

    except HTTPException:
        raise
    except Exception as e:
        # 에러 시 임시 파일 정리
        for tmp_path in tmp_paths:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise HTTPException(500, f"업로드 처리 중 오류: {str(e)}")


@app.get(
    "/async/result/{task_id}",
    response_model=TaskStatusResponse,
    tags=["Async"],
    summary="비동기 작업 결과 조회",
    response_description="작업 상태 및 판별 결과 (완료 시)",
    responses={
        200: {"description": "작업 상태 정상 조회 (PENDING/STARTED/SUCCESS/FAILURE 모두 200으로 반환)"},
    },
)
async def get_task_result(
    task_id: str,
):
    """
    비동기 작업의 현재 상태와 결과를 조회합니다.

    `POST /async/identify` 또는 `POST /async/identify/batch` 응답의 `task_id`를 사용하세요.

    **`status` 값 설명**

    | 값 | 의미 | 다음 행동 |
    |----|------|----------|
    | `PENDING` | 대기 중 (워커 할당 전) | 1~2초 후 재조회 |
    | `STARTED` | 처리 중 | 1~2초 후 재조회 |
    | `SUCCESS` | 완료 | `result` 필드 사용 후 폴링 중단 |
    | `FAILURE` | 실패 | `error` 필드 확인 후 폴링 중단 |

    **폴링 구현 가이드라인**
    - 권장 간격: **1~2초**
    - 최대 대기 시간: **10분** (작업 타임아웃 기준)
    - `SUCCESS` 또는 `FAILURE` 수신 즉시 폴링 중단

    **`result` 필드 구조**
    - 단건 요청(`/async/identify`): `IdentificationResult` 구조
    - 배치 요청(`/async/identify/batch`): `BatchIdentificationResult` 구조

    > 결과는 작업 완료 후 **24시간** 동안 보존됩니다. 이후에는 `PENDING`으로 응답됩니다.
    """
    task = AsyncResult(task_id)

    if task.state == "PENDING":
        return TaskStatusResponse(
            task_id=task_id,
            status="PENDING",
        )
    elif task.state == "STARTED":
        return TaskStatusResponse(
            task_id=task_id,
            status="STARTED",
            progress=task.info if isinstance(task.info, dict) else None,
        )
    elif task.state == "SUCCESS":
        return TaskStatusResponse(
            task_id=task_id,
            status="SUCCESS",
            result=task.result,
        )
    elif task.state == "FAILURE":
        return TaskStatusResponse(
            task_id=task_id,
            status="FAILURE",
            error=str(task.info),
        )
    else:
        return TaskStatusResponse(
            task_id=task_id,
            status=task.state,
        )


# ──────────────────────────────────────────────
# 관리 API
# ──────────────────────────────────────────────

class ReloadVLMRequest(BaseModel):
    model_name: str = PydanticField(..., description="교체할 Ollama 모델명 (예: reeve-vlm-v1)")


@app.post(
    "/admin/reload-vlm",
    tags=["Admin"],
    summary="VLM 모델 핫리로드",
    description=(
        "Ollama에 새 모델이 등록된 후 호출. 서비스 재시작 없이 VLM 모델을 교체한다. "
        "Trainer의 POST /deploy/ollama가 자동으로 호출하거나 수동으로 호출 가능."
    ),
)
async def reload_vlm(req: ReloadVLMRequest, request: Request):
    identifier: VehicleIdentifier = request.app.state.identifier
    vlm = identifier.vlm_service
    if vlm is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"VLM 서비스가 비활성 상태입니다 (IDENTIFIER_MODE={settings.identifier_mode}). "
                "visual_rag 또는 vlm_only 모드에서만 사용 가능합니다."
            ),
        )
    try:
        vlm.reload(req.model_name)
        return {"status": "ok", "model_name": req.model_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ReloadEfficientNetRequest(BaseModel):
    model_path: str = PydanticField(..., description="파인튜닝된 .pth 파일 경로")
    class_mapping_path: str = PydanticField(..., description="class_mapping.json 파일 경로")


@app.post(
    "/admin/reload-efficientnet",
    tags=["Admin"],
    summary="EfficientNetV2-M 분류기 핫리로드",
    description=(
        "파인튜닝 완료 후 호출. 서비스 재시작 없이 분류기를 교체한다. "
        "Trainer의 EfficientNetTrainer가 자동으로 호출하거나 수동으로 호출 가능."
    ),
)
async def reload_efficientnet(req: ReloadEfficientNetRequest, request: Request):
    identifier: VehicleIdentifier = request.app.state.identifier
    if identifier.classifier is None:
        raise HTTPException(status_code=400, detail="EfficientNet 분류기가 초기화되지 않았습니다.")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            identifier.classifier.reload,
            req.model_path,
            req.class_mapping_path,
        )
        return {
            "status": "reloaded",
            "model_path": req.model_path,
            "has_classification_head": identifier.classifier.has_classification_head,
            "num_classes": identifier.classifier.num_classes,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ──────────────────────────────────────────────
# 전역 예외 핸들러
# ──────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc),
        },
    )


# ──────────────────────────────────────────────
# 직접 실행
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    # CPU 코어 수 기반으로 workers 자동 계산
    cpu_count = os.cpu_count() or 8
    workers = max(1, cpu_count // settings.torch_threads)

    logger.info(
        f"Starting with {workers} workers "
        f"(CPU cores: {cpu_count}, torch threads: {settings.torch_threads})"
    )

    uvicorn.run(
        "identifier.main:app",
        host="0.0.0.0",
        port=settings.identifier_port,
        workers=workers,
        reload=False,
    )
