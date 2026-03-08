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
from studio.models.manufacturer import Manufacturer
from studio.models.vehicle_model import VehicleModel
from studio.models.analyzed_vehicle import AnalyzedVehicle

router = APIRouter()
logger = logging.getLogger(__name__)


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
    db: Session = Depends(get_db)
):
    """제조사 목록 조회"""
    query = db.query(Manufacturer)

    if is_domestic is not None:
        query = query.filter(Manufacturer.is_domestic == is_domestic)

    manufacturers = query.offset(skip).limit(limit).all()
    return manufacturers


@router.get("/manufacturers/{manufacturer_id}", response_model=ManufacturerResponse)
async def get_manufacturer(manufacturer_id: int, db: Session = Depends(get_db)):
    """제조사 상세 조회"""
    manufacturer = db.query(Manufacturer).filter(Manufacturer.id == manufacturer_id).first()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")
    return manufacturer


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
    db: Session = Depends(get_db)
):
    """차량 모델 목록 조회"""
    query = db.query(VehicleModel)

    if manufacturer_id is not None:
        query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)

    models = query.offset(skip).limit(limit).all()
    return models


@router.get("/vehicle-models/{model_id}", response_model=VehicleModelResponse)
async def get_vehicle_model(model_id: int, db: Session = Depends(get_db)):
    """차량 모델 상세 조회"""
    model = db.query(VehicleModel).filter(VehicleModel.id == model_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="Vehicle model not found")
    return model


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
@router.get("/analyzed-vehicles-pending")
def get_pending_vehicles(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """미검수 분석 레코드 목록 조회 (페이지 복원용)"""
    records = db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).order_by(AnalyzedVehicle.created_at.desc()).offset(skip).limit(limit).all()
    return {"items": [r.to_dict() for r in records]}


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


@router.patch("/review/{analyzed_id}")
async def update_analyzed_vehicle(
    analyzed_id: int,
    update_data: AnalyzedVehicleUpdate,
    db: Session = Depends(get_db)
):
    """분석 결과 수정 (제조사/모델 변경)"""
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    # 제조사 확인
    manufacturer = db.query(Manufacturer).filter(
        Manufacturer.id == update_data.matched_manufacturer_id
    ).first()
    if not manufacturer:
        raise HTTPException(status_code=404, detail="Manufacturer not found")

    # 모델 확인
    model = db.query(VehicleModel).filter(
        VehicleModel.id == update_data.matched_model_id
    ).first()
    if not model:
        raise HTTPException(status_code=404, detail="Vehicle model not found")

    analyzed.matched_manufacturer_id = update_data.matched_manufacturer_id
    analyzed.matched_model_id = update_data.matched_model_id
    analyzed.manufacturer = update_data.manufacturer or manufacturer.korean_name
    analyzed.model = update_data.model or model.korean_name

    db.commit()
    db.refresh(analyzed)

    return {"message": "Updated successfully", "data": analyzed.to_dict()}


