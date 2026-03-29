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
import httpx
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


@router.get("/hw-profile")
async def get_hw_profile():
    """하드웨어 감지 → 파인튜닝 최적 파라미터 프리셋 반환"""
    import platform
    from studio.services.llamafactory import llamafactory_service

    # Native 모드 + arm64 → Apple Silicon (Docker 안에서는 MPS 불가)
    if llamafactory_service.native and platform.machine() in ("arm64", "aarch64"):
        try:
            import psutil
            ram_gb = psutil.virtual_memory().total / 1024 ** 3
        except Exception:
            ram_gb = 0
        return {
            "hw": "apple_silicon",
            "label": f"Apple Silicon MPS ({ram_gb:.0f} GB unified) [native]",
            "preset": {
                "batch_size": 1, "gradient_accumulation": 8,
                "lora_rank": 16, "quantization_bit": None,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": None, "use_mps": True, "fp16": True,
                "cutoff_len": 1024,
            },
        }

    try:
        import torch
    except ImportError:
        return {"hw": "cpu", "label": "CPU Only", "preset": _cpu_preset()}

    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_properties(0)
        vram_gb = gpu.total_memory / 1024 ** 3
        cc_major, cc_minor = torch.cuda.get_device_capability(0)

        # Blackwell GB10 (sm_12x) or ≥100 GB → DGX Spark
        # - flash_attn fa2: sm_121 공식 미지원, PyTorch SDPA 사용 (2% 더 빠름)
        # - quantization: bitsandbytes aarch64+sm_121 공식 빌드 지원 → 4-bit NF4 사용
        # - bf16: 지원
        # ref: https://github.com/natolambert/dgx-spark-setup
        if cc_major >= 12 or vram_gb >= 100:
            hw, label = "dgx_spark", f"NVIDIA {gpu.name} ({vram_gb:.0f} GB, sm_{cc_major}{cc_minor})"
            preset = {
                "batch_size": 1, "gradient_accumulation": 4,
                "lora_rank": 64, "quantization_bit": 4,
                "learning_rate": "1e-5", "num_epochs": 3.0,
                "flash_attn": None,   # sm_121 미지원 — SDPA 사용
                "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        elif vram_gb >= 40:   # A100-80G / H100-80G (sm_80/90)
            hw, label = "high_end_gpu", f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 4, "gradient_accumulation": 4,
                "lora_rank": 32, "quantization_bit": None,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": "fa2", "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        elif vram_gb >= 20:   # 3090 / A6000 / 4090 (≥20 GB)
            hw, label = "mid_gpu", f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 2, "gradient_accumulation": 8,
                "lora_rank": 16, "quantization_bit": 4,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": "fa2", "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        else:                 # ≤16 GB
            hw, label = "low_gpu", f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 1, "gradient_accumulation": 16,
                "lora_rank": 8, "quantization_bit": 4,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": None, "use_mps": False, "fp16": False,
                "cutoff_len": 1024,
            }

    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        # Apple Silicon MPS
        # - bitsandbytes GPU 가속 quantization 미지원 (PR#1853 미병합, 2026-03 기준)
        #   CPU fallback만 가능 → 매우 느림 → quantization 생략
        # - BF16 미지원 (PyTorch MPS) → fp16 사용
        # - flash_attn: 해당 없음
        # - 64GB 통합메모리 → fp16 LoRA로 8B 모델 충분히 적재 가능
        # ref: https://github.com/hiyouga/LLaMA-Factory/issues/7534
        try:
            import psutil
            ram_gb = psutil.virtual_memory().total / 1024 ** 3
        except Exception:
            ram_gb = 0
        hw = "apple_silicon"
        label = f"Apple Silicon MPS ({ram_gb:.0f} GB unified)"
        preset = {
            "batch_size": 1, "gradient_accumulation": 8,
            "lora_rank": 16, "quantization_bit": None,   # bitsandbytes MPS GPU 미지원
            "learning_rate": "1e-4", "num_epochs": 3.0,
            "flash_attn": None, "use_mps": True, "fp16": True,   # bf16 MPS 에러
            "cutoff_len": 1024,
        }
    else:
        hw, label = "cpu", "CPU Only"
        preset = _cpu_preset()

    return {"hw": hw, "label": label, "preset": preset}


