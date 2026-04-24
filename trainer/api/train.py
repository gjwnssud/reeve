"""
Trainer API 라우터
- 하드웨어 감지 및 파라미터 프리셋
- 학습 시작/상태/중지/로그
- 모델 Export (LoRA 병합)
- Ollama 배포 커맨드 생성
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from pydantic import BaseModel
import asyncio

router = APIRouter()


def _get_trainer():
    """TRAINER_BACKEND 환경변수에 따라 트레이너 인스턴스 반환"""
    from trainer.config import settings
    if settings.trainer_backend == "mlx":
        from trainer.services.mlx_trainer import MLXTrainer
        return MLXTrainer()
    if settings.trainer_backend == "efficientnet":
        from trainer.services.efficientnet_trainer import EfficientNetTrainer
        return EfficientNetTrainer()
    from trainer.services.llamafactory_trainer import LlamaFactoryTrainer
    return LlamaFactoryTrainer()


def _cpu_preset() -> dict:
    return {
        "batch_size": 1, "gradient_accumulation": 16,
        "lora_rank": 8, "quantization_bit": 4,
        "learning_rate": "1e-4", "num_epochs": 1.0,
        "flash_attn": None, "use_mps": False, "fp16": False,
        "cutoff_len": 512,
    }


@router.get("/hw-profile")
async def get_hw_profile():
    """하드웨어 감지 → 파인튜닝 최적 파라미터 프리셋 반환"""
    from trainer.config import settings

    # EfficientNet 백엔드 — PyTorch 이미지 분류기 (MPS/CUDA/CPU 자동 감지)
    if settings.trainer_backend == "efficientnet":
        import os
        try:
            import torch
            if torch.backends.mps.is_available():
                hw = "apple_silicon"
                label = "Apple Silicon MPS (EfficientNetV2-M)"
                batch_size = 16
                preset_extra = {
                    "gradient_accumulation": 2, "num_workers": 2,
                    "use_ema": True, "use_mixup": False,
                }
            elif torch.cuda.is_available():
                gpu = torch.cuda.get_device_properties(0)
                vram_gb = gpu.total_memory / 1024 ** 3
                cc_major, cc_minor = torch.cuda.get_device_capability(0)
                if cc_major >= 12 or vram_gb >= 100:
                    hw = "dgx_spark"
                    label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB, sm_{cc_major}{cc_minor})"
                    batch_size = 64
                    preset_extra = {
                        "gradient_accumulation": 1,
                        "num_workers": min(16, os.cpu_count() or 4),
                        "use_ema": True, "use_mixup": True,
                    }
                elif vram_gb >= 20:
                    hw = "high_end_gpu"
                    label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
                    batch_size = 32
                    preset_extra = {
                        "gradient_accumulation": 2,
                        "num_workers": min(8, os.cpu_count() or 4),
                        "use_ema": True, "use_mixup": True,
                    }
                elif vram_gb >= 8:
                    hw = "mid_gpu"
                    label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
                    batch_size = 16
                    preset_extra = {
                        "gradient_accumulation": 4, "num_workers": 4,
                        "use_ema": False, "use_mixup": False,
                    }
                else:
                    hw = "low_gpu"
                    label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
                    batch_size = 8
                    preset_extra = {
                        "gradient_accumulation": 8, "num_workers": 2,
                        "use_ema": False, "use_mixup": False,
                    }
            else:
                hw = "cpu"
                label = "CPU Only"
                batch_size = 4
                preset_extra = {
                    "gradient_accumulation": 8, "num_workers": 0,
                    "use_ema": False, "use_mixup": False,
                }
        except ImportError:
            hw, label, batch_size = "cpu", "CPU Only", 4
            preset_extra = {
                "gradient_accumulation": 8, "num_workers": 0,
                "use_ema": False, "use_mixup": False,
            }

        preset = {
            "batch_size": batch_size,
            "learning_rate": "1e-4",
            "num_epochs": 10,
            "freeze_epochs": 1,
            "lora_rank": None,
            "quantization_bit": None,
            "cutoff_len": None,
            "flash_attn": None,
            "early_stopping_patience": 3,
            **preset_extra,
        }
        return {
            "hw": hw,
            "backend": "efficientnet",
            "label": label,
            "preset": preset,
        }

    # MLX 백엔드 = Apple Silicon 확정
    if settings.trainer_backend == "mlx":
        try:
            import psutil
            ram_gb = psutil.virtual_memory().total / 1024 ** 3
        except Exception:
            ram_gb = 0
        return {
            "hw": "apple_silicon",
            "backend": "mlx",
            "label": f"Apple Silicon MPS ({ram_gb:.0f} GB unified) [mlx]",
            "preset": {
                "batch_size": 1, "gradient_accumulation": 8,
                "lora_rank": 16, "quantization_bit": None,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": None, "use_mps": True, "fp16": False,
                "cutoff_len": 1024,
            },
        }

    # LlamaFactory 백엔드 — GPU/CPU 감지
    try:
        import torch
    except ImportError:
        return {"hw": "cpu", "backend": "llamafactory", "label": "CPU Only", "preset": _cpu_preset()}

    if torch.cuda.is_available():
        gpu = torch.cuda.get_device_properties(0)
        vram_gb = gpu.total_memory / 1024 ** 3
        cc_major, cc_minor = torch.cuda.get_device_capability(0)

        if cc_major >= 12 or vram_gb >= 100:
            hw = "dgx_spark"
            label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB, sm_{cc_major}{cc_minor})"
            preset = {
                "batch_size": 1, "gradient_accumulation": 4,
                "lora_rank": 64, "quantization_bit": 4,
                "learning_rate": "1e-5", "num_epochs": 3.0,
                "flash_attn": None, "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        elif vram_gb >= 40:
            hw = "high_end_gpu"
            label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 4, "gradient_accumulation": 4,
                "lora_rank": 32, "quantization_bit": None,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": "fa2", "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        elif vram_gb >= 20:
            hw = "mid_gpu"
            label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 2, "gradient_accumulation": 8,
                "lora_rank": 16, "quantization_bit": 4,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": "fa2", "use_mps": False, "fp16": False,
                "cutoff_len": 2048,
            }
        else:
            hw = "low_gpu"
            label = f"NVIDIA {gpu.name} ({vram_gb:.0f} GB)"
            preset = {
                "batch_size": 1, "gradient_accumulation": 16,
                "lora_rank": 8, "quantization_bit": 4,
                "learning_rate": "1e-4", "num_epochs": 3.0,
                "flash_attn": None, "use_mps": False, "fp16": False,
                "cutoff_len": 1024,
            }
    else:
        hw, label = "cpu", "CPU Only"
        preset = _cpu_preset()

    return {"hw": hw, "backend": "llamafactory", "label": label, "preset": preset}


@router.get("/model-info")
async def get_model_info():
    """현재 저장된 EfficientNet 모델의 클래스 수 반환"""
    import json, os
    from trainer.config import settings
    path = os.path.join(settings.efficientnet_model_dir, "class_mapping.json")
    if not os.path.exists(path):
        return {"num_classes": None}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {"num_classes": data.get("num_classes")}


class TrainingConfig(BaseModel):
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"
    learning_rate: float = 1e-4
    num_epochs: float = 3.0
    batch_size: int = 2
    gradient_accumulation: int = 4
    lora_rank: Optional[int] = 8
    quantization_bit: Optional[int] = 4
    cutoff_len: Optional[int] = 1024
    output_dir: str = "efficientnet"
    flash_attn: Optional[str] = None
    use_mps: bool = False
    fp16: bool = False
    # EfficientNet 전용 필드
    freeze_epochs: int = 3
    studio_url: Optional[str] = None
    max_per_class: Optional[int] = None  # 클래스당 최대 샘플 수 (None = 제한 없음)
    min_per_class: Optional[int] = None  # 클래스당 최소 샘플 수 (미만 클래스 제외)
    use_ema: bool = False
    use_mixup: bool = False
    num_workers: Optional[int] = None  # None = 플랫폼 자동 감지
    early_stopping_patience: int = 7


class ExportModelRequest(BaseModel):
    checkpoint_path: str
    output_dir: str = "output/merged"
    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"


@router.post("/train/start")
async def start_training(config: TrainingConfig):
    """학습 시작"""
    trainer = _get_trainer()
    try:
        from trainer.config import settings

        if settings.trainer_backend == "efficientnet":
            result = await trainer.start_training(
                learning_rate=config.learning_rate,
                num_epochs=int(config.num_epochs),
                batch_size=config.batch_size,
                freeze_epochs=config.freeze_epochs,
                output_dir="efficientnet",
                studio_url=config.studio_url or settings.studio_url,
                max_per_class=config.max_per_class,
                min_per_class=config.min_per_class,
                gradient_accumulation=config.gradient_accumulation,
                use_ema=config.use_ema,
                use_mixup=config.use_mixup,
                num_workers=config.num_workers,
                early_stopping_patience=config.early_stopping_patience,
            )
        elif settings.trainer_backend == "llamafactory":
            config_path = trainer.generate_train_yaml(
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
            result = await trainer.start_training(config_path=config_path)
        else:
            # MLX: start_training이 직접 파라미터 수신
            result = await trainer.start_training(
                model_name=config.model_name,
                learning_rate=config.learning_rate,
                num_epochs=config.num_epochs,
                batch_size=config.batch_size,
                gradient_accumulation=config.gradient_accumulation,
                lora_rank=config.lora_rank,
                output_dir="vehicle-vlm",
                cutoff_len=config.cutoff_len,
            )

        if "error" in result:
            raise HTTPException(status_code=409, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/status")
async def get_training_status():
    """학습 진행 상태 조회"""
    try:
        return await _get_trainer().get_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/train/stop")
async def stop_training():
    """학습 중지"""
    try:
        return await _get_trainer().stop_training()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/logs")
async def get_training_logs(tail: int = Query(default=50, ge=1, le=500)):
    """학습 로그 조회 (trainer_log.jsonl)"""
    try:
        logs = await _get_trainer().get_logs(tail=tail)
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/raw-log")
async def get_raw_training_log(tail: int = Query(default=100, ge=1, le=1000)):
    """원시 학습 로그 반환 (stderr/nohup 출력)"""
    try:
        content = await _get_trainer().get_raw_log(tail=tail)
        return {"lines": content.splitlines() if content else []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/train/deploy-config")
async def get_deploy_config():
    """핫리로드에 필요한 Identifier 측 경로 반환 (EfficientNet 전용)"""
    from trainer.config import settings
    return {
        "model_path": settings.identifier_efficientnet_model_path,
        "class_mapping_path": settings.identifier_class_mapping_path,
        "identifier_url": settings.identifier_url,
    }


@router.post("/train/export")
async def export_model(req: ExportModelRequest):
    """LoRA 어댑터 병합 (Export)"""
    try:
        result = await _get_trainer().export_model(
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
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deploy/cmd")
async def deploy_cmd(
    checkpoint_path: str = Query(..., description="학습된 체크포인트 경로"),
    model_name: str = Query("reeve-vlm-v1", description="Ollama 등록 모델명"),
):
    """체크포인트 경로 → Ollama 배포 커맨드 목록 반환"""
    from trainer.config import settings

    gguf_filename = "model.gguf"
    gguf_path = f"{checkpoint_path}/{gguf_filename}"
    merged_dir = f"{checkpoint_path}/merged"

    modelfile_content = (
        f"FROM ./{gguf_filename}\n"
        f'SYSTEM "당신은 차량 식별 전문가입니다. '
        f'차량 이미지를 보고 제조사와 모델을 정확하게 식별합니다."\n'
    )

    if settings.trainer_backend == "mlx":
        merge_step = {
            "title": "1. LoRA 어댑터 병합 (mlx-lm)",
            "cmd": (
                f"python -m mlx_lm.fuse"
                f" --model Qwen/Qwen3-VL-8B-Instruct"
                f" --adapter-path {checkpoint_path}"
                f" --save-path {merged_dir}"
                f" --de-quantize"
            ),
            "type": "cmd",
        }
    else:
        merge_step = {
            "title": "1. LoRA 어댑터 병합 (LLaMA-Factory)",
            "cmd": (
                f"llamafactory-cli export"
                f" --model_name_or_path Qwen/Qwen3-VL-8B-Instruct"
                f" --adapter_name_or_path {checkpoint_path}"
                f" --export_dir {merged_dir}"
                f" --export_size 2"
                f" --export_legacy_format false"
            ),
            "type": "cmd",
        }

    steps = [
        merge_step,
        {
            "title": "2. GGUF 변환 (llama.cpp 필요)",
            "cmd": (
                f"python convert_hf_to_gguf.py {merged_dir}"
                f" --outtype f16 --outfile {gguf_path}"
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
        "backend": settings.trainer_backend,
        "steps": steps,
    }


class OllamaDeployRequest(BaseModel):
    merged_model_dir: str
    model_name: str = "reeve-vlm-v1"
    notify_identifier: bool = True


@router.post("/deploy/ollama")
async def deploy_to_ollama(req: OllamaDeployRequest):
    """
    병합된 모델을 Ollama에 자동 등록하고 Identifier 서비스에 핫리로드 알림.

    사전 조건:
    - POST /train/export 로 LoRA 어댑터를 병합한 merged_model_dir이 준비되어 있어야 함
    - GGUF 자동 변환을 원하면 GGUF_CONVERTER_PATH 환경변수에 convert_hf_to_gguf.py 경로 설정
    - merged_model_dir 안에 model.gguf가 이미 있으면 변환 단계를 건너뜀

    파이프라인:
      1. GGUF 변환 (model.gguf 없을 때, GGUF_CONVERTER_PATH 설정 시)
      2. Ollama Modelfile 생성 + /api/create 등록
      3. Identifier /admin/reload-vlm 호출 (notify_identifier=true 시)
    """
    from trainer.config import settings
    from trainer.services.ollama_deployer import OllamaDeployer

    deployer = OllamaDeployer(
        ollama_base_url=settings.ollama_base_url,
        identifier_base_url=settings.identifier_url,
        gguf_converter_path=settings.gguf_converter_path,
    )

    result = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: deployer.deploy(
            merged_model_dir=req.merged_model_dir,
            model_name=req.model_name,
            notify_identifier=req.notify_identifier,
        ),
    )

    if "error" in result:
        raise HTTPException(status_code=500, detail=result)
    return result
