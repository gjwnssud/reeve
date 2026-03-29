"""
LLaMA-Factory CLI 자동화 서비스
- Docker 모드: docker exec {container}으로 명령 실행
- Native 모드: Docker 컨테이너 없고 로컬에 llamafactory-cli 설치 시 자동 전환 (Mac MPS 지원)
"""
import asyncio
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from studio.config import settings

logger = logging.getLogger(__name__)


class LlamaFactoryService:
    """LLaMA-Factory CLI 래퍼 (Docker exec 또는 Native 모드 자동 감지)"""

    def __init__(self):
        self.container = settings.llamafactory_container
        self.data_dir = Path("data/finetune").resolve()  # 절대경로로 고정
        self.webui_url = "http://localhost:7860"  # _auto_detect에서 갱신될 수 있음
        self.native = self._auto_detect()
        # native 모드: 절대경로 / Docker 모드: 컨테이너 내부 경로
        self.output_base = str(self.data_dir / "output") if self.native else "/app/output"
        logger.info(f"LlamaFactory mode: {'native' if self.native else 'docker'}, output={self.output_base}")

    def _auto_detect(self) -> bool:
        """
        실행 모드 자동 감지:
        1. docker exec {container} true → 성공이면 Docker 모드
        2. 실패 시 LLaMA-Factory WebUI(7860) 접근 확인
           - host.docker.internal:7860 → Studio가 Docker 컨테이너일 때 macOS 호스트 접근
           - localhost:7860 → Studio도 네이티브 실행일 때
        """
        try:
            result = subprocess.run(
                ["docker", "exec", self.container, "true"],
                capture_output=True, timeout=3
            )
            if result.returncode == 0:
                logger.info(f"LlamaFactory: Docker container '{self.container}' detected")
                return False
        except Exception:
            pass

        import urllib.request
        for host in ("host.docker.internal", "localhost"):
            try:
                urllib.request.urlopen(f"http://{host}:7860/", timeout=3)
                self.webui_url = f"http://{host}:7860"
                logger.info(f"LlamaFactory: native WebUI detected at {self.webui_url}")
                return True
            except Exception:
                pass

        logger.warning("LlamaFactory: neither Docker container nor native WebUI(7860) found")
        return False

    @property
    def train_config_path(self) -> str:
        """학습 설정 YAML 경로 (모드별)"""
        if self.native:
            return str(self.data_dir / "train_config.yaml")
        return "/app/data/train_config.yaml"  # 컨테이너 내 마운트 경로

    def _build_cmd(self, cmd: str) -> str:
        if self.native:
            return cmd
        return f"docker exec {self.container} {cmd}"

    def _build_detached_cmd(self, cmd: str) -> str:
        if self.native:
            log_dir = self.data_dir / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / "train.log"
            return f"nohup {cmd} > {log_file} 2>&1 &"
        return f"docker exec -d {self.container} {cmd}"

    async def _exec(self, cmd: str, timeout: int = 30) -> tuple[int, str, str]:
        """명령 실행 (동기 대기)"""
        full_cmd = self._build_cmd(cmd)
        logger.info(f"Executing: {full_cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            return proc.returncode, stdout.decode(), stderr.decode()
        except asyncio.TimeoutError:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)

    async def _exec_detached(self, cmd: str) -> tuple[int, str, str]:
        """명령 실행 (백그라운드 detached)"""
        full_cmd = self._build_detached_cmd(cmd)
        logger.info(f"Executing detached: {full_cmd}")
        try:
            proc = await asyncio.create_subprocess_shell(
                full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=10
            )
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
        quantization_bit: Optional[int] = 4,  # None = 양자화 없음 (Full LoRA)
        output_dir: str = "vehicle-vlm",
        flash_attn: Optional[str] = None,      # "fa2" | None (Blackwell sm_12x 미지원)
        use_mps: bool = False,                  # Apple Silicon MPS
        fp16: bool = False,                     # MPS 전용 (bf16 불가)
        cutoff_len: int = 2048,
    ) -> str:
        """학습 설정 YAML 생성 -> data/finetune/train_config.yaml"""
        config = {
            "model_name_or_path": model_name,
            "stage": "sft",
            "do_train": True,
            "finetuning_type": "lora",
            "lora_rank": lora_rank,
            "lora_target": "all",
            "dataset": "vehicle_train",
            "val_dataset": "vehicle_val",
            "dataset_dir": "/app/data" if not self.native else str(self.data_dir.resolve()),
            "template": "qwen2_vl",
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
            "gradient_checkpointing": True,   # 메모리 절약 (모든 하드웨어)
            "learning_rate": learning_rate,
            "num_train_epochs": num_epochs,
            "lr_scheduler_type": "cosine",
            "warmup_ratio": 0.1,
            "report_to": "none",
        }

        # 양자화 (bitsandbytes)
        # - CUDA: sm_80+ 및 sm_12x(Blackwell) 공식 지원 → 4-bit NF4 사용
        # - MPS: GPU 가속 커널 없음 → None으로 생략 (PR#1853 미병합)
        if quantization_bit is not None:
            config["quantization_bit"] = quantization_bit
            config["quantization_type"] = "nf4"  # NF4가 fp4보다 정확도 높음

        # 정밀도
        # - MPS: bf16 미지원(PyTorch 버그 #141864) → fp16 강제
        # - CUDA: bf16 사용 (Ampere 이상 natively 지원)
        if use_mps:
            config["use_mps_device"] = True
            config["fp16"] = True
        else:
            config["bf16"] = True

        # Flash Attention
        # - fa2: CUDA sm_80–sm_90 (A100/H100/4090 등) 지원
        # - sm_12x (Blackwell GB10 DGX Spark): 공식 미지원 → PyTorch SDPA 사용
        if flash_attn:
            config["flash_attn"] = flash_attn

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
        """학습 시작 (detached)"""
        if config_path is None:
            config_path = self.train_config_path

        # 이미 실행 중인지 확인
        status = await self.get_status()
        if status.get("is_running"):
            return {"error": "Training is already running", "status": status}

        rc, stdout, stderr = await self._exec_detached(
            f"llamafactory-cli train {config_path}"
        )

        if rc != 0 and rc != -1:
            return {"error": f"Failed to start training: {stderr}"}

        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"Training started: job_id={job_id}, native={self.native}")
        return {"job_id": job_id, "message": "Training started", "config_path": config_path}

    async def get_status(self) -> dict:
        """학습 상태 조회 (trainer_log.jsonl 파싱)"""
        # 프로세스 확인
        # [l] 트릭: pgrep이 자기를 실행한 쉘 프로세스를 매칭하는 false-positive 방지
        rc, stdout, stderr = await self._exec(
            "pgrep -f '[l]lamafactory-cli train'", timeout=5
        )
        is_running = rc == 0 and stdout.strip() != ""

        # 로그 파일 찾기 (가장 최근 output 디렉토리)
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
            rc, stdout, stderr = await self._exec(
                f"tail -1 {log_path}", timeout=5
            )
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
        """학습 중지"""
        rc, stdout, stderr = await self._exec(
            "pkill -f '[l]lamafactory-cli train'", timeout=10
        )
        if rc == 0:
            logger.info("Training stopped successfully")
            return {"message": "Training stopped"}
        else:
            return {"message": "No training process found or already stopped"}

    async def get_logs(self, tail: int = 50) -> list:
        """학습 로그 반환 (최근 N줄)"""
        rc, stdout, stderr = await self._exec(
            f"find {self.output_base} -name 'trainer_log.jsonl' -type f | sort -r | head -1",
            timeout=10,
        )
        log_path = stdout.strip()
        if not log_path:
            return []

        rc, stdout, stderr = await self._exec(
            f"tail -{tail} {log_path}", timeout=10
        )
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
        """nohup train.log (llamafactory-cli stderr) 반환 — 학습 시작 실패 시 에러 확인용"""
        log_file = self.data_dir / "logs" / "train.log"
        rc, stdout, stderr = await self._exec(
            f"tail -{tail} {log_file}", timeout=5
        )
        return stdout if rc == 0 else f"(로그 없음: {log_file})"

    async def export_model(
        self,
        checkpoint_path: str,
        output_dir: Optional[str] = None,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
    ) -> dict:
        """LoRA 어댑터 병합 (export)"""
        if output_dir is None:
            output_dir = f"{self.output_base}/merged"
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
        return {"message": "Export completed", "output_dir": output_dir}


# 전역 인스턴스
llamafactory_service = LlamaFactoryService()
