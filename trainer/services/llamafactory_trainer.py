"""
LLaMA-Factory CLI 래퍼 (Linux/Windows NVIDIA GPU)
- Docker Trainer 컨테이너 내에서 직접 llamafactory-cli를 실행
"""
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from trainer.config import settings

logger = logging.getLogger(__name__)


class LlamaFactoryTrainer:
    """LLaMA-Factory CLI 직접 실행 (컨테이너 내 네이티브 실행)"""

    def __init__(self):
        self.data_dir = settings.data_path
        self.output_base = str(settings.output_path)
        logger.info(f"LlamaFactoryTrainer init: data={self.data_dir}, output={self.output_base}")

    @property
    def train_config_path(self) -> str:
        return str(self.data_dir / "train_config.yaml")

    async def _exec(self, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
        logger.info(f"Executing: {cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return proc.returncode, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    async def _exec_detached(self, cmd: str) -> tuple[int, str, str]:
        log_dir = self.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "train.log"
        full_cmd = f"nohup {cmd} > {log_file} 2>&1 &"
        logger.info(f"Executing detached: {full_cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode, stdout.decode(), stderr.decode()
        except Exception as e:
            return -1, "", str(e)

    def generate_train_yaml(
        self,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
        learning_rate: float = 1e-4,
        num_epochs: float = 3.0,
        batch_size: int = 2,
        gradient_accumulation: int = 4,
        lora_rank: int = 8,
        quantization_bit: Optional[int] = 4,
        output_dir: str = "vehicle-vlm",
        flash_attn: Optional[str] = None,
        use_mps: bool = False,
        fp16: bool = False,
        cutoff_len: int = 2048,
    ) -> str:
        config = {
            "model_name_or_path": model_name,
            "stage": "sft",
            "do_train": True,
            "finetuning_type": "lora",
            "lora_rank": lora_rank,
            "lora_target": "all",
            "dataset": "vehicle_train",
            "dataset_dir": str(self.data_dir.resolve()),
            "template": "qwen3_vl",
            "cutoff_len": cutoff_len,
            "overwrite_cache": True,
            "preprocessing_num_workers": 4,
            "output_dir": f"{self.output_base}/{output_dir}",
            "logging_steps": 5,
            "save_steps": 100,
            "eval_steps": 100,
            "plot_loss": True,
            "per_device_train_batch_size": batch_size,
            "gradient_accumulation_steps": gradient_accumulation,
            "gradient_checkpointing": True,
            "learning_rate": learning_rate,
            "num_train_epochs": num_epochs,
            "lr_scheduler_type": "cosine",
            "warmup_ratio": 0.1,
            "report_to": "none",
        }

        if quantization_bit is not None:
            config["quantization_bit"] = quantization_bit
            config["quantization_type"] = "nf4"

        if not use_mps:
            config["bf16"] = True

        if flash_attn:
            config["flash_attn"] = flash_attn

        val_path = self.data_dir / "vehicle_val.json"
        if val_path.exists():
            config["eval_dataset"] = "vehicle_val"

        import yaml
        yaml_path = self.data_dir / "train_config.yaml"
        yaml_path.parent.mkdir(parents=True, exist_ok=True)
        yaml_path.write_text(
            yaml.dump(config, default_flow_style=False, allow_unicode=True),
            encoding="utf-8",
        )
        logger.info(f"Training config saved: {yaml_path}")
        return str(yaml_path)

    async def start_training(self, config_path: Optional[str] = None) -> dict:
        if config_path is None:
            config_path = self.train_config_path

        status = await self.get_status()
        if status.get("is_running"):
            return {"error": "Training is already running", "status": status}

        rc, stdout, stderr = await self._exec_detached(
            f"llamafactory-cli train {config_path}"
        )
        if rc != 0 and rc != -1:
            return {"error": f"Failed to start training: {stderr}"}

        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Training started: job_id={job_id}")
        return {"job_id": job_id, "message": "Training started", "config_path": config_path}

    async def get_status(self) -> dict:
        rc, stdout, stderr = await self._exec(
            "pgrep -f '[l]lamafactory-cli train'", timeout=5
        )
        is_running = rc == 0 and stdout.strip() != ""

        log_path = ""
        if Path(self.output_base).exists():
            rc, stdout, stderr = await self._exec(
                f"find {self.output_base} -name 'trainer_log.jsonl' -type f | sort -r | head -1",
                timeout=10,
            )
            log_path = stdout.strip()

        status = {
            "is_running": is_running,
            "log_path": log_path,
            "step": 0,
            "epoch": 0.0,
            "loss": None,
            "learning_rate": None,
        }

        if log_path:
            rc, stdout, stderr = await self._exec(f"tail -1 {log_path}", timeout=5)
            if rc == 0 and stdout.strip():
                try:
                    last_entry = json.loads(stdout.strip())
                    status["step"] = last_entry.get("current_steps", 0)
                    status["epoch"] = last_entry.get("epoch", 0.0)
                    status["loss"] = last_entry.get("loss")
                    status["learning_rate"] = last_entry.get("learning_rate")
                    status["total_steps"] = last_entry.get("total_steps")
                    status["percentage"] = last_entry.get("percentage")
                except json.JSONDecodeError:
                    pass

        return status

    async def stop_training(self) -> dict:
        rc, stdout, stderr = await self._exec(
            "pkill -f '[l]lamafactory-cli train'", timeout=10
        )
        if rc == 0:
            return {"message": "Training stopped"}
        return {"message": "No training process found or already stopped"}

    async def get_logs(self, tail: int = 50) -> list:
        rc, stdout, stderr = await self._exec(
            f"find {self.output_base} -name 'trainer_log.jsonl' -type f | sort -r | head -1",
            timeout=10,
        )
        log_path = stdout.strip()
        if not log_path:
            return []

        rc, stdout, stderr = await self._exec(f"tail -{tail} {log_path}", timeout=10)
        if rc != 0:
            return []

        logs = []
        for line in stdout.strip().split("\n"):
            if line.strip():
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return logs

    async def get_raw_log(self, tail: int = 100) -> str:
        log_file = self.data_dir / "logs" / "train.log"
        rc, stdout, stderr = await self._exec(f"tail -{tail} {log_file}", timeout=5)
        return stdout if rc == 0 else f"(로그 없음: {log_file})"

    async def export_model(
        self,
        checkpoint_path: str,
        output_dir: Optional[str] = None,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
    ) -> dict:
        if output_dir is None:
            output_dir = str(settings.vlm_model_dir)
        cmd = (
            f"llamafactory-cli export "
            f"--model_name_or_path {model_name} "
            f"--adapter_name_or_path {checkpoint_path} "
            f"--export_dir {output_dir} "
            f"--export_size 2 "
            f"--export_legacy_format false"
        )
        rc, stdout, stderr = await self._exec(cmd, timeout=600)
        if rc != 0:
            return {"error": f"Export failed: {stderr}"}

        # llamafactory export 버그: extra_special_tokens를 list로 저장 → dict로 수정
        import json as _json
        tokenizer_cfg_path = Path(output_dir) / "tokenizer_config.json"
        if tokenizer_cfg_path.exists():
            try:
                cfg = _json.loads(tokenizer_cfg_path.read_text(encoding="utf-8"))
                if isinstance(cfg.get("extra_special_tokens"), list):
                    cfg["extra_special_tokens"] = {}
                    tokenizer_cfg_path.write_text(
                        _json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
            except Exception as e:
                logger.warning(f"Failed to fix tokenizer_config.json: {e}")

        return {"message": "Export completed", "output_dir": output_dir}
