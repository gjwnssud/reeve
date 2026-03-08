"""
파인튜닝 API 라우터
학습 데이터 Export + Ollama 배포 준비
(학습은 LLaMA-Factory WebUI에서 진행)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sql_func
from typing import Optional
from pydantic import BaseModel
import logging
import json
import math
import random
from pathlib import Path
from datetime import datetime

from studio.models import get_db
from studio.models.training_dataset import TrainingDataset
from studio.models.manufacturer import Manufacturer
from studio.models.vehicle_model import VehicleModel

router = APIRouter()
logger = logging.getLogger(__name__)


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


@router.get("/stats")
async def get_stats(db: Session = Depends(get_db)):
    """학습 데이터 통계 (총 레코드 수, 제조사별 분포)"""
    total = db.query(sql_func.count(TrainingDataset.id)).scalar() or 0

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

    return {
        "total": total,
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
    if not (0.0 < params.split < 1.0):
        raise HTTPException(status_code=400, detail="split은 0과 1 사이 값이어야 합니다.")

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

    # 셔플 후 train/val 분리
    random.shuffle(records)
    split_idx = int(len(records) * params.split)
    train_records = records[:split_idx]
    val_records = records[split_idx:]

    HUMAN_PROMPT = (
        "이 차량 이미지에서 제조사와 모델을 식별하세요.\n\n"
        "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요:\n"
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
        gpt_response = json.dumps(
            {
                "manufacturer_korean": mfr_ko,
                "manufacturer_english": mfr_en,
                "model_korean": mdl_ko,
                "model_english": mdl_en,
                "confidence": 1.0,
            },
            ensure_ascii=False,
        )
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
            "images": [record.image_path],
        }

    train_data = [to_entry(r) for r in train_records]
    val_data = [to_entry(r) for r in val_records]

    # data/finetune 디렉토리에 저장
    export_dir = Path("./data/finetune")
    export_dir.mkdir(parents=True, exist_ok=True)

    # train/val JSON 저장 (LLaMA-Factory sharegpt 형식: 배열)
    train_path = export_dir / "vehicle_train.json"
    val_path = export_dir / "vehicle_val.json"
    train_path.write_text(json.dumps(train_data, ensure_ascii=False, indent=2), encoding="utf-8")
    val_path.write_text(json.dumps(val_data, ensure_ascii=False, indent=2), encoding="utf-8")

    # dataset_info.json 생성 (LLaMA-Factory가 데이터셋을 인식하는 메타데이터)
    dataset_info = {
        "vehicle_train": {
            "file_name": "vehicle_train.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "conversations",
                "images": "images",
            },
            "tags": {
                "role_tag": "from",
                "content_tag": "value",
                "user_tag": "human",
                "assistant_tag": "gpt",
            },
        },
        "vehicle_val": {
            "file_name": "vehicle_val.json",
            "formatting": "sharegpt",
            "columns": {
                "messages": "conversations",
                "images": "images",
            },
            "tags": {
                "role_tag": "from",
                "content_tag": "value",
                "user_tag": "human",
                "assistant_tag": "gpt",
            },
        },
    }
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
            "val": str(val_path),
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


@router.get("/deploy/cmd")
async def deploy_cmd(
    checkpoint_path: str = Query(..., description="학습된 체크포인트 경로"),
    model_name: str = Query("vehicle-vlm-v1", description="Ollama 등록 모델명"),
):
    """체크포인트 경로 입력 → Ollama 배포 커맨드 목록 반환"""
    gguf_filename = "model.gguf"
    gguf_path = f"{checkpoint_path}/{gguf_filename}"

    modelfile_content = (
        f"FROM ./{gguf_filename}\n"
        f'SYSTEM "당신은 차량 식별 전문가입니다. '
        f'차량 이미지를 보고 제조사와 모델을 정확하게 식별합니다."\n'
    )

    merged_dir = f"{checkpoint_path}/merged"

    steps = [
        {
            "title": "1. LoRA 어댑터 병합 (LLaMA-Factory)",
            "cmd": (
                f"llamafactory-cli export "
                f"--model_name_or_path Qwen/Qwen3-VL-8B-Instruct "
                f"--adapter_name_or_path {checkpoint_path} "
                f"--export_dir {merged_dir} "
                f"--export_size 2 "
                f"--export_legacy_format false"
            ),
            "type": "cmd",
        },
        {
            "title": "2. GGUF 변환 (llama.cpp 필요)",
            "cmd": (
                f"python convert_hf_to_gguf.py {merged_dir} "
                f"--outtype f16 --outfile {gguf_path}"
            ),
            "type": "cmd",
        },
        {
            "title": "3. Modelfile 생성",
            "content": modelfile_content,
            "filename": "Modelfile",
            "type": "file",
        },
        {
            "title": "4. Ollama 모델 등록",
            "cmd": f"ollama create {model_name} -f Modelfile",
            "type": "cmd",
        },
        {
            "title": "5. Identifier .env 수정",
            "content": f"VLM_MODEL_NAME={model_name}",
            "type": "env",
        },
        {
            "title": "6. 동작 확인",
            "cmd": f'ollama run {model_name} "이 차량은 무엇인가요?"',
            "type": "cmd",
        },
    ]

    return {
        "checkpoint_path": checkpoint_path,
        "model_name": model_name,
        "steps": steps,
    }