def _cpu_preset() -> dict:
    return {
        "batch_size": 1, "gradient_accumulation": 16,
        "lora_rank": 8, "quantization_bit": 4,
        "learning_rate": "1e-4", "num_epochs": 1.0,
        "flash_attn": None, "use_mps": False, "fp16": False,
        "cutoff_len": 512,
    }


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


# =============================================================================
# LLaMA-Factory 학습 자동화 엔드포인트
# =============================================================================

class TrainingConfig(BaseModel):
    """학습 설정"""
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"
    learning_rate: float = 1e-4
    num_epochs: float = 3.0
    batch_size: int = 2
    gradient_accumulation: int = 4
    lora_rank: int = 8
    quantization_bit: Optional[int] = 4   # None = 양자화 없음 (Full LoRA)
    cutoff_len: int = 1024
    output_dir: str = "vehicle-vlm"
    flash_attn: Optional[str] = None      # "fa2" | None
    use_mps: bool = False                  # Apple Silicon MPS
    fp16: bool = False                     # MPS 전용 (bf16 불가)


class ExportModelRequest(BaseModel):
    """LoRA 병합 요청"""
    checkpoint_path: str
    output_dir: str = "/app/output/merged"
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"


@router.post("/train/start")
async def start_training(config: TrainingConfig):
    """LLaMA-Factory 학습 시작"""
    from studio.services.llamafactory import llamafactory_service

    try:
        # YAML 설정 파일 생성
        config_path = llamafactory_service.generate_train_yaml(
            model_name=config.model_name,
            learning_rate=config.learning_rate,
            num_epochs=config.num_epochs,
            batch_size=config.batch_size,
            gradient_accumulation=config.gradient_accumulation,
            lora_rank=config.lora_rank,
            quantization_bit=config.quantization_bit,
            cutoff_len=config.cutoff_len,
            output_dir=config.output_dir,
            flash_attn=config.flash_attn,
            use_mps=config.use_mps,
            fp16=config.fp16,
        )

        # 학습 시작 (native 모드: 로컬 경로 / Docker 모드: 컨테이너 내 경로 자동 사용)
        result = await llamafactory_service.start_training()

        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/status")
async def get_training_status():
    """학습 진행 상태 조회"""
    from studio.services.llamafactory import llamafactory_service

    try:
        return await llamafactory_service.get_status()
    except Exception as e:
        logger.error(f"Failed to get training status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/stop")
async def stop_training():
    """학습 중지"""
    from studio.services.llamafactory import llamafactory_service

    try:
        return await llamafactory_service.stop_training()
    except Exception as e:
        logger.error(f"Failed to stop training: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/logs")
async def get_training_logs(tail: int = Query(default=50, ge=1, le=500)):
    """학습 로그 조회"""
    from studio.services.llamafactory import llamafactory_service

    try:
        logs = await llamafactory_service.get_logs(tail=tail)
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        logger.error(f"Failed to get training logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/raw-log")
async def get_raw_training_log(tail: int = Query(default=100, ge=1, le=1000)):
    """nohup train.log 원문 반환 (학습 시작 실패·에러 확인용)"""
    from studio.services.llamafactory import llamafactory_service

    try:
        content = await llamafactory_service.get_raw_log(tail=tail)
        return {"content": content}
    except Exception as e:
        logger.error(f"Failed to get raw training log: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/export")
async def export_model(req: ExportModelRequest):
    """LoRA 어댑터 병합 (Export)"""
    from studio.services.llamafactory import llamafactory_service

    try:
        result = await llamafactory_service.export_model(
            checkpoint_path=req.checkpoint_path,
            output_dir=req.output_dir,
            model_name=req.model_name,
        )
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

    async with httpx.AsyncClient(timeout=30.0) as client:
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
