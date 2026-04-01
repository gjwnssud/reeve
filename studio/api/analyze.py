"""
차량 분석 API 라우터
고객사용 이미지 분석 엔드포인트
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import os
import json
import asyncio
from pathlib import Path

import logging

from studio.models import get_db
from studio.models.analyzed_vehicle import AnalyzedVehicle
from studio.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# Pydantic 스키마
class AnalysisResponse(BaseModel):
    """차량 분석 응답"""
    id: int
    manufacturer: Optional[str]
    model: Optional[str]
    year: Optional[str]
    confidence_score: Optional[float]
    matched_manufacturer_id: Optional[int]
    matched_model_id: Optional[int]

    class Config:
        from_attributes = True


@router.post("/analyze/vehicle", response_model=AnalysisResponse, status_code=status.HTTP_201_CREATED)
async def analyze_vehicle_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    차량 이미지 분석

    Phase 1: OpenAI Vision API 사용
    Phase 2: LLaVA-1.6 로컬 모델 사용
    """
    # 파일 확장자 검증
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension. Allowed: {settings.allowed_extensions}"
        )

    # 파일 크기 검증
    file.file.seek(0, 2)  # 파일 끝으로 이동
    file_size = file.file.tell()
    file.file.seek(0)  # 다시 처음으로

    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.max_upload_size / 1024 / 1024}MB"
        )

    # 파일 저장 (날짜별 디렉토리)
    from datetime import datetime
    date_str = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path(f"data/uploads/{date_str}")
    data_dir.mkdir(parents=True, exist_ok=True)

    file_path = data_dir / f"{os.urandom(16).hex()}_{file.filename}"

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Vision API 분석 (백엔드 설정에 따라 OpenAI 또는 Ollama)
    from studio.services.vision_backend import get_vision_backend
    vision_service = get_vision_backend()
    from studio.services.matcher import VehicleMatcher

    try:
        # OpenAI Vision API 호출 (DB 세션 전달)
        vision_result = await vision_service.analyze_vehicle_image(str(file_path), db=db)

        # 기준 DB와 매칭 (auto_insert=True: 매칭 실패 시 자동으로 DB에 추가)
        matcher = VehicleMatcher(db, auto_insert=True)
        match_result = matcher.match_vehicle(
            vision_result.get("manufacturer_code", ""),
            vision_result.get("model_code", ""),
            vision_confidence=vision_result.get("confidence")  # Vision API 신뢰도 전달
        )

        # 분석 결과 저장 (한글명 사용)
        analyzed = AnalyzedVehicle(
            image_path=str(file_path),
            raw_result=vision_result,
            manufacturer=match_result["manufacturer"].korean_name if match_result["manufacturer"] else None,
            model=match_result["model"].korean_name if match_result["model"] else None,
            year=vision_result.get("year"),
            matched_manufacturer_id=match_result["manufacturer"].id if match_result["manufacturer"] else None,
            matched_model_id=match_result["model"].id if match_result["model"] else None,
            confidence_score=match_result["overall_confidence"],
            is_verified=False
        )

        db.add(analyzed)
        db.commit()
        db.refresh(analyzed)

    except Exception as e:
        # 오류 발생 시에도 기록
        analyzed = AnalyzedVehicle(
            image_path=str(file_path),
            raw_result={"error": str(e)},
            manufacturer=None,
            model=None,
            confidence_score=0.0,
            is_verified=False
        )
        db.add(analyzed)
        db.commit()
        db.refresh(analyzed)

        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )

    return AnalysisResponse(
        id=analyzed.id,
        manufacturer=analyzed.manufacturer,
        model=analyzed.model,
        year=analyzed.year,
        confidence_score=float(analyzed.confidence_score) if analyzed.confidence_score else 0.0,
        matched_manufacturer_id=analyzed.matched_manufacturer_id,
        matched_model_id=analyzed.matched_model_id
    )


@router.get("/vehicle/{vehicle_id}")
async def get_vehicle_analysis(vehicle_id: int, db: Session = Depends(get_db)):
    """차량 분석 결과 조회"""
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == vehicle_id).first()

    if not analyzed:
        raise HTTPException(status_code=404, detail="Analysis result not found")

    return analyzed.to_dict()