@router.put("/review/{analyzed_id}")
async def review_analyzed_vehicle(
    analyzed_id: int,
    is_approved: bool,
    notes: Optional[str] = None,
    verified_by: str = "admin",
    db: Session = Depends(get_db)
):
    """분석 결과 검수 (승인/거부)"""
    analyzed = db.query(AnalyzedVehicle).options(
        joinedload(AnalyzedVehicle.matched_manufacturer),
        joinedload(AnalyzedVehicle.matched_model)
    ).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    analyzed.is_verified = is_approved
    analyzed.verified_by = verified_by
    analyzed.notes = notes

    if is_approved:
        from datetime import datetime
        from studio.models.training_dataset import TrainingDataset
        from studio.services.embedding import embedding_service
        from studio.services.vectordb import vectordb_service

        analyzed.verified_at = datetime.now()

        # 승인된 데이터를 학습 데이터셋에 추가
        if analyzed.matched_manufacturer_id and analyzed.matched_model_id:
            try:
                # 기존 학습 데이터 확인 (중복 방지)
                existing = db.query(TrainingDataset).filter(
                    TrainingDataset.image_path == analyzed.image_path
                ).first()

                if not existing:
                    # 이미지 임베딩 생성
                    image_embedding = embedding_service.encode_image(analyzed.image_path)

                    # 학습 데이터셋에 추가
                    training_data = TrainingDataset(
                        image_path=analyzed.image_path,
                        manufacturer_id=analyzed.matched_manufacturer_id,
                        model_id=analyzed.matched_model_id,
                        qdrant_id=None
                    )

                    db.add(training_data)
                    db.flush()  # ID 생성

                    # 제조사/모델 이름 (이미 joinedload로 로드됨, 추가 쿼리 없음)
                    mfr = analyzed.matched_manufacturer
                    mdl = analyzed.matched_model

                    # Qdrant 메타데이터 (extra_metadata 대신 직접 생성)
                    qdrant_metadata = {
                        "confidence_score": float(analyzed.confidence_score) if analyzed.confidence_score else 0.0,
                        "verified_by": verified_by,
                        "verified_at": datetime.now().isoformat()
                    }

                    # QdrantDB에 추가
                    success = vectordb_service.add_training_image(
                        training_id=training_data.id,
                        image_path=training_data.image_path,
                        manufacturer_id=training_data.manufacturer_id,
                        model_id=training_data.model_id,
                        embedding=image_embedding,
                        metadata=qdrant_metadata,
                        manufacturer_korean=mfr.korean_name if mfr else None,
                        manufacturer_english=mfr.english_name if mfr else None,
                        model_korean=mdl.korean_name if mdl else None,
                        model_english=mdl.english_name if mdl else None,
                    )

                    if success:
                        training_data.qdrant_id = f"train_{training_data.id}"
                        logger.info(f"Added to training dataset: {training_data.id}")

            except Exception as e:
                logger.error(f"Failed to add to training dataset: {e}")
                # 실패해도 검수는 완료되도록 함

    db.commit()
    db.refresh(analyzed)

    return {"message": "Review completed", "data": analyzed.to_dict()}


