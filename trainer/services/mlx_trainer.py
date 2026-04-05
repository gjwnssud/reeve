"""
MLX 기반 파인튜닝 트레이너 (Mac Apple Silicon 전용)
mlx-lm 또는 mlx-vlm을 사용하여 LoRA 파인튜닝 실행

의존성:
  pip install mlx-lm mlx-vlm

학습 로그는 trainer_log.jsonl 형식으로 변환하여 저장 (LlamaFactory 호환)
"""
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

from trainer.config import settings

logger = logging.getLogger(__name__)

# trainer_log.jsonl 변환 로그 경로
_JSONL_LOG_FILENAME = "trainer_log.jsonl"
# mlx 원시 stderr 로그
_RAW_LOG_FILENAME = "train.log"


class MLXTrainer:
    """mlx-lm LoRA 파인튜닝 (Apple Silicon MPS)"""

    def __init__(self):
        self.data_dir = settings.data_path
        self.output_base = str(settings.output_path)
        logger.info(f"MLXTrainer init: data={self.data_dir}, output={self.output_base}")

    async def _exec(self, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
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

    def _log_dir(self, output_dir: str) -> Path:
        return Path(self.output_base) / output_dir

    def generate_train_yaml(self, **kwargs) -> str:
        """MLX 백엔드에서는 YAML 불필요. 호환성을 위해 빈 경로 반환."""
        return ""

    def _build_mlx_cmd(
        self,
        model_name: str,
        learning_rate: float,
        num_epochs: float,
        batch_size: int,
        gradient_accumulation: int,
        lora_rank: int,
        output_dir: str,
        cutoff_len: int,
        **kwargs,
    ) -> str:
        """mlx_lm.lora 학습 커맨드 생성"""
        adapter_path = f"{self.output_base}/{output_dir}"
        data_path = str(self.data_dir)

        # mlx-lm은 iters(스텝 수)로 학습량을 지정 (epoch 미지원)
        # train.json 크기 기반으로 스텝 수 추정
        train_file = self.data_dir / "vehicle_train.json"
        try:
            data = json.loads(train_file.read_text(encoding="utf-8"))
            n_samples = len(data)
        except Exception:
            n_samples = 100
        iters = max(100, int(n_samples * num_epochs / batch_size))

        return (
            f"python -m mlx_lm.lora"
            f" --model {model_name}"
            f" --train"
            f" --data {data_path}"
            f" --batch-size {batch_size}"
            f" --lora-layers {lora_rank}"
            f" --iters {iters}"
            f" --learning-rate {learning_rate}"
            f" --adapter-path {adapter_path}"
            f" --max-seq-length {cutoff_len}"
            f" --grad-checkpoint"
        )

    async def start_training(
        self,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
        learning_rate: float = 1e-4,
        num_epochs: float = 3.0,
        batch_size: int = 1,
        gradient_accumulation: int = 8,
        lora_rank: int = 16,
        output_dir: str = "vehicle-vlm",
        cutoff_len: int = 1024,
        config_path: Optional[str] = None,
        **kwargs,
    ) -> dict:
        status = await self.get_status()
        if status.get("is_running"):
            return {"error": "Training is already running", "status": status}

        run_dir = self._log_dir(output_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        raw_log = log_dir / _RAW_LOG_FILENAME
        jsonl_log = run_dir / _JSONL_LOG_FILENAME

        mlx_cmd = self._build_mlx_cmd(
            model_name=model_name,
            learning_rate=learning_rate,
            num_epochs=num_epochs,
            batch_size=batch_size,
            gradient_accumulation=gradient_accumulation,
            lora_rank=lora_rank,
            output_dir=output_dir,
            cutoff_len=cutoff_len,
        )

        # MLX stdout/stderr → trainer_log.jsonl 변환 래퍼 스크립트 실행
        wrapper_cmd = (
            f"nohup python -u -c \""
            f"import subprocess, sys, json, re, time\n"
            f"proc = subprocess.Popen({repr(mlx_cmd.split())}, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)\n"
            f"step = 0\n"
            f"with open('{jsonl_log}', 'w') as jf, open('{raw_log}', 'w') as rf:\n"
            f"    for line in proc.stdout:\n"
            f"        rf.write(line); rf.flush()\n"
            f"        m = re.search(r'Iter (\\\\d+).*Loss ([\\\\.\\\\d]+)', line)\n"
            f"        if m:\n"
            f"            step = int(m.group(1))\n"
            f"            entry = {{'current_steps': step, 'loss': float(m.group(2)), 'epoch': 0.0}}\n"
            f"            jf.write(json.dumps(entry) + '\\\\n'); jf.flush()\n"
            f"proc.wait()\n"
            f"\" >> {raw_log} 2>&1 &"
        )

        # 보다 안정적인 방법: 래퍼 스크립트를 임시 파일로 작성 후 실행
        wrapper_script = log_dir / "mlx_wrapper.py"
        wrapper_script.write_text(
            f"""import subprocess, json, re
import sys

mlx_cmd = {repr(mlx_cmd.split())}
jsonl_log = {repr(str(jsonl_log))}
raw_log = {repr(str(raw_log))}

proc = subprocess.Popen(mlx_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
with open(jsonl_log, 'w') as jf, open(raw_log, 'w') as rf:
    for line in proc.stdout:
        rf.write(line)
        rf.flush()
        # mlx-lm 로그 형식: "Iter 10: Train loss 2.345, ..."
        m = re.search(r'Iter (\\d+).*[Ll]oss ([\\d\\.]+)', line)
        if m:
            step = int(m.group(1))
            loss = float(m.group(2))
            entry = {{"current_steps": step, "loss": loss, "epoch": 0.0}}
            jf.write(json.dumps(entry) + '\\n')
            jf.flush()
proc.wait()
""",
            encoding="utf-8",
        )

        full_cmd = f"nohup python {wrapper_script} >> {raw_log} 2>&1 &"
        rc, stdout, stderr = await self._exec(full_cmd, timeout=10)
        if rc not in (0, -1):
            return {"error": f"Failed to start MLX training: {stderr}"}

        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"MLX Training started: job_id={job_id}, cmd={mlx_cmd}")
        return {"job_id": job_id, "message": "MLX Training started", "cmd": mlx_cmd}

    async def get_status(self) -> dict:
        rc, stdout, stderr = await self._exec(
            "pgrep -f '[m]lx_lm.lora'", timeout=5
        )
        is_running = rc == 0 and stdout.strip() != ""

        # 가장 최근 trainer_log.jsonl 찾기
        log_path = ""
        if Path(self.output_base).exists():
            rc, stdout, stderr = await self._exec(
                f"find {self.output_base} -name '{_JSONL_LOG_FILENAME}' -type f | sort -r | head -1",
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
            "pkill -f '[m]lx_lm.lora'", timeout=10
        )
        if rc == 0:
            return {"message": "Training stopped"}
        return {"message": "No training process found or already stopped"}

    async def get_logs(self, tail: int = 50) -> list:
        rc, stdout, stderr = await self._exec(
            f"find {self.output_base} -name '{_JSONL_LOG_FILENAME}' -type f | sort -r | head -1",
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
        log_file = self.data_dir / "logs" / _RAW_LOG_FILENAME
        rc, stdout, stderr = await self._exec(f"tail -{tail} {log_file}", timeout=5)
        return stdout if rc == 0 else f"(로그 없음: {log_file})"

    async def export_model(
        self,
        checkpoint_path: str,
        output_dir: Optional[str] = None,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
    ) -> dict:
        """mlx-lm LoRA 어댑터를 베이스 모델에 병합"""
        if output_dir is None:
            output_dir = str(settings.vlm_model_dir)

        cmd = (
            f"python -m mlx_lm.fuse"
            f" --model {model_name}"
            f" --adapter-path {checkpoint_path}"
            f" --save-path {output_dir}"
            f" --de-quantize"
        )
        rc, stdout, stderr = await self._exec(cmd, timeout=600)
        if rc != 0:
            return {"error": f"MLX export failed: {stderr}"}

        return {"message": "Export completed", "output_dir": output_dir}