#=============================================================================
# 차량 감지 엔드포인트
#=============================================================================

class DetectionResponse(BaseModel):
    """차량 감지 응답"""
    detections: List[dict]
    count: int
    image_size: dict


@router.post("/detect-vehicle", response_model=DetectionResponse)
async def detect_vehicle(
    file: Optional[UploadFile] = File(None),
    analyzed_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
):
    """
    이미지에서 차량 감지

    YOLO26을 사용하여 이미지 내 차량을 감지하고 바운딩 박스 반환
    blocking 작업(cv2, YOLO)은 run_in_executor로 스레드풀에서 실행
    analyzed_id가 제공되면 DB에서 original_image_path를 읽어 사용
    """
    import asyncio
    from studio.services.vehicle_detector import get_vehicle_detector
    import cv2

    temp_file = False

    if analyzed_id:
        # DB에서 original_image_path 로드
        analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
        if not analyzed or not analyzed.original_image_path:
            raise HTTPException(status_code=404, detail="Analyzed vehicle not found or no original image")
        file_path = Path(analyzed.original_image_path)
    elif file:
        # 파일 확장자 검증
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in settings.allowed_extensions_list:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed: {settings.allowed_extensions}"
            )

        # 파일 크기 검증
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {settings.max_upload_size / 1024 / 1024}MB"
            )

        # 임시 파일 저장
        data_dir = Path("data/temp")
        data_dir.mkdir(parents=True, exist_ok=True)
        file_path = data_dir / f"{os.urandom(16).hex()}_{file.filename}"
        with open(file_path, "wb") as buffer:
            buffer.write(await file.read())
        temp_file = True
    else:
        raise HTTPException(status_code=400, detail="Either file or analyzed_id must be provided")

    try:
        # blocking 작업을 스레드풀에서 실행
        loop = asyncio.get_event_loop()

        def _detect_sync():
            image = cv2.imread(str(file_path))
            if image is None:
                return None, 0, 0
            h, w = image.shape[:2]
            detector = get_vehicle_detector(model_size='m')
            dets = detector.detect_vehicles(
                str(file_path),
                confidence_threshold=0.3,
                iou_threshold=0.45
            )
            return dets, w, h

        detections, w, h = await loop.run_in_executor(None, _detect_sync)

        if detections is None:
            raise HTTPException(status_code=400, detail="Invalid image file")

        # DB 업데이트 (analyzed_id가 있는 경우)
        if analyzed_id:
            analyzed.yolo_detections = detections
            analyzed.processing_stage = 'yolo_detected'
            db.commit()

        return DetectionResponse(
            detections=detections,
            count=len(detections),
            image_size={"width": w, "height": h}
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Vehicle detection failed: {str(e)}"
        )

    finally:
        # 임시 파일만 삭제 (원본 이미지는 삭제하지 않음)
        if temp_file and file_path.exists():
            file_path.unlink()


#=============================================================================
# SSE 스트리밍 분석 엔드포인트
#=============================================================================

