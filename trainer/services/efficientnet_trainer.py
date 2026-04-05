"""
EfficientNetV2-M 이미지 분류기 파인튜닝 트레이너

PyTorch 표준 학습 루프 — 디바이스 자동 감지:
  MPS  → Mac Apple Silicon
  CUDA → Linux/Windows NVIDIA GPU
  CPU  → 폴백

학습 데이터는 Studio의 /finetune/export-efficientnet API로 내보낸 CSV를 사용.
학습 완료 시 Identifier 서비스에 /admin/reload-efficientnet으로 핫리로드 알림.
"""
import asyncio
import json
import logging
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Optional

from trainer.config import settings

logger = logging.getLogger(__name__)

_JSONL_LOG_FILENAME = "trainer_log.jsonl"
_RAW_LOG_FILENAME = "train.log"
_SCRIPT_FILENAME = "efficientnet_train.py"
_MODEL_FILENAME = "efficientnetv2_m_finetuned.pth"
_CLASS_MAP_FILENAME = "class_mapping.json"


class EfficientNetTrainer:
    """EfficientNetV2-M 이미지 분류기 파인튜닝 (MPS/CUDA/CPU)"""

    def __init__(self):
        self.data_dir = settings.data_path
        self.output_base = str(settings.output_path)
        self.efficientnet_model_dir = Path(settings.efficientnet_model_dir)
        logger.info(f"EfficientNetTrainer init: data={self.data_dir}, output={self.output_base}")

    def _log_dir(self, output_dir: str) -> Path:
        return Path(settings.trainer_log_dir) / output_dir

    async def start_training(
        self,
        learning_rate: float = 1e-4,
        num_epochs: int = 10,
        batch_size: int = 16,
        freeze_epochs: int = 1,
        output_dir: str = "efficientnet",
        studio_url: Optional[str] = None,
        max_per_class: Optional[int] = None,
    ) -> dict:
        """EfficientNetV2-M 파인튜닝 시작 (백그라운드 프로세스)"""
        log_dir = self._log_dir(output_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # 이미 실행 중 확인
        status = await self.get_status()
        if status.get("is_running"):
            return {"error": "학습이 이미 실행 중입니다."}

        _studio_url = studio_url or settings.studio_url

        # 학습 파라미터를 스크립트에 주입
        script_path = log_dir / _SCRIPT_FILENAME
        model_out = str(self.efficientnet_model_dir / _MODEL_FILENAME)
        class_map_out = str(self.efficientnet_model_dir / _CLASS_MAP_FILENAME)
        jsonl_log = str(log_dir / _JSONL_LOG_FILENAME)
        raw_log = str(log_dir / _RAW_LOG_FILENAME)

        script_content = self._build_script(
            studio_url=_studio_url,
            learning_rate=learning_rate,
            num_epochs=num_epochs,
            batch_size=batch_size,
            freeze_epochs=freeze_epochs,
            model_out=model_out,
            class_map_out=class_map_out,
            jsonl_log=jsonl_log,
            raw_log=raw_log,
            max_per_class=max_per_class,
        )
        script_path.write_text(script_content, encoding="utf-8")

        # 기존 로그 초기화
        (log_dir / _JSONL_LOG_FILENAME).unlink(missing_ok=True)
        (log_dir / _RAW_LOG_FILENAME).unlink(missing_ok=True)

        cmd = f"nohup {sys.executable} {script_path} >> {raw_log} 2>&1 &"
        subprocess.Popen(cmd, shell=True)
        await asyncio.sleep(1)

        from datetime import datetime
        job_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        logger.info(f"EfficientNet 학습 시작: {script_path}")
        return {
            "status": "started",
            "job_id": job_id,
            "script": str(script_path),
            "log": raw_log,
            "jsonl_log": jsonl_log,
        }

    def _build_script(
        self,
        studio_url: str,
        learning_rate: float,
        num_epochs: int,
        batch_size: int,
        freeze_epochs: int,
        model_out: str,
        class_map_out: str,
        jsonl_log: str,
        raw_log: str,
        max_per_class: Optional[int] = None,
    ) -> str:
        """학습 스크립트를 파라미터와 함께 빌드."""
        max_per_class_val = max_per_class if max_per_class else "None"
        return textwrap.dedent(f"""\
            import json, csv, sys, os, time, math, random, shutil
            from pathlib import Path
            from collections import Counter, defaultdict

            import torch
            import torch.nn as nn
            import torch.nn.functional as F
            import torch.optim as optim
            from torch.utils.data import Dataset, DataLoader
            import torchvision.transforms as T
            import timm
            from PIL import Image
            import httpx

            STUDIO_URL = "{studio_url}"
            IDENTIFIER_URL = "{settings.identifier_url}"
            LEARNING_RATE = {learning_rate}
            NUM_EPOCHS = {num_epochs}
            BATCH_SIZE = {batch_size}
            FREEZE_EPOCHS = {freeze_epochs}
            MAX_PER_CLASS = {max_per_class_val}
            MODEL_OUT = "{model_out}"
            MODEL_BEST = MODEL_OUT.replace(".pth", ".best.pth")
            CLASS_MAP_OUT = "{class_map_out}"
            JSONL_LOG = "{jsonl_log}"
            RAW_LOG = "{raw_log}"
            # Identifier 컨테이너 내부 경로 (핫리로드 요청용)
            IDENTIFIER_MODEL_PATH = "{settings.identifier_efficientnet_model_path}"
            IDENTIFIER_CLASS_MAP_PATH = "{settings.identifier_class_mapping_path}"

            def log_raw(msg):
                Path(RAW_LOG).parent.mkdir(parents=True, exist_ok=True)
                with open(RAW_LOG, "a", encoding="utf-8") as f:
                    f.write(msg + "\\n")

            def log_jsonl(step, total_steps, epoch, loss, val_acc=None):
                entry = {{
                    "current_steps": step,
                    "total_steps": total_steps,
                    "epoch": round(epoch, 2),
                    "loss": round(loss, 4),
                    "percentage": round(step / total_steps * 100, 1) if total_steps else 0,
                }}
                if val_acc is not None:
                    entry["val_acc"] = round(val_acc, 2)
                Path(JSONL_LOG).parent.mkdir(parents=True, exist_ok=True)
                with open(JSONL_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\\n")

            if torch.backends.mps.is_available():
                device = torch.device("mps")
                log_raw("디바이스: MPS (Apple Silicon)")
            elif torch.cuda.is_available():
                device = torch.device("cuda")
                log_raw(f"디바이스: CUDA {{torch.cuda.get_device_name(0)}}")
            else:
                device = torch.device("cpu")
                log_raw("디바이스: CPU")

            # Studio에서 학습 데이터 내보내기
            log_raw("Studio에서 학습 데이터 내보내기 요청...")
            export_body = {{"split": 0.9}}
            if MAX_PER_CLASS is not None:
                export_body["max_per_class"] = MAX_PER_CLASS
            try:
                resp = httpx.post(
                    f"{{STUDIO_URL}}/finetune/export-efficientnet",
                    json=export_body,
                    timeout=120.0,
                )
                resp.raise_for_status()
                export_info = resp.json()
                log_raw(f"내보내기 완료: {{export_info['counts']}}")
            except Exception as e:
                log_raw(f"학습 데이터 내보내기 실패: {{e}}")
                sys.exit(1)

            train_dir = export_info["files"]["train_dir"]
            val_dir = export_info["files"].get("val_dir")
            class_mapping_path = export_info["files"]["class_mapping"]

            with open(class_mapping_path, encoding="utf-8") as f:
                class_mapping = json.load(f)
            num_classes = class_mapping["num_classes"]
            log_raw(f"클래스 수: {{num_classes}}")

            if num_classes < 2:
                log_raw("오류: 클래스가 2개 미만입니다.")
                sys.exit(1)

            class VehicleDataset(Dataset):
                def __init__(self, data_dir, transform):
                    import glob
                    self.items = []
                    chunk_files = sorted(glob.glob(os.path.join(data_dir, "chunk_*.csv")))
                    for csv_path in chunk_files:
                        with open(csv_path, encoding="utf-8") as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                p = row["image_path"]
                                if os.path.exists(p):
                                    self.items.append((p, int(row["class_idx"])))
                    self.transform = transform

                def __len__(self):
                    return len(self.items)

                def __getitem__(self, idx):
                    path, label = self.items[idx]
                    img = Image.open(path).convert("RGB")
                    return self.transform(img), label

            train_transform = T.Compose([
                T.RandomResizedCrop(480, scale=(0.7, 1.0)),
                T.RandomHorizontalFlip(),
                T.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])
            val_transform = T.Compose([
                T.Resize((480, 480)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            train_ds = VehicleDataset(train_dir, train_transform)
            val_ds = VehicleDataset(val_dir, val_transform) if val_dir and os.path.isdir(val_dir) else None

            if len(train_ds) == 0:
                log_raw("오류: 유효한 학습 이미지가 없습니다.")
                sys.exit(1)

            # macOS spawn 방식에서 num_workers > 0은 스크립트 재실행을 유발하므로 0으로 고정
            num_workers = 0 if device.type == "mps" else min(4, os.cpu_count() or 1)
            train_loader = DataLoader(
                train_ds, batch_size=BATCH_SIZE, shuffle=True,
                num_workers=num_workers, pin_memory=(device.type == "cuda"),
            )
            val_loader = DataLoader(
                val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=num_workers,
            ) if val_ds else None

            log_raw(f"학습: {{len(train_ds)}}장, 검증: {{len(val_ds) if val_ds else 0}}장")

            # 클래스 가중치 계산 (불균형 보정)
            label_counts = Counter(label for _, label in train_ds.items)
            total_samples = len(train_ds.items)
            class_weights = torch.zeros(num_classes)
            for cls_idx in range(num_classes):
                count = label_counts.get(cls_idx, 0)
                class_weights[cls_idx] = (total_samples / (num_classes * count)) ** 0.5 if count > 0 else 1.0
            class_weights = class_weights.to(device)
            log_raw(f"클래스 가중치: min={{class_weights.min():.3f}}, max={{class_weights.max():.3f}}")

            criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)

            # 모델 생성
            backbone = timm.create_model("tf_efficientnetv2_m.in21k_ft_in1k", pretrained=True, num_classes=0)
            with torch.no_grad():
                sample = torch.zeros(1, 3, 480, 480)
                feat_dim = backbone(sample).shape[-1]
            log_raw(f"특징 차원: {{feat_dim}}")

            model = nn.Sequential(
                backbone,
                nn.Dropout(0.3),
                nn.Linear(feat_dim, num_classes),
            ).to(device)

            # 기존 모델 이어 학습
            if os.path.exists(MODEL_OUT):
                log_raw(f"기존 모델 발견: {{MODEL_OUT}} — 이어 학습 시도")
                try:
                    ckpt = torch.load(MODEL_OUT, map_location=device, weights_only=True)
                    saved_classes = ckpt.get("2.weight", None)
                    if saved_classes is not None and saved_classes.shape[0] == num_classes:
                        model.load_state_dict(ckpt)
                        log_raw(f"전체 가중치 로드 완료 (클래스 수 일치: {{num_classes}})")
                    else:
                        saved_n = saved_classes.shape[0] if saved_classes is not None else "?"
                        backbone_state = {{k: v for k, v in ckpt.items() if k.startswith("0.")}}
                        model.load_state_dict(backbone_state, strict=False)
                        log_raw(f"backbone 가중치만 로드 (클래스 수 변경: {{saved_n}} → {{num_classes}}, head 재초기화)")
                except Exception as e:
                    log_raw(f"기존 모델 로드 실패, 처음부터 학습: {{e}}")
            else:
                log_raw("기존 모델 없음 — ImageNet 사전학습 가중치로 시작")

            # CUDA 환경에서만 torch.compile 적용 (MPS는 Metal shader 컴파일 오버헤드로 비효율)
            if device.type == "cuda":
                try:
                    model = torch.compile(model)
                    log_raw("torch.compile 적용 (CUDA)")
                except Exception as e:
                    log_raw(f"torch.compile 실패 (무시): {{e}}")

            steps_per_epoch = math.ceil(len(train_ds) / BATCH_SIZE)
            total_steps = NUM_EPOCHS * steps_per_epoch
            global_step = 0
            best_val_acc = 0.0
            opt = None
            scheduler = None

            for epoch in range(NUM_EPOCHS):
                # Optimizer / Scheduler 초기화 (freeze → unfreeze 전환 시 재생성)
                if epoch == 0:
                    # freeze 구간: head만 학습, LR × 10
                    for p in backbone.parameters():
                        p.requires_grad = False
                    opt = optim.AdamW(
                        [p for p in model.parameters() if p.requires_grad],
                        lr=LEARNING_RATE * 10, weight_decay=0.05,
                    )
                    scheduler = optim.lr_scheduler.OneCycleLR(
                        opt, max_lr=LEARNING_RATE * 10,
                        total_steps=total_steps, pct_start=0.1, anneal_strategy="cos",
                    )
                    log_raw(f"Epoch 1: backbone 동결, head lr={{LEARNING_RATE * 10:.2e}}")
                elif epoch == FREEZE_EPOCHS:
                    # unfreeze: backbone은 LR × 0.1, head는 LR × 1.0 (Layer-wise LR decay)
                    for p in backbone.parameters():
                        p.requires_grad = True
                    opt = optim.AdamW([
                        {{"params": list(model[2].parameters()), "lr": LEARNING_RATE,       "weight_decay": 0.05}},
                        {{"params": list(backbone.parameters()),  "lr": LEARNING_RATE * 0.1, "weight_decay": 0.05}},
                    ])
                    remaining_steps = max(1, total_steps - global_step)
                    scheduler = optim.lr_scheduler.OneCycleLR(
                        opt,
                        max_lr=[LEARNING_RATE, LEARNING_RATE * 0.1],
                        total_steps=remaining_steps, pct_start=0.1, anneal_strategy="cos",
                    )
                    log_raw(f"Epoch {{epoch+1}}: 전체 파인튜닝 시작 — head lr={{LEARNING_RATE:.2e}}, backbone lr={{LEARNING_RATE * 0.1:.2e}}")

                model.train()
                epoch_loss = 0.0
                log_interval = max(1, steps_per_epoch // 10)

                for batch_idx, (imgs, labels) in enumerate(train_loader):
                    imgs, labels = imgs.to(device), labels.to(device)
                    opt.zero_grad()
                    loss = criterion(model(imgs), labels)
                    loss.backward()
                    opt.step()
                    scheduler.step()

                    global_step += 1
                    epoch_loss += loss.item()

                    if batch_idx % log_interval == 0:
                        cur_epoch = epoch + (batch_idx + 1) / steps_per_epoch
                        log_raw(f"Ep{{epoch+1}} step{{global_step}}/{{total_steps}} loss={{loss.item():.4f}}")
                        log_jsonl(global_step, total_steps, cur_epoch, loss.item())

                avg_loss = epoch_loss / max(1, len(train_loader))
                log_raw(f"Epoch {{epoch+1}}/{{NUM_EPOCHS}} 완료 avg_loss={{avg_loss:.4f}}")

                if val_loader:
                    model.eval()
                    correct = total_val = 0
                    with torch.no_grad():
                        for imgs, labels in val_loader:
                            imgs, labels = imgs.to(device), labels.to(device)
                            preds = model(imgs).argmax(dim=1)
                            correct += (preds == labels).sum().item()
                            total_val += len(labels)
                    val_acc = correct / max(1, total_val) * 100
                    log_raw(f"검증 정확도: {{val_acc:.1f}}% ({{correct}}/{{total_val}})")
                    log_jsonl(global_step, total_steps, epoch + 1, avg_loss, val_acc=val_acc)

                    # Best model 저장
                    if val_acc > best_val_acc:
                        best_val_acc = val_acc
                        Path(MODEL_BEST).parent.mkdir(parents=True, exist_ok=True)
                        torch.save(model.state_dict(), MODEL_BEST)
                        log_raw(f"Best model 저장 (val_acc={{val_acc:.1f}}%): {{MODEL_BEST}}")

            # 최종 모델 저장: best checkpoint 우선, 없으면 마지막 epoch
            Path(MODEL_OUT).parent.mkdir(parents=True, exist_ok=True)
            if os.path.exists(MODEL_BEST):
                shutil.copy(MODEL_BEST, MODEL_OUT)
                log_raw(f"Best model → 최종 모델 복사 (best_val_acc={{best_val_acc:.1f}}%): {{MODEL_OUT}}")
            else:
                torch.save(model.state_dict(), MODEL_OUT)
                log_raw(f"모델 저장 완료 (val 없음, 마지막 epoch): {{MODEL_OUT}}")

            shutil.copy(class_mapping_path, CLASS_MAP_OUT)
            log_raw(f"class_mapping 저장: {{CLASS_MAP_OUT}}")

            # Identifier 핫리로드 (컨테이너 내부 경로 사용)
            try:
                resp = httpx.post(
                    f"{{IDENTIFIER_URL}}/admin/reload-efficientnet",
                    json={{"model_path": IDENTIFIER_MODEL_PATH, "class_mapping_path": IDENTIFIER_CLASS_MAP_PATH}},
                    timeout=30.0,
                )
                log_raw(f"Identifier 핫리로드: {{resp.status_code}}")
            except Exception as e:
                log_raw(f"Identifier 핫리로드 실패 (무시): {{e}}")

            log_raw("EfficientNetV2-M 파인튜닝 완료!")
        """)

    async def get_status(self) -> dict:
        """학습 진행 상태 조회"""
        try:
            # 프로세스 실행 여부 확인
            proc = await asyncio.create_subprocess_shell(
                f"pgrep -f '{_SCRIPT_FILENAME}' | head -1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            pid = stdout.decode().strip()
            is_running = bool(pid)
        except Exception:
            is_running = False
            pid = None

        # 로그 파싱
        log_dir = self._log_dir("efficientnet")
        jsonl_path = log_dir / _JSONL_LOG_FILENAME
        last_entry = {}
        last_val_acc = None

        if jsonl_path.exists():
            try:
                lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
                if lines:
                    last_entry = json.loads(lines[-1])
                    # val_acc는 epoch 단위로만 기록되므로 별도로 역순 탐색
                    for line in reversed(lines):
                        try:
                            entry = json.loads(line)
                            if "val_acc" in entry:
                                last_val_acc = entry["val_acc"]
                                break
                        except Exception:
                            pass
            except Exception:
                pass

        status = "running" if is_running else ("done" if last_entry else "idle")

        return {
            "is_running": is_running,
            "status": status,
            "pid": pid,
            "current_steps": last_entry.get("current_steps", 0),
            "total_steps": last_entry.get("total_steps", 0),
            "epoch": last_entry.get("epoch", 0),
            "loss": last_entry.get("loss"),
            "percentage": last_entry.get("percentage", 0),
            "val_acc": last_val_acc,
        }

    async def stop_training(self) -> dict:
        """학습 중지"""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"pkill -f '{_SCRIPT_FILENAME}'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            return {"status": "stopped"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_logs(self, tail: int = 50) -> list:
        """trainer_log.jsonl 파싱 로그 반환"""
        log_dir = self._log_dir("efficientnet")
        jsonl_path = log_dir / _JSONL_LOG_FILENAME

        if not jsonl_path.exists():
            return []

        try:
            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            entries = []
            for line in lines[-tail:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
            return entries
        except Exception:
            return []

    async def get_raw_log(self, tail: int = 100) -> str:
        """원시 학습 로그 반환"""
        log_dir = self._log_dir("efficientnet")
        raw_log_path = log_dir / _RAW_LOG_FILENAME

        if not raw_log_path.exists():
            return ""

        try:
            lines = raw_log_path.read_text(encoding="utf-8").splitlines()
            return "\n".join(lines[-tail:])
        except Exception:
            return ""

    def generate_train_yaml(self, **kwargs) -> str:
        """호환성을 위해 존재. EfficientNet 백엔드에서는 YAML 불필요."""
        return ""

    async def export_model(self, **kwargs) -> dict:
        """EfficientNet은 별도 병합 불필요. 모델 경로만 반환."""
        model_path = self.efficientnet_model_dir / _MODEL_FILENAME
        class_map_path = self.efficientnet_model_dir / _CLASS_MAP_FILENAME

        if not model_path.exists():
            return {"error": f"모델 파일이 없습니다: {model_path}"}

        return {
            "status": "ready",
            "model_path": str(model_path),
            "class_mapping_path": str(class_map_path) if class_map_path.exists() else None,
        }
