"""
파인튜닝 API 라우터
- 학습 데이터 Export (DB → ShareGPT JSON)
- Trainer 서비스 프록시 (학습 시작/상태/중지/로그, 하드웨어 프리셋, 배포 커맨드)
- Before/After 평가 (Identifier 서비스 연동)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func, select, tuple_
from typing import Optional
from pydantic import BaseModel
import asyncio
import httpx
import logging
import json
import math
import random
import shutil
import csv as csv_module
from pathlib import Path
from datetime import datetime

from studio.models import get_db
from studio.models.training_dataset import TrainingDataset
from studio.models.manufacturer import Manufacturer
from studio.models.vehicle_model import VehicleModel

router = APIRouter()
logger = logging.getLogger(__name__)


async def _proxy_get(path: str, params: dict = None) -> dict:
    """Trainer 서비스 GET 프록시"""
    from studio.config import settings
    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        resp = await client.get(f"{settings.trainer_url}{path}", params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


async def _proxy_post(path: str, body: dict = None) -> dict:
    """Trainer 서비스 POST 프록시"""
    from studio.config import settings
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        resp = await client.post(f"{settings.trainer_url}{path}", json=body or {})
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)
        return resp.json()


class ExportParams(BaseModel):
    # 필터
    manufacturer_id: Optional[int] = None
    date_from: Optional[str] = None   # YYYY-MM-DD
    date_to: Optional[str] = None     # YYYY-MM-DD
    # 페이징
    page: int = 1
    page_size: int = 500
    split: float = 0.9               # train/val 비율


def _apply_filters(query, manufacturer_id=None, date_from=None, date_to=None):
    """공통 필터 적용 헬퍼"""
    if manufacturer_id:
        query = query.filter(TrainingDataset.manufacturer_id == manufacturer_id)
    if date_from:
        try:
            date_from_parsed = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(TrainingDataset.created_at >= date_from_parsed)
        except ValueError:
            pass
    if date_to:
        try:
            date_to_parsed = datetime.strptime(date_to, "%Y-%m-%d")
            query = query.filter(TrainingDataset.created_at < date_to_parsed.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass
    return query


@router.get("/mode")
async def get_finetune_mode():
    """식별 서비스의 현재 판별 모드 조회 (IDENTIFIER_MODE)"""
    from studio.config import settings
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=False) as client:
            resp = await client.get(f"{settings.identifier_url}/health")
            data = resp.json()
            return {"identifier_mode": data.get("identifier_mode", "efficientnet")}
    except Exception:
        return {"identifier_mode": "efficientnet"}


@router.get("/hw-profile")
async def get_hw_profile():
    """하드웨어 감지 → 파인튜닝 최적 파라미터 프리셋 반환 (Trainer 서비스 프록시)"""
    return await _proxy_get("/hw-profile")


@router.get("/freeze-epochs")
async def get_freeze_epochs(db: Session = Depends(get_db)):
    """현재 DB 클래스 수와 저장된 모델 클래스 수를 비교해 freeze_epochs 권장값 반환"""
    db_classes = (
        db.query(TrainingDataset.manufacturer_id, TrainingDataset.model_id)
        .filter(
            TrainingDataset.manufacturer_id.isnot(None),
            TrainingDataset.model_id.isnot(None),
        )
        .distinct()
        .count()
    )

    model_classes = None
    try:
        info = await _proxy_get("/model-info")
        model_classes = info.get("num_classes")
    except Exception:
        pass

    if model_classes is None:
        reason = "저장된 모델 없음 — 첫 학습"
        freeze_epochs = 3
    elif db_classes != model_classes:
        reason = f"클래스 수 변경 ({model_classes} → {db_classes}) — head 재초기화"
        freeze_epochs = 3
    else:
        reason = f"클래스 수 동일 ({db_classes})"
        freeze_epochs = 1

    return {"freeze_epochs": freeze_epochs, "reason": reason, "db_classes": db_classes, "model_classes": model_classes}


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """학습 데이터 통계 (총 레코드 수, 제조사별 분포)"""
    total = db.query(sql_func.count(TrainingDataset.id)).scalar() or 0

    num_classes = (
        db.query(TrainingDataset.manufacturer_id, TrainingDataset.model_id)
        .filter(
            TrainingDataset.manufacturer_id.isnot(None),
            TrainingDataset.model_id.isnot(None),
        )
        .distinct()
        .count()
    )

    by_manufacturer = (
        db.query(
            Manufacturer.id,
            Manufacturer.korean_name,
            Manufacturer.english_name,
            sql_func.count(TrainingDataset.id).label("count"),
        )
        .join(TrainingDataset, Manufacturer.id == TrainingDataset.manufacturer_id)
        .group_by(Manufacturer.id, Manufacturer.korean_name, Manufacturer.english_name)
        .order_by(sql_func.count(TrainingDataset.id).desc())
        .all()
    )

    by_model = (
        db.query(
            VehicleModel.id,
            VehicleModel.korean_name,
            VehicleModel.english_name,
            Manufacturer.korean_name.label("manufacturer_korean"),
            sql_func.count(TrainingDataset.id).label("count"),
        )
        .join(TrainingDataset, VehicleModel.id == TrainingDataset.model_id)
        .join(Manufacturer, VehicleModel.manufacturer_id == Manufacturer.id)
        .group_by(VehicleModel.id, VehicleModel.korean_name, VehicleModel.english_name, Manufacturer.korean_name)
        .order_by(sql_func.count(TrainingDataset.id).desc())
        .all()
    )

    return {
        "total": total,
        "num_classes": num_classes,
        "manufacturers_count": len(by_manufacturer),
        "by_manufacturer": [
            {
                "manufacturer_id": row.id,
                "korean_name": row.korean_name,
                "english_name": row.english_name,
                "count": row.count,
            }
            for row in by_manufacturer
        ],
        "by_model": [
            {
                "model_id": row.id,
                "korean_name": row.korean_name,
                "english_name": row.english_name,
                "manufacturer_korean": row.manufacturer_korean,
                "count": row.count,
            }
            for row in by_model
        ],
    }


@router.get("/export/preview")
async def export_preview(
    manufacturer_id: Optional[int] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page_size: int = 500,
    db: Session = Depends(get_db),
):
    """Export 미리보기 — 현재 필터 기준 총 건수 + 총 페이지 수"""
    query = db.query(TrainingDataset)
    query = _apply_filters(query, manufacturer_id, date_from, date_to)
    total = query.count()
    total_pages = math.ceil(total / page_size) if page_size > 0 else 0

    return {
        "total": total,
        "page_size": page_size,
        "total_pages": total_pages,
    }


@router.post("/export")
async def export_data(params: ExportParams, db: Session = Depends(get_db)):
    """Export 실행 → LLaMA-Factory data 디렉토리에 직접 저장

    생성 파일:
    - data/finetune/vehicle_train.json (sharegpt 형식)
    - data/finetune/vehicle_val.json (sharegpt 형식)
    - data/finetune/dataset_info.json (LLaMA-Factory 메타데이터)
    """
    if params.page < 1:
        raise HTTPException(status_code=400, detail="page는 1 이상이어야 합니다.")
    if not (0.0 < params.split <= 1.0):
        raise HTTPException(status_code=400, detail="split은 0 초과 1 이하 값이어야 합니다.")

    query = (
        db.query(TrainingDataset)
        .options(
            joinedload(TrainingDataset.manufacturer),
            joinedload(TrainingDataset.model),
        )
    )
    query = _apply_filters(query, params.manufacturer_id, params.date_from, params.date_to)

    total = query.count()
    if total == 0:
        raise HTTPException(status_code=404, detail="해당 조건의 데이터가 없습니다.")

    total_pages = math.ceil(total / params.page_size)
    offset = (params.page - 1) * params.page_size
    records = (
        query.order_by(TrainingDataset.id).offset(offset).limit(params.page_size).all()
    )

    if not records:
        raise HTTPException(status_code=404, detail=f"페이지 {params.page}에 데이터가 없습니다. (총 {total_pages}페이지)")

    # 셔플 후 train/val 분리 (split=1.0이면 전체 학습셋)
    random.shuffle(records)
    if params.split >= 1.0:
        train_records = records
        val_records = []
    else:
        split_idx = int(len(records) * params.split)
        train_records = records[:split_idx]
        val_records = records[split_idx:]

    HUMAN_PROMPT = (
        "이 차량 이미지에서 제조사와 모델을 식별하세요.\n\n"
        "차량의 외관 특징(그릴, 헤드라이트, 로고, 차체 형태 등)을 분석한 뒤 아래 JSON 형식으로 응답하세요:\n"
        '{"manufacturer_korean": "<제조사 한글>", "manufacturer_english": "<제조사 영문>", '
        '"model_korean": "<모델 한글>", "model_english": "<모델 영문>", '
        '"confidence": <0.0~1.0>}\n\n'
        "식별할 수 없으면 모든 이름 필드를 null로, confidence를 0.0으로 설정하세요."
    )

    def to_entry(record: TrainingDataset) -> dict:
        mfr_ko = record.manufacturer.korean_name if record.manufacturer else "Unknown"
        mfr_en = record.manufacturer.english_name if record.manufacturer else "Unknown"
        mdl_ko = record.model.korean_name if record.model else "Unknown"
        mdl_en = record.model.english_name if record.model else "Unknown"
        think_chain = (
            f"이미지를 분석합니다. "
            f"차량의 외관 특징을 살펴보면 {mfr_ko} {mdl_ko}의 디자인 요소가 확인됩니다. "
            f"그릴 형태, 헤드라이트 디자인, 차체 비율 등이 {mfr_ko} {mdl_ko}({mfr_en} {mdl_en})의 특징과 일치합니다."
        )
        answer = json.dumps(
            {
                "manufacturer_korean": mfr_ko,
                "manufacturer_english": mfr_en,
                "model_korean": mdl_ko,
                "model_english": mdl_en,
                "confidence": 1.0,
            },
            ensure_ascii=False,
        )
        gpt_response = f"<think>\n{think_chain}\n</think>\n{answer}"
        return {
            "id": f"reeve_{record.id}",
            "conversations": [
                {
                    "from": "human",
                    "value": f"<image>\n{HUMAN_PROMPT}",
                },
                {
                    "from": "gpt",
                    "value": gpt_response,
                },
            ],
            "images": [str(Path(record.image_path).resolve())],
        }

    train_data = [to_entry(r) for r in train_records]
    val_data = [to_entry(r) for r in val_records]

    # data/finetune 디렉토리에 저장
    export_dir = Path("./data/finetune")
    export_dir.mkdir(parents=True, exist_ok=True)

    # train/val JSON 저장 (LLaMA-Factory sharegpt 형식: 배열)
    train_path = export_dir / "vehicle_train.json"
    train_path.write_text(json.dumps(train_data, ensure_ascii=False, indent=2), encoding="utf-8")

    _sharegpt_entry = {
        "formatting": "sharegpt",
        "columns": {"messages": "conversations", "images": "images"},
        "tags": {"role_tag": "from", "content_tag": "value", "user_tag": "human", "assistant_tag": "gpt"},
    }

    # dataset_info.json 생성 (LLaMA-Factory가 데이터셋을 인식하는 메타데이터)
    dataset_info = {
        "vehicle_train": {"file_name": "vehicle_train.json", **_sharegpt_entry},
    }

    val_path = None
    if val_data:
        val_path = export_dir / "vehicle_val.json"
        val_path.write_text(json.dumps(val_data, ensure_ascii=False, indent=2), encoding="utf-8")
        dataset_info["vehicle_val"] = {"file_name": "vehicle_val.json", **_sharegpt_entry}
    dataset_info_path = export_dir / "dataset_info.json"
    dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        f"Export 완료: train={len(train_data)}건, val={len(val_data)}건 → {export_dir}"
    )

    return JSONResponse({
        "message": "Export 완료 — LLaMA-Factory에서 바로 사용 가능합니다.",
        "export_dir": str(export_dir),
        "files": {
            "train": str(train_path),
            "val": str(val_path) if val_path else None,
            "dataset_info": str(dataset_info_path),
        },
        "counts": {
            "total_records": total,
            "total_pages": total_pages,
            "current_page": params.page,
            "train_count": len(train_data),
            "val_count": len(val_data),
            "split_ratio": params.split,
        },
    })


class EfficientNetExportParams(BaseModel):
    manufacturer_id: Optional[int] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    split: float = 0.9
    max_per_class: Optional[int] = None  # 클래스당 최대 샘플 수 (None = 제한 없음)
    min_per_class: Optional[int] = None  # 클래스당 최소 샘플 수 (미만 클래스 제외)


def _export_efficientnet_sync(params: "EfficientNetExportParams", db: Session) -> dict:
    """EfficientNetV2-M export 동기 작업 (스레드풀에서 실행)"""
    CHUNK_SIZE = 50_000

    if not (0.0 < params.split <= 1.0):
        raise HTTPException(status_code=400, detail="split은 0 초과 1 이하 값이어야 합니다.")

    # ── 1. class mapping: min_per_class 필터 포함 GROUP BY 쿼리 ──────────
    pairs_stmt = (
        select(
            TrainingDataset.manufacturer_id,
            TrainingDataset.model_id,
            Manufacturer.korean_name.label("mfr_korean"),
            Manufacturer.english_name.label("mfr_english"),
            VehicleModel.korean_name.label("model_korean"),
            VehicleModel.english_name.label("model_english"),
            sql_func.count(TrainingDataset.id).label("sample_count"),
        )
        .join(Manufacturer, TrainingDataset.manufacturer_id == Manufacturer.id)
        .join(VehicleModel, TrainingDataset.model_id == VehicleModel.id)
        .where(
            TrainingDataset.manufacturer_id.isnot(None),
            TrainingDataset.model_id.isnot(None),
        )
        .group_by(
            TrainingDataset.manufacturer_id,
            TrainingDataset.model_id,
            Manufacturer.korean_name,
            Manufacturer.english_name,
            VehicleModel.korean_name,
            VehicleModel.english_name,
        )
    )
    if params.manufacturer_id:
        pairs_stmt = pairs_stmt.where(TrainingDataset.manufacturer_id == params.manufacturer_id)
    if params.date_from:
        try:
            pairs_stmt = pairs_stmt.where(
                TrainingDataset.created_at >= datetime.strptime(params.date_from, "%Y-%m-%d")
            )
        except ValueError:
            pass
    if params.date_to:
        try:
            dt = datetime.strptime(params.date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            pairs_stmt = pairs_stmt.where(TrainingDataset.created_at < dt)
        except ValueError:
            pass
    if params.min_per_class and params.min_per_class > 0:
        pairs_stmt = pairs_stmt.having(sql_func.count(TrainingDataset.id) >= params.min_per_class)

    pairs_rows = db.execute(pairs_stmt).all()
    if not pairs_rows:
        raise HTTPException(status_code=404, detail="해당 조건의 학습 데이터가 없습니다.")

    pairs = sorted({(r.manufacturer_id, r.model_id) for r in pairs_rows})
    pair_to_idx = {pair: idx for idx, pair in enumerate(pairs)}
    name_map = {(r.manufacturer_id, r.model_id): r for r in pairs_rows}

    classes = {}
    for idx, (mid, vid) in enumerate(pairs):
        r = name_map.get((mid, vid))
        classes[str(idx)] = {
            "manufacturer_id": mid,
            "model_id": vid,
            "manufacturer_korean": r.mfr_korean if r else None,
            "manufacturer_english": r.mfr_english if r else None,
            "model_korean": r.model_korean if r else None,
            "model_english": r.model_english if r else None,
        }
    class_mapping = {"num_classes": len(pairs), "classes": classes}

    # ── 2. 데이터 쿼리: SQL Window Function + 스트리밍 ────────────────────
    base_cols = [
        TrainingDataset.image_path,
        TrainingDataset.manufacturer_id,
        TrainingDataset.model_id,
    ]

    # min_per_class 필터로 선택된 유효 클래스 (manufacturer_id, model_id) 목록
    valid_pairs = pairs  # pairs는 이미 min_per_class HAVING 필터가 적용된 결과

    def _apply_common_filters(q):
        q = q.where(
            TrainingDataset.manufacturer_id.isnot(None),
            TrainingDataset.model_id.isnot(None),
        )
        if valid_pairs:
            # 유효 클래스만 포함: (manufacturer_id, model_id) IN (...)
            q = q.where(
                tuple_(TrainingDataset.manufacturer_id, TrainingDataset.model_id).in_(valid_pairs)
            )
        if params.manufacturer_id:
            q = q.where(TrainingDataset.manufacturer_id == params.manufacturer_id)
        if params.date_from:
            try:
                q = q.where(
                    TrainingDataset.created_at >= datetime.strptime(params.date_from, "%Y-%m-%d")
                )
            except ValueError:
                pass
        if params.date_to:
            try:
                dt = datetime.strptime(params.date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                q = q.where(TrainingDataset.created_at < dt)
            except ValueError:
                pass
        return q

    if params.max_per_class and params.max_per_class > 0:
        # ROW_NUMBER() OVER (PARTITION BY class ORDER BY id) — DB 레벨 클램핑
        rn = sql_func.row_number().over(
            partition_by=[TrainingDataset.manufacturer_id, TrainingDataset.model_id],
            order_by=TrainingDataset.id,
        ).label("rn")
        inner = _apply_common_filters(select(*base_cols, rn))
        subq = inner.subquery()
        stmt = select(
            subq.c.image_path,
            subq.c.manufacturer_id,
            subq.c.model_id,
        ).where(subq.c.rn <= params.max_per_class)
    else:
        stmt = _apply_common_filters(select(*base_cols)).order_by(TrainingDataset.id)

    # ── 3. 디렉토리 초기화 ────────────────────────────────────────────────
    export_dir = Path("./data/finetune")
    train_dir = export_dir / "train"
    val_dir = export_dir / "val"
    shutil.rmtree(train_dir, ignore_errors=True)
    shutil.rmtree(val_dir, ignore_errors=True)
    train_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    class_mapping_path = export_dir / "class_mapping.json"
    class_mapping_path.write_text(json.dumps(class_mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 4. 스트리밍 + 청크 CSV 쓰기 ──────────────────────────────────────
    train_count = 0
    val_count = 0
    train_chunk_idx = 0
    val_chunk_idx = 0
    train_f = train_writer = None
    val_f = val_writer = None

    def open_chunk(directory: Path, chunk_idx: int):
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"chunk_{chunk_idx:04d}.csv"
        f = open(path, "w", newline="", encoding="utf-8")
        w = csv_module.writer(f)
        w.writerow(["image_path", "class_idx"])
        return f, w

    result = db.execute(stmt.execution_options(stream_results=True))
    for row in result.yield_per(1000):
        class_idx = pair_to_idx.get((row.manufacturer_id, row.model_id))
        if class_idx is None:
            continue

        if params.split >= 1.0 or random.random() < params.split:
            if train_writer is None or train_count % CHUNK_SIZE == 0 and train_count > 0:
                if train_f:
                    train_f.close()
                train_f, train_writer = open_chunk(train_dir, train_chunk_idx)
                train_chunk_idx += 1
            train_writer.writerow([row.image_path, class_idx])
            train_count += 1
        else:
            if val_writer is None or val_count % CHUNK_SIZE == 0 and val_count > 0:
                if val_f:
                    val_f.close()
                val_f, val_writer = open_chunk(val_dir, val_chunk_idx)
                val_chunk_idx += 1
            val_writer.writerow([row.image_path, class_idx])
            val_count += 1

    if train_f:
        train_f.close()
    if val_f:
        val_f.close()

    if train_count == 0:
        raise HTTPException(status_code=404, detail="유효한 학습 이미지가 없습니다.")

    logger.info(
        f"EfficientNet export 완료: train={train_count}건({train_chunk_idx}청크), "
        f"val={val_count}건({val_chunk_idx}청크), classes={len(pairs)} → {export_dir}"
    )

    return {
        "message": "EfficientNet 학습 데이터 내보내기 완료",
        "export_dir": str(export_dir),
        "num_classes": len(pairs),
        "class_mapping_path": str(class_mapping_path),
        "files": {
            "train_dir": str(train_dir),
            "val_dir": str(val_dir) if val_count > 0 else None,
            "class_mapping": str(class_mapping_path),
        },
        "counts": {
            "total_records": train_count + val_count,
            "train_count": train_count,
            "val_count": val_count,
            "train_chunks": train_chunk_idx,
            "val_chunks": val_chunk_idx,
            "split_ratio": params.split,
        },
    }


@router.post("/export-efficientnet")
async def export_efficientnet_data(params: EfficientNetExportParams):
    """EfficientNetV2-M 분류기 학습용 데이터 내보내기

    생성 디렉토리:
    - data/finetune/train/chunk_0000.csv, chunk_0001.csv, ...
    - data/finetune/val/chunk_0000.csv, ...
    - data/finetune/class_mapping.json

    최적화:
    - class mapping: 경량 DISTINCT 쿼리 (joinedload 없음)
    - max_per_class: SQL Window Function으로 DB 레벨 처리
    - 데이터 스트리밍: stream_results + yield_per (메모리 일정)
    - CSV 청크: 50,000행 단위 파일 분할
    - blocking I/O는 스레드풀에서 실행 (event loop 점유 방지)
    """
    from studio.models.database import SessionLocal

    def run():
        with SessionLocal() as db:
            return _export_efficientnet_sync(params, db)

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, run)
    return JSONResponse(result)


@router.get("/deploy/cmd")
async def deploy_cmd(
    checkpoint_path: str = Query(..., description="학습된 체크포인트 경로"),
    model_name: str = Query("reeve-vlm-v1", description="Ollama 등록 모델명"),
):
    """체크포인트 경로 → Ollama 배포 커맨드 목록 반환 (Trainer 서비스 프록시)"""
    return await _proxy_get("/deploy/cmd", params={"checkpoint_path": checkpoint_path, "model_name": model_name})


# =============================================================================
# Trainer 서비스 프록시 엔드포인트 (학습 자동화)
# =============================================================================

class TrainingConfig(BaseModel):
    """학습 설정"""
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"
    learning_rate: float = 1e-4
    num_epochs: float = 3.0
    batch_size: int = 2
    gradient_accumulation: int = 4
    lora_rank: int = 8
    quantization_bit: Optional[int] = 4
    cutoff_len: int = 1024
    output_dir: str = "vehicle-vlm"
    flash_attn: Optional[str] = None
    use_mps: bool = False
    fp16: bool = False
    # EfficientNet 전용 필드
    freeze_epochs: int = 3
    max_per_class: Optional[int] = None
    min_per_class: Optional[int] = None
    use_ema: bool = False
    use_mixup: bool = False
    num_workers: Optional[int] = None
    early_stopping_patience: int = 7


class ExportModelRequest(BaseModel):
    """LoRA 병합 요청"""
    checkpoint_path: str
    output_dir: str = "output/merged"
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"


@router.post("/train/start")
async def start_training(config: TrainingConfig):
    """학습 시작 (Trainer 서비스 프록시)"""
    return await _proxy_post("/train/start", config.model_dump())


@router.get("/train/status")
async def get_training_status():
    """학습 진행 상태 조회 (Trainer 서비스 프록시)"""
    return await _proxy_get("/train/status")


@router.post("/train/stop")
async def stop_training():
    """학습 중지 (Trainer 서비스 프록시)"""
    return await _proxy_post("/train/stop")


@router.get("/train/logs")
async def get_training_logs(tail: int = Query(default=50, ge=1, le=500)):
    """학습 로그 조회 (Trainer 서비스 프록시)"""
    return await _proxy_get("/train/logs", params={"tail": tail})


@router.get("/train/raw-log")
async def get_raw_training_log(tail: int = Query(default=100, ge=1, le=1000)):
    """원시 학습 로그 반환 (Trainer 서비스 프록시)"""
    return await _proxy_get("/train/raw-log", params={"tail": tail})


@router.get("/train/deploy-config")
async def get_deploy_config():
    """핫리로드 경로 설정 반환 (Trainer 서비스 프록시)"""
    return await _proxy_get("/train/deploy-config")


@router.post("/train/export")
async def export_model(req: ExportModelRequest):
    """LoRA 어댑터 병합 (Trainer 서비스 프록시)"""
    return await _proxy_post("/train/export", req.model_dump())


@router.get("/evaluate")
async def evaluate_model(
    sample_size: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Before/After 평가 -- Identifier 서비스로 정확도 비교"""
    from studio.config import settings

    # training_dataset에서 랜덤 샘플링
    total = db.query(sql_func.count(TrainingDataset.id)).scalar() or 0
    if total == 0:
        raise HTTPException(status_code=404, detail="학습 데이터가 없습니다.")

    actual_size = min(sample_size, total)
    samples = (
        db.query(TrainingDataset)
        .options(
            joinedload(TrainingDataset.manufacturer),
            joinedload(TrainingDataset.model),
        )
        .order_by(sql_func.rand())
        .limit(actual_size)
        .all()
    )

    correct = 0
    total_confidence = 0.0
    incorrect_samples = []

    async with httpx.AsyncClient(timeout=30.0, verify=False) as client:
        for sample in samples:
            try:
                # Identifier에 이미지 전송
                image_path = sample.image_path
                if not Path(image_path).exists():
                    continue

                with open(image_path, "rb") as f:
                    files = {"file": (Path(image_path).name, f, "image/jpeg")}
                    resp = await client.post(
                        f"{settings.identifier_url}/identify",
                        files=files,
                    )

                if resp.status_code != 200:
                    continue

                result = resp.json()
                confidence = result.get("confidence", 0.0)
                total_confidence += confidence

                # IdentificationResult에는 manufacturer_id가 없으므로
                # top_k_details[0]에서 추출하거나, 이름으로 비교
                pred_mf_id = None
                pred_mdl_id = None
                top_k = result.get("top_k_details", [])
                if top_k:
                    pred_mf_id = top_k[0].get("manufacturer_id")
                    pred_mdl_id = top_k[0].get("model_id")

                if pred_mf_id == sample.manufacturer_id and pred_mdl_id == sample.model_id:
                    correct += 1
                else:
                    incorrect_samples.append({
                        "image_path": sample.image_path,
                        "expected": {
                            "manufacturer": sample.manufacturer.korean_name if sample.manufacturer else None,
                            "model": sample.model.korean_name if sample.model else None,
                        },
                        "predicted": {
                            "manufacturer_korean": result.get("manufacturer_korean"),
                            "model_korean": result.get("model_korean"),
                            "status": result.get("status"),
                        },
                        "confidence": confidence,
                    })

            except Exception as e:
                logger.warning(f"Evaluation failed for sample {sample.id}: {e}")

    evaluated = correct + len(incorrect_samples)
    accuracy = (correct / evaluated * 100) if evaluated > 0 else 0

    return {
        "accuracy": round(accuracy, 2),
        "avg_confidence": round(total_confidence / evaluated, 4) if evaluated > 0 else 0,
        "total": actual_size,
        "evaluated": evaluated,
        "correct": correct,
        "incorrect_count": len(incorrect_samples),
        "incorrect_samples": incorrect_samples[:20],  # 최대 20개만
    }