async def stream_analysis_progress(
    file_path: str,
    bbox: List[int],
    db: Session,
    analyzed_id: Optional[int] = None
):
    """
    차량 분석을 SSE 스트리밍으로 처리

    Args:
        file_path: 원본 이미지 경로
        bbox: 크롭할 바운딩 박스 [x1, y1, x2, y2]
        db: 데이터베이스 세션

    Yields:
        SSE 형식의 진행 상황 및 결과
    """
    import cv2
    from studio.services.matcher import VehicleMatcher

    try:
        # 1단계: 진행 상황 전송
        yield f"data: {json.dumps({'event': 'progress', 'progress': 10, 'message': '이미지 크롭 중'})}\n\n"
        await asyncio.sleep(0.1)

        # 이미지 크롭
        image = cv2.imread(file_path)
        if image is None:
            raise ValueError("Failed to load image")

        h, w = image.shape[:2]
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        # 좌표 정규화: x1<x2, y1<y2 보장
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        # 이미지 범위 클램핑
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            raise ValueError(f"유효하지 않은 bbox: [{x1},{y1},{x2},{y2}] (이미지 크기: {w}x{h})")
        cropped = image[y1:y2, x1:x2]
        if cropped.size == 0:
            raise ValueError("크롭 결과가 비어있습니다")

        # 크롭된 이미지 저장 (날짜별 디렉토리)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        crop_dir = Path(f"data/crops/{date_str}")
        crop_dir.mkdir(parents=True, exist_ok=True)
        crop_path = crop_dir / f"{os.urandom(16).hex()}_crop.jpg"
        cv2.imwrite(str(crop_path), cropped)

        # 2단계: Vision API 호출
        api_label = "ChatGPT + Gemini 교차 검증 중" if settings.gemini_api_key else "ChatGPT Vision API 호출 중"
        yield f"data: {json.dumps({'event': 'progress', 'progress': 30, 'message': api_label})}\n\n"
        await asyncio.sleep(0.1)

        from studio.services.vision_backend import get_vision_backend
        vision_service = get_vision_backend()
        vision_result = await vision_service.analyze_vehicle_image(str(crop_path), db=db)

        yield f"data: {json.dumps({'event': 'progress', 'progress': 60, 'message': 'DB 매칭 중'})}\n\n"
        await asyncio.sleep(0.1)

        # 3단계: 기준 DB와 매칭 (auto_insert=True: 매칭 실패 시 자동으로 DB에 추가)
        matcher = VehicleMatcher(db, auto_insert=True)
        match_result = matcher.match_vehicle(
            vision_result.get("manufacturer_code", ""),
            vision_result.get("model_code", ""),
            vision_confidence=vision_result.get("confidence")  # Vision API 신뢰도 전달
        )

        yield f"data: {json.dumps({'event': 'progress', 'progress': 80, 'message': '결과 저장 중'})}\n\n"
        await asyncio.sleep(0.1)

        # 4단계: 분석 결과 저장 (한글명 사용)
        new_raw_result = {
            **vision_result,
            "original_image": file_path,
            "bbox": bbox
        }
        new_manufacturer = match_result["manufacturer"].korean_name if match_result["manufacturer"] else None
        new_model = match_result["model"].korean_name if match_result["model"] else None
        new_mf_id = match_result["manufacturer"].id if match_result["manufacturer"] else None
        new_model_id = match_result["model"].id if match_result["model"] else None
        new_confidence = match_result["overall_confidence"]

        analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first() if analyzed_id else None

        if analyzed:
            # 기존 크롭 이미지 삭제 (원본 이미지는 삭제하지 않음)
            if analyzed.image_path and analyzed.image_path != analyzed.original_image_path:
                old_crop = Path(analyzed.image_path)
                if old_crop.exists():
                    old_crop.unlink()
            # 기존 레코드 업데이트
            analyzed.image_path = str(crop_path)
            analyzed.raw_result = new_raw_result
            analyzed.manufacturer = new_manufacturer
            analyzed.model = new_model
            analyzed.year = vision_result.get("year")
            analyzed.matched_manufacturer_id = new_mf_id
            analyzed.matched_model_id = new_model_id
            analyzed.confidence_score = new_confidence
            analyzed.is_verified = False
            analyzed.processing_stage = 'analysis_complete'
            analyzed.selected_bbox = bbox
        else:
            analyzed = AnalyzedVehicle(
                image_path=str(crop_path),
                original_image_path=file_path,
                raw_result=new_raw_result,
                manufacturer=new_manufacturer,
                model=new_model,
                year=vision_result.get("year"),
                matched_manufacturer_id=new_mf_id,
                matched_model_id=new_model_id,
                confidence_score=new_confidence,
                is_verified=False,
                processing_stage='analysis_complete',
                selected_bbox=bbox,
            )
            db.add(analyzed)

        db.commit()
        db.refresh(analyzed)

        # 5단계: 완료 전송
        result = {
            "event": "completed",
            "progress": 100,
            "result": {
                "id": analyzed.id,
                "manufacturer": analyzed.manufacturer,
                "model": analyzed.model,
                "year": analyzed.year,
                "confidence_score": float(analyzed.confidence_score) if analyzed.confidence_score else 0.0,
                "matched_manufacturer_id": analyzed.matched_manufacturer_id,
                "matched_model_id": analyzed.matched_model_id
            }
        }

        yield f"data: {json.dumps(result)}\n\n"

    except Exception as e:
        # 에러 전송
        error_data = {
            "event": "error",
            "message": str(e)
        }
        yield f"data: {json.dumps(error_data)}\n\n"


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    source: str = Form('file'),
    client_uuid: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    """
    파일 즉시 업로드 (DB-First 아키텍처)

    파일 선택 시 즉시 서버에 업로드하고 analyzed_vehicles 레코드 생성
    YOLO 감지는 별도로 detect-vehicle 엔드포인트를 통해 실행
    """
    from datetime import datetime

    # 파일 확장자 검증
    file_ext = file.filename.split(".")[-1].lower()
    if file_ext not in settings.allowed_extensions_list:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension. Allowed: {settings.allowed_extensions}"
        )

    # 파일 크기 검증
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size > settings.max_upload_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Max size: {settings.max_upload_size / 1024 / 1024}MB"
        )

    # 파일 저장 (날짜별 디렉토리)
    date_str = datetime.now().strftime("%Y-%m-%d")
    data_dir = Path(f"data/uploads/{date_str}")
    data_dir.mkdir(parents=True, exist_ok=True)
    file_path = data_dir / f"{os.urandom(16).hex()}_{file.filename}"

    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # DB 레코드 생성
    analyzed = AnalyzedVehicle(
        image_path=str(file_path),
        original_image_path=str(file_path),
        processing_stage='uploaded',
        is_verified=False,
        source=source,
        client_uuid=client_uuid,
    )
    db.add(analyzed)
    db.commit()
    db.refresh(analyzed)

    return {"analyzed_id": analyzed.id, "original_image_path": str(file_path)}