@router.post("/review/batch-save-all")
async def batch_save_all_to_vectordb(
    db: Session = Depends(get_db)
):
    """is_verified=false인 전체 항목을 벡터DB에 일괄 저장 (SSE 스트리밍, 커서 기반 페이지네이션)"""
    from sqlalchemy import func as sql_func
    from studio.models.training_dataset import TrainingDataset
    from studio.services.embedding import embedding_service
    from studio.services.vectordb import vectordb_service

    BATCH_SIZE = 100

    # 전체 미검수 개수
    total_unverified = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
        AnalyzedVehicle.is_verified == False
    ).scalar()

    # 저장 가능한 항목 개수 (제조사/모델 매칭 완료된 항목만)
    total = db.query(sql_func.count(AnalyzedVehicle.id)).filter(
        AnalyzedVehicle.is_verified == False,
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
            # 커서 기반 배치 조회 (desc 순) + JOIN 최적화
            query = db.query(AnalyzedVehicle).options(
                joinedload(AnalyzedVehicle.matched_manufacturer),
                joinedload(AnalyzedVehicle.matched_model)
            ).filter(
                AnalyzedVehicle.is_verified == False,
                AnalyzedVehicle.matched_manufacturer_id.isnot(None),
                AnalyzedVehicle.matched_model_id.isnot(None)
            ).order_by(AnalyzedVehicle.id.desc())

            if last_id is not None:
                query = query.filter(AnalyzedVehicle.id < last_id)

            batch = query.limit(BATCH_SIZE).all()

            if not batch:
                break

            for analyzed in batch:
                current += 1
                vectordb_ok = False
                try:
                    # 기존 학습 데이터 확인 (중복 방지)
                    existing = db.query(TrainingDataset).filter(
                        TrainingDataset.image_path == analyzed.image_path
                    ).first()

                    if existing:
                        vectordb_ok = True
                    else:
                        # 이미지 임베딩 생성
                        image_embedding = embedding_service.encode_image(analyzed.image_path)

                        # 학습 데이터셋에 추가
                        training_data = TrainingDataset(
                            image_path=analyzed.image_path,
                            manufacturer_id=analyzed.matched_manufacturer_id,
                            model_id=analyzed.matched_model_id,
                            qdrant_id=None
                        )

                        db.add(training_data)
                        db.flush()

                        # 제조사/모델 이름 (이미 joinedload로 로드됨, 추가 쿼리 없음)
                        mfr = analyzed.matched_manufacturer
                        mdl = analyzed.matched_model

                        # Qdrant 메타데이터
                        qdrant_metadata = {
                            "confidence_score": float(analyzed.confidence_score) if analyzed.confidence_score else 0.0,
                            "verified_by": "admin",
                            "verified_at": datetime.now().isoformat()
                        }

                        # QdrantDB에 추가
                        qdrant_success = vectordb_service.add_training_image(
                            training_id=training_data.id,
                            image_path=training_data.image_path,
                            manufacturer_id=training_data.manufacturer_id,
                            model_id=training_data.model_id,
                            embedding=image_embedding,
                            metadata=qdrant_metadata,
                            manufacturer_korean=mfr.korean_name if mfr else None,
                            manufacturer_english=mfr.english_name if mfr else None,
                            model_korean=mdl.korean_name if mdl else None,
                            model_english=mdl.english_name if mdl else None,
                        )

                        if qdrant_success:
                            training_data.qdrant_id = f"train_{training_data.id}"

                        db.commit()
                        vectordb_ok = True

                except Exception as e:
                    db.rollback()
                    logger.error(f"Batch VectorDB save: {analyzed.id} training_data failed - {e}")

                # is_verified는 training_data 성공/실패와 무관하게 항상 업데이트
                try:
                    # rollback 후 객체가 detached 될 수 있으므로 다시 조회
                    analyzed_fresh = db.query(AnalyzedVehicle).filter(
                        AnalyzedVehicle.id == analyzed.id
                    ).first()
                    if analyzed_fresh and not analyzed_fresh.is_verified:
                        analyzed_fresh.is_verified = True
                        analyzed_fresh.verified_by = "admin"
                        analyzed_fresh.verified_at = datetime.now()
                        db.commit()

                    succeeded += 1
                    logger.info(f"Batch VectorDB save: {analyzed.id} succeeded (vectordb={'OK' if vectordb_ok else 'SKIP'}) ({current}/{total})")

                except Exception as e:
                    db.rollback()
                    logger.error(f"Batch VectorDB save: {analyzed.id} is_verified update failed - {e}")
                    failed += 1
                    failed_ids.append(analyzed.id)

                # 진행 이벤트
                yield f"data: {json.dumps({'type': 'progress', 'current': current, 'total': total, 'succeeded': succeeded, 'failed': failed, 'item_id': analyzed.id})}\n\n"

                await asyncio.sleep(0.1)

            last_id = batch[-1].id

        # 완료 이벤트
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
async def save_to_vectordb(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """벡터DB에 저장 (간소화된 버전 - 메모 입력 없음)"""
    from datetime import datetime
    from sqlalchemy.orm import joinedload
    from studio.models.training_dataset import TrainingDataset
    from studio.services.embedding import embedding_service
    from studio.services.vectordb import vectordb_service

    analyzed = db.query(AnalyzedVehicle).options(
        joinedload(AnalyzedVehicle.matched_manufacturer),
        joinedload(AnalyzedVehicle.matched_model)
    ).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    # 제조사와 모델이 모두 있어야 저장 가능
    if not analyzed.matched_manufacturer_id or not analyzed.matched_model_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot save: manufacturer and model must be identified"
        )

    # 1) training_dataset + QdrantDB 저장 시도
    vectordb_ok = False
    try:
        # 기존 학습 데이터 확인 (중복 방지)
        existing = db.query(TrainingDataset).filter(
            TrainingDataset.image_path == analyzed.image_path
        ).first()

        if existing:
            vectordb_ok = True
        else:
            # 이미지 임베딩 생성
            image_embedding = embedding_service.encode_image(analyzed.image_path)

            # 학습 데이터셋에 추가
            training_data = TrainingDataset(
                image_path=analyzed.image_path,
                manufacturer_id=analyzed.matched_manufacturer_id,
                model_id=analyzed.matched_model_id,
                qdrant_id=None
            )

            db.add(training_data)
            db.flush()  # ID 생성

            # 제조사/모델 이름 (이미 joinedload로 로드됨, 추가 쿼리 없음)
            mfr = analyzed.matched_manufacturer
            mdl = analyzed.matched_model

            # Qdrant 메타데이터
            qdrant_metadata = {
                "confidence_score": float(analyzed.confidence_score) if analyzed.confidence_score else 0.0,
                "verified_by": "admin",
                "verified_at": datetime.now().isoformat()
            }

            # QdrantDB에 추가
            qdrant_success = vectordb_service.add_training_image(
                training_id=training_data.id,
                image_path=training_data.image_path,
                manufacturer_id=training_data.manufacturer_id,
                model_id=training_data.model_id,
                embedding=image_embedding,
                metadata=qdrant_metadata,
                manufacturer_korean=mfr.korean_name if mfr else None,
                manufacturer_english=mfr.english_name if mfr else None,
                model_korean=mdl.korean_name if mdl else None,
                model_english=mdl.english_name if mdl else None,
            )

            if qdrant_success:
                training_data.qdrant_id = f"train_{training_data.id}"
                logger.info(f"Added to VectorDB: {training_data.id}")

            db.commit()
            vectordb_ok = True

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save to VectorDB: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"VectorDB 저장 실패: {str(e)}"
        )

    # 2) VectorDB 성공 시에만 is_verified 업데이트
    try:
        analyzed_fresh = db.query(AnalyzedVehicle).filter(
            AnalyzedVehicle.id == analyzed_id
        ).first()
        analyzed_fresh.is_verified = True
        analyzed_fresh.verified_by = "admin"
        analyzed_fresh.verified_at = datetime.now()
        db.commit()
        db.refresh(analyzed_fresh)

        return {"message": "Saved to VectorDB successfully", "data": analyzed_fresh.to_dict()}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update is_verified: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"is_verified 업데이트 실패: {str(e)}"
        )


