"""
관리자 API 라우터
기준 데이터 관리, 이미지 분석, 검수 등
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import logging
import json
import asyncio

from studio.models import get_db
from studio.models.database import SessionLocal
from studio.models.manufacturer import Manufacturer
from studio.models.vehicle_model import VehicleModel
from studio.models.analyzed_vehicle import AnalyzedVehicle
from studio.services.crop_utils import ensure_cropped_image

router = APIRouter()
logger = logging.getLogger(__name__)


def _av_tab_subquery(db: Session, status: Optional[str], review_status: Optional[str], id_col):
    """탭 필터 조건에 맞는 AnalyzedVehicle 에서 id_col 값의 distinct 서브쿼리를 반환."""
    from sqlalchemy import func as _func, or_ as _or
    q = db.query(id_col).filter(id_col != None)
    if status == 'uploaded':
        q = q.filter(AnalyzedVehicle.processing_stage == 'uploaded')
    elif status == 'yolo_failed':
        q = q.filter(
            AnalyzedVehicle.processing_stage == 'yolo_detected',
            _or(AnalyzedVehicle.yolo_detections == None,
                _func.json_length(AnalyzedVehicle.yolo_detections) == 0),
        )
    elif status == 'analysis_complete':
        q = q.filter(
            AnalyzedVehicle.processing_stage == 'analysis_complete',
            AnalyzedVehicle.review_status == 'pending',
        )
    if review_status and review_status in {'pending', 'approved', 'on_hold', 'rejected'}:
        q = q.filter(AnalyzedVehicle.review_status == review_status)
    return q.distinct()


# Pydantic 스키마 정의
class ManufacturerCreate(BaseModel):
    """제조사 생성 요청"""
    code: str
    english_name: str
    korean_name: str
    is_domestic: bool = False


class ManufacturerResponse(BaseModel):
    """제조사 응답"""
    id: int
    code: str
    english_name: str
    korean_name: str
    is_domestic: bool
    created_at: datetime

    class Config:
        from_attributes = True


class VehicleModelCreate(BaseModel):
    """차량 모델 생성 요청"""
    code: str
    manufacturer_id: int
    manufacturer_code: str
    english_name: str
    korean_name: str


class VehicleModelResponse(BaseModel):
    """차량 모델 응답"""
    id: int
    code: str
    manufacturer_id: int
    manufacturer_code: str
    english_name: str
    korean_name: str
    created_at: datetime

    class Config:
        from_attributes = True


# 제조사 관리 API
@router.get("/manufacturers", response_model=List[ManufacturerResponse])
async def get_manufacturers(
    skip: int = 0,
    limit: int = 100,
    is_domestic: Optional[bool] = None,
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """제조사 목록 조회.
    status / review_status 를 넘기면 해당 탭에 데이터가 있는 제조사만 반환.
    """
    query = db.query(Manufacturer)

    if is_domestic is not None:
        query = query.filter(Manufacturer.is_domestic == is_domestic)

    if status or review_status:
        sub = _av_tab_subquery(db, status, review_status, AnalyzedVehicle.matched_manufacturer_id)
        query = query.filter(Manufacturer.id.in_(sub))

    manufacturers = query.offset(skip).limit(limit).all()
    return manufacturers


@router.post("/manufacturers", response_model=ManufacturerResponse, status_code=status.HTTP_201_CREATED)
async def create_manufacturer(manufacturer: ManufacturerCreate, db: Session = Depends(get_db)):
    """제조사 생성"""
    # 중복 체크
    existing = db.query(Manufacturer).filter(Manufacturer.code == manufacturer.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Manufacturer code already exists")

    db_manufacturer = Manufacturer(**manufacturer.model_dump())
    db.add(db_manufacturer)
    db.commit()
    db.refresh(db_manufacturer)
    return db_manufacturer


# 차량 모델 관리 API
@router.get("/vehicle-models", response_model=List[VehicleModelResponse])
async def get_vehicle_models(
    skip: int = 0,
    limit: int = 100,
    manufacturer_id: Optional[int] = None,
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """차량 모델 목록 조회.
    status / review_status 를 넘기면 해당 탭에 데이터가 있는 모델만 반환.
    """
    query = db.query(VehicleModel)

    if manufacturer_id is not None:
        query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)

    if status or review_status:
        sub = _av_tab_subquery(db, status, review_status, AnalyzedVehicle.matched_model_id)
        query = query.filter(VehicleModel.id.in_(sub))

    models = query.offset(skip).limit(limit).all()
    return models


@router.post("/vehicle-models", response_model=VehicleModelResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle_model(model: VehicleModelCreate, db: Session = Depends(get_db)):
    """차량 모델 생성"""
    # 제조사 존재 확인
    manufacturer = db.query(Manufacturer).filter(Manufacturer.id == model.manufacturer_id).first()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")

    db_model = VehicleModel(**model.model_dump())
    db.add(db_model)
    db.commit()
    db.refresh(db_model)
    return db_model


# 검수 관리 API
@router.get("/analyzed-vehicles")
async def get_all_analyzed_vehicles(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    review_status: Optional[str] = None,
    manufacturer_id: Optional[int] = None,
    model_id: Optional[int] = None,
    min_confidence: Optional[float] = None,
    max_confidence: Optional[float] = None,
    sort: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """전체 분석 레코드 조회 (차량데이터 관리용)

    status 필터 (호환용, processing_stage/is_verified 기준):
      uploaded / yolo_failed / yolo_detected / analysis_complete / verified

    review_status 필터 (신규):
      pending / approved / on_hold / rejected

    min_confidence / max_confidence: confidence_score 0~100 범위 필터
    sort: created_desc(default) / created_asc / confidence_desc / confidence_asc
    """
    from sqlalchemy import func as _func, or_ as _or

    query = db.query(AnalyzedVehicle)

    if status == 'uploaded':
        query = query.filter(AnalyzedVehicle.processing_stage == 'uploaded')
    elif status == 'yolo_failed':
        query = query.filter(
            AnalyzedVehicle.processing_stage == 'yolo_detected',
            _or(
                AnalyzedVehicle.yolo_detections == None,
                _func.json_length(AnalyzedVehicle.yolo_detections) == 0,
            )
        )
    elif status == 'yolo_detected':
        query = query.filter(
            AnalyzedVehicle.processing_stage == 'yolo_detected',
            _func.json_length(AnalyzedVehicle.yolo_detections) > 0,
        )
    elif status == 'analysis_complete':
        query = query.filter(
            AnalyzedVehicle.processing_stage == 'analysis_complete',
            AnalyzedVehicle.review_status == 'pending'
        )
    elif status == 'verified':
        query = query.filter(AnalyzedVehicle.review_status == 'approved')

    if review_status and review_status in VALID_REVIEW_STATUSES:
        query = query.filter(AnalyzedVehicle.review_status == review_status)

    if manufacturer_id is not None:
        query = query.filter(AnalyzedVehicle.matched_manufacturer_id == manufacturer_id)
    if model_id is not None:
        query = query.filter(AnalyzedVehicle.matched_model_id == model_id)

    if min_confidence is not None:
        query = query.filter(AnalyzedVehicle.confidence_score >= min_confidence)
    if max_confidence is not None:
        query = query.filter(AnalyzedVehicle.confidence_score <= max_confidence)

    sort_map = {
        'created_desc': AnalyzedVehicle.created_at.desc(),
        'created_asc': AnalyzedVehicle.created_at.asc(),
        'confidence_desc': AnalyzedVehicle.confidence_score.desc(),
        'confidence_asc': AnalyzedVehicle.confidence_score.asc(),
    }
    order_by = sort_map.get(sort or 'created_desc', AnalyzedVehicle.created_at.desc())

    total = query.count()
    items = query.order_by(order_by).offset(skip).limit(limit).all()

    return {
        "total": total,
        "items": [item.to_dict(include_raw=True) for item in items]
    }


@router.get("/analyzed-vehicles-counts")
def get_analyzed_vehicles_counts(db: Session = Depends(get_db)):
    """탭별 건수 + 신뢰도 통계를 단일 쿼리로 반환 (뱃지/대시보드용)"""
    from sqlalchemy import case
    from sqlalchemy.sql import func as sql_func

    row = db.query(
        sql_func.count().label("all"),
        sql_func.sum(case((AnalyzedVehicle.processing_stage == 'uploaded', 1), else_=0)).label("uploaded"),
        sql_func.sum(case(
            (
                (AnalyzedVehicle.processing_stage == 'yolo_detected') &
                (
                    (AnalyzedVehicle.yolo_detections == None) |
                    (sql_func.json_length(AnalyzedVehicle.yolo_detections) == 0)
                ),
                1
            ), else_=0
        )).label("yolo_failed"),
        sql_func.sum(case(
            (
                (AnalyzedVehicle.processing_stage == 'yolo_detected') &
                (sql_func.json_length(AnalyzedVehicle.yolo_detections) > 0),
                1
            ), else_=0
        )).label("yolo_detected"),
        sql_func.sum(case(
            (
                (AnalyzedVehicle.processing_stage == 'analysis_complete') &
                (AnalyzedVehicle.review_status == 'pending'),
                1
            ), else_=0
        )).label("analysis_complete"),
        sql_func.sum(case((AnalyzedVehicle.review_status == 'pending', 1), else_=0)).label("pending"),
        sql_func.sum(case((AnalyzedVehicle.review_status == 'on_hold', 1), else_=0)).label("on_hold"),
        sql_func.sum(case((AnalyzedVehicle.review_status == 'approved', 1), else_=0)).label("approved"),
        sql_func.sum(case((AnalyzedVehicle.review_status == 'rejected', 1), else_=0)).label("rejected"),
        sql_func.avg(AnalyzedVehicle.confidence_score).label("avg_confidence"),
        sql_func.sum(case(
            ((AnalyzedVehicle.confidence_score >= 85), 1), else_=0
        )).label("high_confidence"),
        sql_func.sum(case(
            ((AnalyzedVehicle.confidence_score >= 60) & (AnalyzedVehicle.confidence_score < 85), 1), else_=0
        )).label("mid_confidence"),
        sql_func.sum(case(
            ((AnalyzedVehicle.confidence_score < 60), 1), else_=0
        )).label("low_confidence"),
    ).one()

    avg_conf = float(row.avg_confidence) if row.avg_confidence is not None else None

    return {
        "all": row.all or 0,
        "uploaded": row.uploaded or 0,
        "yolo_failed": row.yolo_failed or 0,
        "yolo_detected": row.yolo_detected or 0,
        "analysis_complete": row.analysis_complete or 0,
        "pending": row.pending or 0,
        "on_hold": row.on_hold or 0,
        "approved": row.approved or 0,
        "rejected": row.rejected or 0,
        # 호환: 기존 클라이언트가 'verified' 키를 기대할 수 있음
        "verified": row.approved or 0,
        "avg_confidence": round(avg_conf, 2) if avg_conf is not None else None,
        "high_confidence": row.high_confidence or 0,
        "mid_confidence": row.mid_confidence or 0,
        "low_confidence": row.low_confidence or 0,
    }


@router.get("/review-queue")
async def get_review_queue(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """검수 대기 목록 조회 (페이징 지원)"""
    from sqlalchemy import func as sql_func

    total = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
        AnalyzedVehicle.is_verified == False
    ).scalar()

    analyzed = db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).order_by(AnalyzedVehicle.id.desc()).offset(skip).limit(limit).all()

    return {
        "items": [item.to_dict() for item in analyzed],
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total
    }


class AnalyzedVehicleUpdate(BaseModel):
    """분석 결과 수정 요청"""
    matched_manufacturer_id: int
    matched_model_id: int
    manufacturer: Optional[str] = None
    model: Optional[str] = None


class ReviewActionRequest(BaseModel):
    """보류/반려/재열기 등 검수 액션 요청"""
    reason: Optional[str] = None


class BatchActionRequest(BaseModel):
    """일괄 액션 요청"""
    action: str  # 'approve' | 'hold' | 'reject'
    ids: List[int]
    reason: Optional[str] = None


VALID_REVIEW_STATUSES = {'pending', 'approved', 'on_hold', 'rejected'}


def _remove_from_training(analyzed: AnalyzedVehicle, db: Session) -> bool:
    """TrainingDataset에서 해당 image_path 항목 제거. 제거되었으면 True."""
    from studio.models.training_dataset import TrainingDataset
    if not analyzed.image_path:
        return False
    existing = db.query(TrainingDataset).filter(
        TrainingDataset.image_path == analyzed.image_path
    ).first()
    if existing:
        db.delete(existing)
        db.flush()
        return True
    return False


def _upsert_training(analyzed: AnalyzedVehicle, db: Session) -> bool:
    """TrainingDataset upsert. 추가 또는 매칭 변경되었으면 True."""
    from studio.models.training_dataset import TrainingDataset
    if not (analyzed.matched_manufacturer_id and analyzed.matched_model_id):
        return False
    existing = db.query(TrainingDataset).filter(
        TrainingDataset.image_path == analyzed.image_path
    ).first()
    if existing:
        if (existing.manufacturer_id != analyzed.matched_manufacturer_id
                or existing.model_id != analyzed.matched_model_id):
            existing.manufacturer_id = analyzed.matched_manufacturer_id
            existing.model_id = analyzed.matched_model_id
            db.flush()
            return True
        return False
    db.add(TrainingDataset(
        image_path=analyzed.image_path,
        manufacturer_id=analyzed.matched_manufacturer_id,
        model_id=analyzed.matched_model_id,
    ))
    db.flush()
    return True


@router.patch("/review/{analyzed_id}")
async def update_analyzed_vehicle(
    analyzed_id: int,
    update_data: AnalyzedVehicleUpdate,
    db: Session = Depends(get_db)
):
    """분석 결과 수정 (제조사/모델 변경).

    review_status='approved' 인 항목을 수정하면 TrainingDataset도 즉시 upsert해
    학습셋과 일관성을 유지한다 (재검수 흐름).
    """
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    manufacturer = db.query(Manufacturer).filter(
        Manufacturer.id == update_data.matched_manufacturer_id
    ).first()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")

    model = db.query(VehicleModel).filter(
        VehicleModel.id == update_data.matched_model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail="Vehicle model not found")

    analyzed.matched_manufacturer_id = update_data.matched_manufacturer_id
    analyzed.matched_model_id = update_data.matched_model_id
    analyzed.manufacturer = update_data.manufacturer or manufacturer.korean_name
    analyzed.model = update_data.model or model.korean_name

    ensure_cropped_image(analyzed)

    training_synced = False
    if analyzed.review_status == 'approved':
        try:
            training_synced = _upsert_training(analyzed, db)
            analyzed.verified_at = datetime.now()
        except Exception as e:
            db.rollback()
            logger.error(f"PATCH /review/{analyzed_id}: TrainingDataset 동기화 실패 - {e}")
            raise HTTPException(status_code=500, detail=f"학습 데이터 동기화 실패: {e}")

    db.commit()
    db.refresh(analyzed)

    return {
        "message": "Updated successfully",
        "data": analyzed.to_dict(),
        "training_synced": training_synced,
    }


@router.post("/review/batch-save-all")
async def batch_save_all_to_training():
    """is_verified=false인 전체 항목을 학습 데이터로 일괄 저장 (SSE 스트리밍, 커서 기반 페이지네이션)"""
    from sqlalchemy import func as sql_func
    from studio.models.training_dataset import TrainingDataset

    BATCH_SIZE = 100

    # 초기 카운트 조회 후 즉시 세션 반환 (보류/반려는 제외 → pending만 대상)
    with SessionLocal() as db:
        total_unverified = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
            AnalyzedVehicle.review_status == 'pending'
        ).scalar()
        total = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
            AnalyzedVehicle.review_status == 'pending',
            AnalyzedVehicle.matched_manufacturer_id.isnot(None),
            AnalyzedVehicle.matched_model_id.isnot(None)
        ).scalar()

    skipped = total_unverified - total

    async def generate():
        succeeded = 0
        failed = 0
        failed_ids = []
        current = 0
        last_id = None  # desc 순이므로 None부터 시작

        # 시작 이벤트
        yield f"data: {json.dumps({'type': 'start', 'total': total, 'total_unverified': total_unverified, 'skipped': skipped})}\n\n"

        while True:
            # 배치마다 새 세션으로 짧게 커넥션 점유
            with SessionLocal() as db:
                query = db.query(AnalyzedVehicle).options(
                    joinedload(AnalyzedVehicle.matched_manufacturer),
                    joinedload(AnalyzedVehicle.matched_model)
                ).filter(
                    AnalyzedVehicle.review_status == 'pending',
                    AnalyzedVehicle.matched_manufacturer_id.isnot(None),
                    AnalyzedVehicle.matched_model_id.isnot(None)
                ).order_by(AnalyzedVehicle.id.desc())

                if last_id is not None:
                    query = query.filter(AnalyzedVehicle.id < last_id)

                batch = query.limit(BATCH_SIZE).all()

                if not batch:
                    break

                # 학습 데이터에는 반드시 크롭된 이미지가 필요 → 원본 그대로인 항목은 즉석 크롭
                crop_dirty = False
                for a in batch:
                    if a.image_path == a.original_image_path:
                        if ensure_cropped_image(a):
                            crop_dirty = True
                if crop_dirty:
                    db.commit()

                batch_data = [
                    {
                        "id": a.id,
                        "image_path": a.image_path,
                        "original_image_path": a.original_image_path,
                        "matched_manufacturer_id": a.matched_manufacturer_id,
                        "matched_model_id": a.matched_model_id,
                    }
                    for a in batch
                ]
                last_id = batch[-1].id

            for item in batch_data:
                current += 1

                # 크롭이 보장되지 않은 항목은 학습 데이터로 적재하지 않음
                if item["image_path"] == item["original_image_path"]:
                    failed += 1
                    failed_ids.append(item["id"])
                    yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': item['id'], 'reason': 'no_crop'})}\n\n"
                    await asyncio.sleep(0.05)
                    continue

                try:
                    # training_dataset upsert
                    with SessionLocal() as db:
                        existing = db.query(TrainingDataset).filter(
                            TrainingDataset.image_path == item["image_path"]
                        ).first()

                        if existing:
                            if (existing.manufacturer_id != item["matched_manufacturer_id"]
                                    or existing.model_id != item["matched_model_id"]):
                                existing.manufacturer_id = item["matched_manufacturer_id"]
                                existing.model_id = item["matched_model_id"]
                                db.commit()
                        else:
                            training_data = TrainingDataset(
                                image_path=item["image_path"],
                                manufacturer_id=item["matched_manufacturer_id"],
                                model_id=item["matched_model_id"],
                            )
                            db.add(training_data)
                            db.commit()

                except Exception as e:
                    logger.error(f"Batch save: {item['id']} training_data failed - {e}")

                # 검수 상태 업데이트
                try:
                    with SessionLocal() as db:
                        analyzed_fresh = db.query(AnalyzedVehicle).filter(
                            AnalyzedVehicle.id == item["id"]
                        ).first()
                        if analyzed_fresh and analyzed_fresh.review_status != 'approved':
                            analyzed_fresh.is_verified = True
                            analyzed_fresh.review_status = 'approved'
                            analyzed_fresh.review_reason = None
                            analyzed_fresh.verified_by = "admin"
                            analyzed_fresh.verified_at = datetime.now()
                            db.commit()

                    succeeded += 1
                    logger.info(f"Batch save: {item['id']} succeeded ({current}/{total})")

                except Exception as e:
                    logger.error(f"Batch save: {item['id']} is_verified update failed - {e}")
                    failed += 1
                    failed_ids.append(item["id"])

                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': item['id']})}\n\n"

                await asyncio.sleep(0.1)

        yield f"data: {json.dumps({'type': 'done', 'total': total, 'succeeded': succeeded, 'failed': failed, 'failed_ids': failed_ids})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/review/{analyzed_id}")
async def save_to_training(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """검수 승인: 학습 데이터 적재 + is_verified 업데이트"""
    from datetime import datetime
    from sqlalchemy.orm import joinedload
    from studio.models.training_dataset import TrainingDataset

    analyzed = db.query(AnalyzedVehicle).options(
        joinedload(AnalyzedVehicle.matched_manufacturer),
        joinedload(AnalyzedVehicle.matched_model)
    ).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    if not analyzed.matched_manufacturer_id or not analyzed.matched_model_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot save: manufacturer and model must be identified"
        )

    # 학습 데이터에는 반드시 크롭된 이미지가 들어가야 함
    if not ensure_cropped_image(analyzed):
        if analyzed.image_path == analyzed.original_image_path:
            raise HTTPException(
                status_code=400,
                detail="크롭 이미지가 없고 bbox 정보도 없습니다. 수정 모달에서 영역을 지정 후 다시 시도하세요."
            )
    db.flush()

    # 1) training_dataset upsert
    try:
        existing = db.query(TrainingDataset).filter(
            TrainingDataset.image_path == analyzed.image_path
        ).first()

        if existing:
            if (existing.manufacturer_id != analyzed.matched_manufacturer_id
                    or existing.model_id != analyzed.matched_model_id):
                existing.manufacturer_id = analyzed.matched_manufacturer_id
                existing.model_id = analyzed.matched_model_id
                db.flush()
                logger.info(f"Updated training_dataset: {existing.id}")
        else:
            training_data = TrainingDataset(
                image_path=analyzed.image_path,
                manufacturer_id=analyzed.matched_manufacturer_id,
                model_id=analyzed.matched_model_id,
            )
            db.add(training_data)
            db.flush()
            logger.info(f"Added training_dataset: {training_data.id}")

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save training data: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"학습 데이터 저장 실패: {str(e)}"
        )

    # 2) 검수 상태 업데이트
    try:
        analyzed.is_verified = True
        analyzed.review_status = 'approved'
        analyzed.review_reason = None
        analyzed.verified_by = "admin"
        analyzed.verified_at = datetime.now()
        db.commit()
        db.refresh(analyzed)

        return {"message": "검수 승인 완료", "data": analyzed.to_dict()}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update review_status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"검수 상태 업데이트 실패: {str(e)}"
        )


@router.post("/review/{analyzed_id}/hold")
async def hold_analyzed_vehicle(
    analyzed_id: int,
    payload: ReviewActionRequest = ReviewActionRequest(),
    db: Session = Depends(get_db)
):
    """검수 보류: TrainingDataset에서 제거 + review_status='on_hold'."""
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    removed = _remove_from_training(analyzed, db)
    analyzed.review_status = 'on_hold'
    analyzed.review_reason = payload.reason
    analyzed.is_verified = False
    db.commit()
    db.refresh(analyzed)
    return {
        "message": "검수 보류 처리 완료",
        "data": analyzed.to_dict(),
        "training_removed": removed,
    }


@router.post("/review/{analyzed_id}/reject")
async def reject_analyzed_vehicle(
    analyzed_id: int,
    payload: ReviewActionRequest = ReviewActionRequest(),
    db: Session = Depends(get_db)
):
    """검수 반려: TrainingDataset에서 제거 + review_status='rejected'.

    DELETE와 달리 이미지 파일과 분석 레코드는 보존(통계/감사용).
    """
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    removed = _remove_from_training(analyzed, db)
    analyzed.review_status = 'rejected'
    analyzed.review_reason = payload.reason
    analyzed.is_verified = False
    db.commit()
    db.refresh(analyzed)
    return {
        "message": "검수 반려 처리 완료",
        "data": analyzed.to_dict(),
        "training_removed": removed,
    }


@router.post("/review/{analyzed_id}/reopen")
async def reopen_analyzed_vehicle(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """검수 상태를 pending으로 되돌림.

    approved 상태였다면 TrainingDataset에서도 제거(학습셋과 분리).
    """
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    removed = False
    if analyzed.review_status == 'approved':
        removed = _remove_from_training(analyzed, db)

    analyzed.review_status = 'pending'
    analyzed.review_reason = None
    analyzed.is_verified = False
    analyzed.verified_at = None
    db.commit()
    db.refresh(analyzed)
    return {
        "message": "검수 상태가 대기로 변경됨",
        "data": analyzed.to_dict(),
        "training_removed": removed,
    }


@router.post("/review/batch-action")
async def batch_review_action(payload: BatchActionRequest):
    """선택된 ID 목록에 대해 일괄 검수 액션 (SSE 스트리밍).

    action: approve | hold | reject
    """
    from studio.models.training_dataset import TrainingDataset

    if payload.action not in ('approve', 'hold', 'reject'):
        raise HTTPException(status_code=400, detail="action은 approve|hold|reject 중 하나여야 합니다")

    ids = list(dict.fromkeys(payload.ids))  # 중복 제거, 순서 유지
    if not ids:
        raise HTTPException(status_code=400, detail="ids가 비어 있습니다")

    action = payload.action
    reason = payload.reason
    total = len(ids)

    async def generate():
        succeeded = 0
        failed = 0
        failed_ids: list[int] = []
        current = 0

        yield f"data: {json.dumps({'type': 'start', 'total': total, 'action': action})}\n\n"

        for vid in ids:
            current += 1
            try:
                with SessionLocal() as db:
                    analyzed = db.query(AnalyzedVehicle).filter(
                        AnalyzedVehicle.id == vid
                    ).first()
                    if not analyzed:
                        failed += 1
                        failed_ids.append(vid)
                        yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': vid, 'reason': 'not_found'})}\n\n"
                        continue

                    if action == 'approve':
                        if not (analyzed.matched_manufacturer_id and analyzed.matched_model_id):
                            failed += 1
                            failed_ids.append(vid)
                            yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': vid, 'reason': 'no_match'})}\n\n"
                            continue
                        if not ensure_cropped_image(analyzed):
                            if analyzed.image_path == analyzed.original_image_path:
                                failed += 1
                                failed_ids.append(vid)
                                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': vid, 'reason': 'no_crop'})}\n\n"
                                continue
                        db.flush()
                        _upsert_training(analyzed, db)
                        analyzed.is_verified = True
                        analyzed.review_status = 'approved'
                        analyzed.review_reason = None
                        analyzed.verified_by = "admin"
                        analyzed.verified_at = datetime.now()
                    elif action == 'hold':
                        _remove_from_training(analyzed, db)
                        analyzed.review_status = 'on_hold'
                        analyzed.review_reason = reason
                        analyzed.is_verified = False
                    elif action == 'reject':
                        _remove_from_training(analyzed, db)
                        analyzed.review_status = 'rejected'
                        analyzed.review_reason = reason
                        analyzed.is_verified = False

                    db.commit()
                    succeeded += 1

                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': vid})}\n\n"
            except Exception as e:
                logger.error(f"batch-action {action} id={vid} failed: {e}")
                failed += 1
                failed_ids.append(vid)
                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': vid, 'reason': 'error'})}\n\n"

            await asyncio.sleep(0.02)

        yield f"data: {json.dumps({'type': 'done', 'total': total, 'succeeded': succeeded, 'failed': failed, 'failed_ids': failed_ids})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _delete_analyzed_vehicle(analyzed: AnalyzedVehicle, db: Session) -> dict:
    """analyzed_vehicle 레코드 하나를 완전 삭제.

    삭제 대상:
    - 크롭 이미지 파일
    - 원본 업로드 이미지 파일 (raw_result["original_image"] + original_image_path 둘 다)
    - training_dataset 레코드 (존재할 경우)
    - analyzed_vehicles DB 레코드 (호출자가 commit 해야 함)

    반환: {"deleted_files": int, "failed_files": int}
    """
    import os
    from studio.models.training_dataset import TrainingDataset

    deleted_files = 0
    failed_files = 0

    # 1. 크롭 이미지 삭제
    if analyzed.image_path and os.path.exists(analyzed.image_path):
        try:
            os.remove(analyzed.image_path)
            deleted_files += 1
        except Exception as e:
            logger.warning(f"Failed to delete crop file {analyzed.image_path}: {e}")
            failed_files += 1

    # 2. 원본 업로드 이미지 삭제 (두 경로 모두 확인)
    original_paths = set()
    if analyzed.raw_result and isinstance(analyzed.raw_result, dict):
        p = analyzed.raw_result.get("original_image")
        if p:
            original_paths.add(p)
    if analyzed.original_image_path:
        original_paths.add(analyzed.original_image_path)

    for original_path in original_paths:
        if original_path != analyzed.image_path and os.path.exists(original_path):
            try:
                os.remove(original_path)
                deleted_files += 1
            except Exception as e:
                logger.warning(f"Failed to delete original file {original_path}: {e}")
                failed_files += 1

    # 3. training_dataset 삭제 (존재할 경우)
    try:
        training = db.query(TrainingDataset).filter(
            TrainingDataset.image_path == analyzed.image_path
        ).first()
        if training:
            db.delete(training)
            db.flush()
    except Exception as e:
        logger.warning(f"Failed to cleanup training_dataset for analyzed_id={analyzed.id}: {e}")

    # 4. analyzed_vehicles 레코드 삭제
    db.delete(analyzed)

    return {"deleted_files": deleted_files, "failed_files": failed_files}


@router.delete("/review-delete-all")
async def batch_delete_all_analyzed_vehicles(
    db: Session = Depends(get_db)
):
    """미검수 분석 결과 전체 삭제 (이미지 파일 + training_dataset + DB 레코드)"""
    all_unverified = db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).all()

    total = len(all_unverified)
    deleted_files = 0
    failed_files = 0

    for analyzed in all_unverified:
        result = _delete_analyzed_vehicle(analyzed, db)
        deleted_files += result["deleted_files"]
        failed_files += result["failed_files"]

    db.commit()

    logger.info(f"Batch deleted {total} unverified records, {deleted_files} files deleted, {failed_files} file errors")
    return {
        "message": f"{total}개 레코드 전체 삭제 완료",
        "total": total,
        "deleted_files": deleted_files,
        "failed_files": failed_files
    }


@router.delete("/review/{analyzed_id}")
async def delete_analyzed_vehicle(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """분석 결과 삭제 (크롭 이미지 + 원본 업로드 파일 + training_dataset + MySQL 레코드)"""
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    _delete_analyzed_vehicle(analyzed, db)
    db.commit()

    return {"message": "Deleted successfully"}


@router.post("/analyze/{analyzed_id}")
async def analyze_single_image(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """
    단일 이미지 재분석 (기존 크롭 또는 bbox 기반)

    - 기존 크롭이 있으면(image_path != original_image_path) → 그대로 사용
    - 크롭이 없으면 selected_bbox → yolo_detections[0] 순서로 크롭 생성
    """
    import cv2
    import os as _os
    from pathlib import Path
    from studio.services.vision_backend import get_vision_backend
    from studio.services.matcher import VehicleMatcher
    from studio.config import settings as _settings

    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    is_local = _settings.vision_backend == "local_inference"

    try:
        target_path = analyzed.image_path

        if is_local:
            # 자체 추론 모드: 자체 API가 YOLO+분류를 모두 수행하므로 crop 우회.
            # 원본 이미지를 그대로 전달하고, selected_bbox는 vision 응답으로 갱신한다.
            target_path = analyzed.original_image_path
        elif analyzed.image_path == analyzed.original_image_path:
            # 크롭이 없는 경우(원본 == image_path) → bbox로 크롭 생성
            bbox = analyzed.selected_bbox
            if not bbox and analyzed.yolo_detections:
                bbox = analyzed.yolo_detections[0].get("bbox")
            if not bbox:
                raise ValueError("크롭 이미지가 없고 bbox 정보도 없습니다. 수정 모달에서 영역을 선택 후 재분석해주세요.")

            image = cv2.imread(analyzed.original_image_path)
            if image is None:
                raise ValueError("원본 이미지를 읽을 수 없습니다.")

            h, w = image.shape[:2]
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            x1, x2 = min(x1, x2), max(x1, x2)
            y1, y2 = min(y1, y2), max(y1, y2)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                raise ValueError(f"유효하지 않은 bbox: [{x1},{y1},{x2},{y2}]")

            from datetime import datetime
            date_str = datetime.now().strftime("%Y-%m-%d")
            crop_dir = Path(f"data/crops/{date_str}")
            crop_dir.mkdir(parents=True, exist_ok=True)
            crop_path = crop_dir / f"{_os.urandom(16).hex()}_crop.jpg"
            cv2.imwrite(str(crop_path), image[y1:y2, x1:x2])

            analyzed.image_path = str(crop_path)
            analyzed.selected_bbox = bbox
            target_path = str(crop_path)

        vision_service = get_vision_backend()
        # Vision 프롬프트 캐시 준비 후 커넥션 반환
        vision_service.preload_db_context(db)
        db.close()

        # Vision API 호출 (DB 커넥션 미점유)
        vision_result = await vision_service.analyze_vehicle_image(target_path)

        # 매칭 및 저장 (짧은 세션)
        with SessionLocal() as write_db:
            matcher = VehicleMatcher(write_db, auto_insert=True)
            match_result = matcher.match_vehicle(
                vision_result.get("manufacturer_code", "") or "",
                vision_result.get("model_code", "") or "",
                vision_confidence=vision_result.get("confidence")
            )

            analyzed_fresh = write_db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
            if not analyzed_fresh:
                raise ValueError("Record not found after re-query")
            analyzed_fresh.raw_result = vision_result
            analyzed_fresh.manufacturer = match_result["manufacturer"].korean_name if match_result["manufacturer"] else None
            analyzed_fresh.model = match_result["model"].korean_name if match_result["model"] else None
            analyzed_fresh.matched_manufacturer_id = match_result["manufacturer"].id if match_result["manufacturer"] else None
            analyzed_fresh.matched_model_id = match_result["model"].id if match_result["model"] else None
            analyzed_fresh.confidence_score = match_result["overall_confidence"]
            analyzed_fresh.processing_stage = 'analysis_complete'
            analyzed_fresh.is_verified = False
            analyzed_fresh.review_status = 'pending'
            analyzed_fresh.review_reason = None

            # 자체 추론 모드: 응답의 bbox로 selected_bbox 갱신, image_path는 원본 유지
            if is_local:
                local_bbox = vision_result.get("selected_bbox")
                if local_bbox:
                    analyzed_fresh.selected_bbox = local_bbox
                analyzed_fresh.image_path = analyzed_fresh.original_image_path

            write_db.commit()
            write_db.refresh(analyzed_fresh)
            result_dict = analyzed_fresh.to_dict()

        return {
            "message": "Analysis completed",
            "data": result_dict
        }

    except Exception as e:
        logger.error(f"Failed to analyze image {analyzed_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


# 데이터베이스 통계 조회
@router.get("/db-stats")
async def get_database_stats(db: Session = Depends(get_db)):
    """
    데이터베이스 통계 정보 및 정리 대상 확인

    Returns:
        - analyzed_vehicles 통계 (전체/검수완료/미검수/가장 오래된 데이터)
        - training_dataset 통계
        - 정리 대상 통계 (retention 정책 기반)
    """
    from sqlalchemy import func as sql_func
    from studio.models.training_dataset import TrainingDataset
    from studio.tasks.cleanup import get_cleanup_stats

    # analyzed_vehicles 통계
    analyzed_total = db.query(sql_func.count(AnalyzedVehicle.id)).scalar()
    analyzed_verified = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
        AnalyzedVehicle.is_verified == True
    ).scalar()
    analyzed_unverified = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
        AnalyzedVehicle.is_verified == False
    ).scalar()

    oldest_analyzed = db.query(sql_func.min(AnalyzedVehicle.created_at)).scalar()
    newest_analyzed = db.query(sql_func.max(AnalyzedVehicle.created_at)).scalar()

    # training_dataset 통계
    training_total = db.query(sql_func.count(TrainingDataset.id)).scalar()
    oldest_training = db.query(sql_func.min(TrainingDataset.created_at)).scalar()
    newest_training = db.query(sql_func.max(TrainingDataset.created_at)).scalar()

    # 정리 통계
    cleanup_info = await get_cleanup_stats(db)

    return {
        "analyzed_vehicles": {
            "total": analyzed_total,
            "verified": analyzed_verified,
            "unverified": analyzed_unverified,
            "oldest_created_at": oldest_analyzed.isoformat() if oldest_analyzed else None,
            "newest_created_at": newest_analyzed.isoformat() if newest_analyzed else None,
        },
        "training_dataset": {
            "total": training_total,
            "oldest_created_at": oldest_training.isoformat() if oldest_training else None,
            "newest_created_at": newest_training.isoformat() if newest_training else None,
        },
        "cleanup": cleanup_info,
        "storage_optimization": {
            "duplicated_records": analyzed_verified,  # training_dataset와 중복
            "description": "Verified analyzed_vehicles are duplicated in training_dataset"
        }
    }


# 정리 작업 수동 실행 (테스트/긴급용)
@router.post("/cleanup-now")
async def trigger_cleanup_now():
    """
    정리 작업 즉시 실행 (수동 트리거)

    Warning: 이 엔드포인트는 테스트 또는 긴급 상황에서만 사용하세요.
    """
    from studio.tasks.cleanup import cleanup_old_analyzed_vehicles

    try:
        await cleanup_old_analyzed_vehicles()
        return {"message": "Cleanup completed successfully"}
    except Exception as e:
        logger.error(f"Manual cleanup failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )




@router.post("/reload-efficientnet", tags=["Admin"])
async def reload_efficientnet_proxy():
    """Identifier 서비스의 EfficientNet 핫리로드 프록시 (Studio → Identifier)"""
    import httpx
    from studio.config import get_settings
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
            resp = await client.post(f"{settings.identifier_url}/admin/reload-efficientnet")
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Identifier 연결 실패: {e}")