@router.post("/analyze-vehicle-stream")
async def analyze_vehicle_stream(
    file: Optional[UploadFile] = File(None),
    bbox: str = Form(...),  # JSON 문자열로 받기
    analyzed_id: Optional[int] = Form(None),  # DB-first 업로드 ID 또는 재분석 레코드 ID
    db: Session = Depends(get_db)
):
    """
    차량 이미지 분석 (SSE 스트리밍)

    프론트엔드에서 선택한 바운딩 박스 영역을 크롭하여 ChatGPT Vision API로 분석
    진행 상황을 실시간으로 SSE 스트리밍
    analyzed_id가 있으면 DB의 original_image_path를 사용 (파일 재전송 불필요)
    """
    # bbox 파싱
    try:
        bbox_list = json.loads(bbox)
        if not isinstance(bbox_list, list) or len(bbox_list) != 4:
            raise ValueError("bbox must be [x1, y1, x2, y2]")
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bbox format: {str(e)}"
        )

    if analyzed_id:
        # DB에서 original_image_path 로드 (파일 재전송 불필요)
        analyzed_record = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
        if not analyzed_record or not analyzed_record.original_image_path:
            raise HTTPException(status_code=404, detail="Analyzed vehicle not found or no original image")
        file_path_str = analyzed_record.original_image_path

        return StreamingResponse(
            stream_analysis_progress(file_path_str, bbox_list, db, analyzed_id=analyzed_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )

    elif file:
        # 파일 확장자 검증 (하위 호환)
        file_ext = file.filename.split(".")[-1].lower()
        if file_ext not in settings.allowed_extensions_list:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed: {settings.allowed_extensions}"
            )

        # 파일 저장 (날짜별 디렉토리)
        from datetime import datetime
        date_str = datetime.now().strftime("%Y-%m-%d")
        data_dir = Path(f"data/uploads/{date_str}")
        data_dir.mkdir(parents=True, exist_ok=True)
        file_path = data_dir / f"{os.urandom(16).hex()}_{file.filename}"

        try:
            with open(file_path, "wb") as buffer:
                buffer.write(await file.read())

            return StreamingResponse(
                stream_analysis_progress(str(file_path), bbox_list, db, analyzed_id=None),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )

        except Exception as e:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=500,
                detail=f"Analysis failed: {str(e)}"
            )

    else:
        raise HTTPException(status_code=400, detail="Either file or analyzed_id must be provided")


#=============================================================================
# 일괄 분석 엔드포인트 (토큰 사용량 관리)
#=============================================================================

class BatchAnalysisRequest(BaseModel):
    """일괄 분석 요청"""
    image_ids: List[str]
    max_concurrent: int = 3  # 동시 처리 최대 개수