@router.delete("/review-delete-all")
async def batch_delete_all_analyzed_vehicles(
    db: Session = Depends(get_db)
):
    """미검수 분석 결과 전체 삭제 (DB 레벨 일괄 삭제 + 이미지 파일 삭제)"""
    import os

    # 전체 미검수 레코드 조회 (파일 경로 추출용)
    all_unverified = db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).all()

    total = len(all_unverified)
    deleted_files = 0
    failed_files = 0

    for analyzed in all_unverified:
        # 크롭 이미지 삭제
        try:
            if analyzed.image_path and os.path.exists(analyzed.image_path):
                os.remove(analyzed.image_path)
                deleted_files += 1
        except Exception as e:
            logger.warning(f"Failed to delete crop file {analyzed.image_path}: {e}")
            failed_files += 1

        # 원본 업로드 이미지 삭제 (raw_result에 original_image 경로가 있는 경우)
        try:
            if analyzed.raw_result and isinstance(analyzed.raw_result, dict):
                original_path = analyzed.raw_result.get("original_image")
                if original_path and os.path.exists(original_path):
                    os.remove(original_path)
                    deleted_files += 1
        except Exception as e:
            logger.warning(f"Failed to delete original file: {e}")
            failed_files += 1

    # DB 전체 삭제 (단일 쿼리 - 개별 삭제 대신)
    db.query(AnalyzedVehicle).filter(
        AnalyzedVehicle.is_verified == False
    ).delete(synchronize_session=False)
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
    """분석 결과 삭제 (크롭 이미지 + 원본 업로드 파일 + MySQL 레코드)"""
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    # 크롭 이미지 파일 삭제
    try:
        import os
        if analyzed.image_path and os.path.exists(analyzed.image_path):
            os.remove(analyzed.image_path)
            logger.info(f"Deleted crop file: {analyzed.image_path}")
    except Exception as e:
        logger.warning(f"Failed to delete crop file: {e}")

    # 원본 업로드 이미지 파일 삭제
    try:
        import os
        if analyzed.raw_result and isinstance(analyzed.raw_result, dict):
            original_path = analyzed.raw_result.get("original_image")
            if original_path and os.path.exists(original_path):
                os.remove(original_path)
                logger.info(f"Deleted original file: {original_path}")
    except Exception as e:
        logger.warning(f"Failed to delete original file: {e}")

    # DB에서 삭제
    db.delete(analyzed)
    db.commit()

    return {"message": "Deleted successfully"}


@router.post("/analyze/{analyzed_id}")
async def analyze_single_image(
    analyzed_id: int,
    db: Session = Depends(get_db)
):
    """
    단일 이미지 재분석 (일괄 분석용)

    Args:
        analyzed_id: 분석할 AnalyzedVehicle ID
    """
    from studio.services.openai_vision import vision_service
    from studio.services.matcher import VehicleMatcher

    # 기존 분석 결과 조회
    analyzed = db.query(AnalyzedVehicle).filter(AnalyzedVehicle.id == analyzed_id).first()
    if not analyzed:
        raise HTTPException(status_code=404, detail="Analyzed vehicle not found")

    try:
        # OpenAI Vision API 분석
        vision_result = await vision_service.analyze_vehicle_image(analyzed.image_path, db=db)

        # 기준 DB와 매칭
        matcher = VehicleMatcher(db, auto_insert=True)
        match_result = matcher.match_vehicle(
            vision_result.get("manufacturer_code", ""),
            vision_result.get("model_code", ""),
            vision_confidence=vision_result.get("confidence")
        )

        # 분석 결과 업데이트
        analyzed.raw_result = vision_result
        analyzed.manufacturer = match_result["manufacturer"].korean_name if match_result["manufacturer"] else None
        analyzed.model = match_result["model"].korean_name if match_result["model"] else None
        analyzed.matched_manufacturer_id = match_result["manufacturer"].id if match_result["manufacturer"] else None
        analyzed.matched_model_id = match_result["model"].id if match_result["model"] else None
        analyzed.confidence_score = match_result["overall_confidence"]

        db.commit()
        db.refresh(analyzed)

        return {
            "message": "Analysis completed",
            "data": analyzed.to_dict()
        }

    except Exception as e:
        logger.error(f"Failed to analyze image {analyzed_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


# 일괄 분석 API
@router.post("/analyze-batch")
async def analyze_batch_images(
    image_dir: str,
    db: Session = Depends(get_db)
):
    """
    디렉토리 내 이미지 일괄 분석

    Args:
        image_dir: 분석할 이미지가 있는 디렉토리 경로
    """
    from pathlib import Path
    from studio.services.openai_vision import vision_service
    from studio.services.matcher import VehicleMatcher
    import os

    # 디렉토리 확인
    dir_path = Path(image_dir)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail="Invalid directory path")

    # 이미지 파일 수집
    image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}
    image_files = [
        str(f) for f in dir_path.iterdir()
        if f.suffix.lower() in image_extensions
    ]

    if not image_files:
        raise HTTPException(status_code=400, detail="No image files found in directory")

    # 일괄 분석
    results = []
    matcher = VehicleMatcher(db, auto_insert=True)  # 매칭 실패 시 자동 DB 추가

    for image_path in image_files:
        try:
            # OpenAI Vision API 분석 (DB 세션 전달)
            vision_result = await vision_service.analyze_vehicle_image(image_path, db=db)

            # 기준 DB와 매칭
            match_result = matcher.match_vehicle(
                vision_result.get("manufacturer_code", ""),
                vision_result.get("model_code", ""),
                vision_confidence=vision_result.get("confidence")  # Vision API 신뢰도 전달
            )

            # DB에 저장 (한글명 사용)
            analyzed = AnalyzedVehicle(
                image_path=image_path,
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

            results.append({
                "image_path": image_path,
                "analyzed_id": analyzed.id,
                "manufacturer": vision_result.get("manufacturer"),
                "model": vision_result.get("model"),
                "matched": match_result["manufacturer"] is not None or match_result["model"] is not None,
                "confidence": match_result["overall_confidence"]
            })

        except Exception as e:
            results.append({
                "image_path": image_path,
                "error": str(e),
                "success": False
            })

    return {
        "total": len(image_files),
        "processed": len(results),
        "results": results
    }


# 벡터 DB 동기화 API
@router.post("/sync-vectordb")
async def sync_vector_database(
    db: Session = Depends(get_db)
):
    """
    벡터 데이터베이스 동기화 (학습 이미지 → training_images 컬렉션)
    - Incremental sync: qdrant_id가 없는 레코드만 동기화
    - JOIN 최적화: N+1 쿼리 제거
    """
    from sqlalchemy import func as sql_func
    from sqlalchemy.orm import joinedload
    from studio.services.vectordb import vectordb_service
    from studio.services.embedding import embedding_service
    from studio.models.training_dataset import TrainingDataset

    BATCH_SIZE = 100

    results = {
        "training": {"total": 0, "synced": 0, "errors": 0, "skipped": 0}
    }

    # Incremental sync: qdrant_id가 없는 것만 카운트
    total = db.query(sql_func.count(TrainingDataset.id)).filter(
        TrainingDataset.qdrant_id.is_(None)
    ).scalar()
    results["training"]["total"] = total

    if total == 0:
        logger.info("All training data already synced to Qdrant")
        results["stats"] = vectordb_service.get_collection_stats()
        return results

    # 커서 기반 페이지네이션 + JOIN 최적화
    last_id = 0
    while True:
        batch = db.query(TrainingDataset).options(
            joinedload(TrainingDataset.manufacturer),
            joinedload(TrainingDataset.model)
        ).filter(
            TrainingDataset.id > last_id,
            TrainingDataset.qdrant_id.is_(None)  # Incremental sync
        ).order_by(TrainingDataset.id.asc()).limit(BATCH_SIZE).all()

        if not batch:
            break

        for data in batch:
            try:
                # 이미지 임베딩 생성
                embedding = embedding_service.encode_image(data.image_path)

                # 제조사/모델 이름 (이미 joinedload로 로드됨, 추가 쿼리 없음)
                mfr = data.manufacturer
                mdl = data.model

                # Qdrant에 추가
                success = vectordb_service.add_training_image(
                    training_id=data.id,
                    image_path=data.image_path,
                    manufacturer_id=data.manufacturer_id,
                    model_id=data.model_id,
                    embedding=embedding,
                    metadata=None,
                    manufacturer_korean=mfr.korean_name if mfr else None,
                    manufacturer_english=mfr.english_name if mfr else None,
                    model_korean=mdl.korean_name if mdl else None,
                    model_english=mdl.english_name if mdl else None,
                )

                if success:
                    results["training"]["synced"] += 1
                    data.qdrant_id = f"train_{data.id}"
                else:
                    results["training"]["errors"] += 1

            except Exception as e:
                logger.error(f"Failed to sync training data {data.id}: {e}")
                results["training"]["errors"] += 1

        last_id = batch[-1].id
        db.commit()  # 배치 단위 커밋

    results["stats"] = vectordb_service.get_collection_stats()

    return results


# 벡터 DB 통계 조회
@router.get("/vectordb-stats")
async def get_vectordb_stats():
    """벡터 데이터베이스 통계 정보"""
    from studio.services.vectordb import vectordb_service
    from studio.services.embedding import embedding_service

    return {
        "collections": vectordb_service.get_collection_stats(),
        "embedding": embedding_service.get_model_info()
    }


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