async def batch_stream_analysis(
    image_data_list: List[tuple],  # (file_path, bbox, image_id)
    db: Session,
    max_concurrent: int = 3
):
    """
    여러 이미지를 동시에 분석하되 토큰 사용량을 고려하여 제한

    Args:
        image_data_list: 분석할 이미지 데이터 리스트
        db: 데이터베이스 세션
        max_concurrent: 동시 처리 최대 개수

    Yields:
        SSE 형식의 진행 상황 및 결과
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def analyze_with_semaphore(file_path, bbox, image_id):
        async with semaphore:
            async for event in stream_analysis_progress(file_path, bbox, db):
                # 이미지 ID를 이벤트에 추가
                event_data = json.loads(event.strip().replace("data: ", ""))
                event_data["image_id"] = image_id
                yield f"data: {json.dumps(event_data)}\n\n"

    # 모든 이미지를 동시에 처리 (세마포어로 제한)
    tasks = []
    for file_path, bbox, image_id in image_data_list:
        task = analyze_with_semaphore(file_path, bbox, image_id)
        tasks.append(task)

    # 모든 태스크의 이벤트를 병합하여 스트리밍
    for task in tasks:
        async for event in task:
            yield event


#=============================================================================
# 실시간 분석 피드 (SSE)
#=============================================================================

@router.get("/pending-records")
async def get_pending_records(
    skip: int = 0,
    limit: int = 20,
    source: Optional[str] = None,
    client_uuid: Optional[str] = None,
    failure_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    레코드 페이지네이션 조회

    초기 hydration 및 무한 스크롤에 사용
    source, client_uuid로 탭별/사용자별 필터링 가능
    failure_only=true: 분석실패(analysis_error) + 탐지실패(no_vehicle) 레코드만 반환
    """
    from sqlalchemy import or_, and_, func as sql_func

    if failure_only:
        query = db.query(AnalyzedVehicle).filter(
            or_(
                and_(
                    AnalyzedVehicle.processing_stage == 'analysis_complete',
                    or_(
                        AnalyzedVehicle.manufacturer.is_(None),
                        AnalyzedVehicle.model.is_(None)
                    )
                ),
                and_(
                    AnalyzedVehicle.processing_stage == 'yolo_detected',
                    or_(
                        AnalyzedVehicle.yolo_detections.is_(None),
                        sql_func.json_length(AnalyzedVehicle.yolo_detections) == 0
                    )
                )
            )
        )
    else:
        query = db.query(AnalyzedVehicle).filter(
            AnalyzedVehicle.processing_stage.in_(['uploaded', 'yolo_detected', 'analysis_complete', 'verified'])
        )

    if source:
        query = query.filter(AnalyzedVehicle.source == source)
    if client_uuid:
        query = query.filter(AnalyzedVehicle.client_uuid == client_uuid)

    total = query.count()
    records = query.order_by(AnalyzedVehicle.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "items": [r.to_dict() for r in records],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total
    }


@router.get("/analyze-feed")
async def analyze_feed(client_uuid: Optional[str] = None, source: Optional[str] = None):
    """
    분석 레코드 실시간 피드 (SSE)

    3초마다 업데이트된 레코드 스트리밍 (초기 데이터는 /api/pending-records 사용)
    client_uuid로 사용자별, source로 탭별 필터링 가능
    """
    from datetime import datetime
    from studio.models.database import SessionLocal

    async def event_generator():
        last_check = datetime.now()

        # 3초마다 업데이트 체크
        while True:
            await asyncio.sleep(3)
            current_check = datetime.now()

            db = SessionLocal()
            try:
                query = db.query(AnalyzedVehicle).filter(
                    AnalyzedVehicle.updated_at >= last_check,
                    AnalyzedVehicle.is_verified == False
                )
                if client_uuid:
                    query = query.filter(AnalyzedVehicle.client_uuid == client_uuid)
                if source:
                    query = query.filter(AnalyzedVehicle.source == source)
                updated = query.all()
                for record in updated:
                    yield f"data: {json.dumps({'type': 'record_updated', 'record': record.to_dict()})}\n\n"
            finally:
                db.close()

            last_check = current_check

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# TODO: 추가 예정
# - POST /api/analyze/batch (일괄 분석 - 구현 필요)
# - GET /api/analysis-history (분석 이력)
