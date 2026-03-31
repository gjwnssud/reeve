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
        return Path(self.output_base) / output_dir

    def _write_train_script(self, log_dir: Path, studio_url: str) -> Path:
        """백그라운드로 실행될 학습 파이썬 스크립트를 생성."""
        script_path = log_dir / _SCRIPT_FILENAME
        model_out = str(self.efficientnet_model_dir / _MODEL_FILENAME)
        class_map_out = str(self.efficientnet_model_dir / _CLASS_MAP_FILENAME)
        jsonl_log = str(log_dir / _JSONL_LOG_FILENAME)
        raw_log = str(log_dir / _RAW_LOG_FILENAME)

        script = textwrap.dedent(f"""\
            import json, csv, sys, os, time, math, random
            from pathlib import Path

            # 라이브러리 import
            import torch
            import torch.nn as nn
            import torch.optim as optim
            from torch.utils.data import Dataset, DataLoader
            import torchvision.transforms as T
            import timm
            from PIL import Image
            import httpx

            # 학습 파라미터 (스크립트 생성 시 주입됨)
            STUDIO_URL = "{{studio_url}}"
            LEARNING_RATE = {{learning_rate}}
            NUM_EPOCHS = {{num_epochs}}
            BATCH_SIZE = {{batch_size}}
            FREEZE_EPOCHS = {{freeze_epochs}}
            MODEL_OUT = "{{model_out}}"
            CLASS_MAP_OUT = "{{class_map_out}}"
            JSONL_LOG = "{{jsonl_log}}"
            RAW_LOG = "{{raw_log}}"
            DATA_DIR = "{{data_dir}}"
            IDENTIFIER_URL = "{{identifier_url}}"

            def log_raw(msg):
                print(msg, flush=True)
                with open(RAW_LOG, "a", encoding="utf-8") as f:
                    f.write(msg + "\\n")

            def log_jsonl(step, total_steps, epoch, loss):
                entry = {{
                    "current_steps": step,
                    "total_steps": total_steps,
                    "epoch": round(epoch, 2),
                    "loss": round(loss, 4),
                    "percentage": round(step / total_steps * 100, 1) if total_steps else 0,
                }}
                with open(JSONL_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\\n")

            # 디바이스 선택
            if torch.backends.mps.is_available():
                device = torch.device("mps")
                log_raw(f"디바이스: MPS (Apple Silicon)")
            elif torch.cuda.is_available():
                device = torch.device("cuda")
                log_raw(f"디바이스: CUDA {{torch.cuda.get_device_name(0)}}")
            else:
                device = torch.device("cpu")
                log_raw("디바이스: CPU")

            # 1. Studio에서 학습 데이터 내보내기
            log_raw("Studio에서 학습 데이터 내보내기 요청...")
            try:
                resp = httpx.post(
                    f"{{STUDIO_URL}}/api/finetune/export-efficientnet",
                    json={{"split": 0.9}},
                    timeout=120.0,
                )
                resp.raise_for_status()
                export_info = resp.json()
                log_raw(f"내보내기 완료: {{export_info['counts']}}")
            except Exception as e:
                log_raw(f"학습 데이터 내보내기 실패: {{e}}")
                sys.exit(1)

            train_csv = export_info["files"]["train_csv"]
            val_csv = export_info["files"].get("val_csv")
            class_mapping_path = export_info["files"]["class_mapping"]

            with open(class_mapping_path, encoding="utf-8") as f:
                class_mapping = json.load(f)
            num_classes = class_mapping["num_classes"]
            log_raw(f"클래스 수: {{num_classes}}")

            if num_classes < 2:
                log_raw("오류: 클래스가 2개 미만입니다. 더 많은 학습 데이터를 추가하세요.")
                sys.exit(1)

            # 2. Dataset 정의
            class VehicleDataset(Dataset):
                def __init__(self, csv_path, transform):
                    self.items = []
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

            train_ds = VehicleDataset(train_csv, train_transform)
            val_ds = VehicleDataset(val_csv, val_transform) if val_csv and os.path.exists(val_csv) else None

            if len(train_ds) == 0:
                log_raw("오류: 유효한 학습 이미지가 없습니다.")
                sys.exit(1)

            train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                                      num_workers=min(4, os.cpu_count() or 1), pin_memory=(device.type == "cuda"))
            val_loader = DataLoader(val_ds, batch_size=BATCH_SIZE, shuffle=False,
                                    num_workers=min(4, os.cpu_count() or 1)) if val_ds else None

            log_raw(f"학습 데이터: {{len(train_ds)}}장, 검증: {{len(val_ds) if val_ds else 0}}장")

            # 3. 모델 생성: EfficientNetV2-M backbone + classification head
            backbone = timm.create_model("efficientnetv2_m", pretrained=True, num_classes=0)
            feat_dim = backbone(torch.zeros(1, 3, 480, 480)).shape[-1]  # 1280
            model = nn.Sequential(
                backbone,
                nn.Dropout(0.3),
                nn.Linear(feat_dim, num_classes),
            ).to(device)

            # 4. 학습 설정
            steps_per_epoch = math.ceil(len(train_ds) / BATCH_SIZE)
            total_steps = NUM_EPOCHS * steps_per_epoch
            criterion = nn.CrossEntropyLoss()

            global_step = 0

            for epoch in range(NUM_EPOCHS):
                # freeze_epochs 동안 backbone 동결
                if epoch < FREEZE_EPOCHS:
                    for p in backbone.parameters():
                        p.requires_grad = False
                    optimizer = optim.AdamW(
                        [p for p in model.parameters() if p.requires_grad],
                        lr=LEARNING_RATE * 10,
                    )
                else:
                    for p in backbone.parameters():
                        p.requires_grad = True
                    optimizer = optim.AdamW(model.parameters(), lr=LEARNING_RATE)

                scheduler = optim.lr_scheduler.CosineAnnealingLR(
                    optimizer, T_max=steps_per_epoch
                )

                model.train()
                epoch_loss = 0.0

                for batch_idx, (imgs, labels) in enumerate(train_loader):
                    imgs, labels = imgs.to(device), labels.to(device)
                    optimizer.zero_grad()
                    logits = model(imgs)
                    loss = criterion(logits, labels)
                    loss.backward()
                    optimizer.step()
                    scheduler.step()

                    global_step += 1
                    epoch_loss += loss.item()

                    if batch_idx % max(1, steps_per_epoch // 10) == 0:
                        cur_epoch = epoch + (batch_idx + 1) / steps_per_epoch
                        log_raw(f"Epoch {{epoch+1}}/{{NUM_EPOCHS}} Step {{global_step}}/{{total_steps}} loss={{loss.item():.4f}}")
                        log_jsonl(global_step, total_steps, cur_epoch, loss.item())

                avg_loss = epoch_loss / len(train_loader)
                log_raw(f"Epoch {{epoch+1}} 완료 — avg_loss={{avg_loss:.4f}}")

                # 검증
                if val_loader:
                    model.eval()
                    correct = total = 0
                    with torch.no_grad():
                        for imgs, labels in val_loader:
                            imgs, labels = imgs.to(device), labels.to(device)
                            preds = model(imgs).argmax(dim=1)
                            correct += (preds == labels).sum().item()
                            total += len(labels)
                    val_acc = correct / total * 100 if total else 0
                    log_raw(f"검증 정확도: {{val_acc:.1f}}% ({{correct}}/{{total}})")

            # 5. 모델 저장
            Path(MODEL_OUT).parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), MODEL_OUT)
            log_raw(f"모델 저장: {{MODEL_OUT}}")

            # class_mapping.json 공유 경로에 복사
            import shutil
            shutil.copy(class_mapping_path, CLASS_MAP_OUT)
            log_raw(f"class_mapping 저장: {{CLASS_MAP_OUT}}")

            # 6. Identifier 핫리로드
            try:
                resp = httpx.post(
                    f"{{IDENTIFIER_URL}}/admin/reload-efficientnet",
                    json={{"model_path": MODEL_OUT, "class_mapping_path": CLASS_MAP_OUT}},
                    timeout=30.0,
                )
                log_raw(f"Identifier 핫리로드: {{resp.status_code}}")
            except Exception as e:
                log_raw(f"Identifier 핫리로드 실패 (무시): {{e}}")

            log_raw("EfficientNetV2-M 파인튜닝 완료!")
        """)

        # 파라미터 치환
        script = script.replace("{studio_url}", studio_url)
        script = script.replace("{identifier_url}", settings.identifier_url)
        script = script.replace("{model_out}", model_out)
        script = script.replace("{class_map_out}", class_map_out)
        script = script.replace("{jsonl_log}", jsonl_log)
        script = script.replace("{raw_log}", raw_log)
        script = script.replace("{data_dir}", str(self.data_dir))

        script_path.write_text(script, encoding="utf-8")
        return script_path

    async def start_training(
        self,
        learning_rate: float = 1e-4,
        num_epochs: int = 10,
        batch_size: int = 16,
        freeze_epochs: int = 1,
        output_dir: str = "efficientnet",
        studio_url: Optional[str] = None,
    ) -> dict:
        """EfficientNetV2-M 파인튜닝 시작 (백그라운드 프로세스)"""
        log_dir = self._log_dir(output_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        # 이미 실행 중 확인
        status = await self.get_status()
        if status.get("status") == "running":
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
        )
        script_path.write_text(script_content, encoding="utf-8")

        # 기존 로그 초기화
        (log_dir / _JSONL_LOG_FILENAME).unlink(missing_ok=True)
        (log_dir / _RAW_LOG_FILENAME).unlink(missing_ok=True)

        cmd = f"nohup python3 {script_path} >> {raw_log} 2>&1 &"
        proc = subprocess.Popen(cmd, shell=True)
        await asyncio.sleep(1)

        logger.info(f"EfficientNet 학습 시작: {script_path}")
        return {
            "status": "started",
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
    ) -> str:
        """학습 스크립트를 파라미터와 함께 빌드."""
        return textwrap.dedent(f"""\
            import json, csv, sys, os, time, math, random, shutil
            from pathlib import Path

            import torch
            import torch.nn as nn
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
            MODEL_OUT = "{model_out}"
            CLASS_MAP_OUT = "{class_map_out}"
            JSONL_LOG = "{jsonl_log}"
            RAW_LOG = "{raw_log}"

            def log_raw(msg):
                print(msg, flush=True)
                Path(RAW_LOG).parent.mkdir(parents=True, exist_ok=True)
                with open(RAW_LOG, "a", encoding="utf-8") as f:
                    f.write(msg + "\\n")

            def log_jsonl(step, total_steps, epoch, loss):
                entry = {{
                    "current_steps": step,
                    "total_steps": total_steps,
                    "epoch": round(epoch, 2),
                    "loss": round(loss, 4),
                    "percentage": round(step / total_steps * 100, 1) if total_steps else 0,
                }}
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
            try:
                resp = httpx.post(
                    f"{{STUDIO_URL}}/api/finetune/export-efficientnet",
                    json={{"split": 0.9}},
                    timeout=120.0,
                )
                resp.raise_for_status()
                export_info = resp.json()
                log_raw(f"내보내기 완료: {{export_info['counts']}}")
            except Exception as e:
                log_raw(f"학습 데이터 내보내기 실패: {{e}}")
                sys.exit(1)

            train_csv = export_info["files"]["train_csv"]
            val_csv = export_info["files"].get("val_csv")
            class_mapping_path = export_info["files"]["class_mapping"]

            with open(class_mapping_path, encoding="utf-8") as f:
                class_mapping = json.load(f)
            num_classes = class_mapping["num_classes"]
            log_raw(f"클래스 수: {{num_classes}}")

            if num_classes < 2:
                log_raw("오류: 클래스가 2개 미만입니다.")
                sys.exit(1)

            class VehicleDataset(Dataset):
                def __init__(self, csv_path, transform):
                    self.items = []
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

            train_ds = VehicleDataset(train_csv, train_transform)
            val_ds = VehicleDataset(val_csv, val_transform) if val_csv and os.path.exists(val_csv) else None

            if len(train_ds) == 0:
                log_raw("오류: 유효한 학습 이미지가 없습니다.")
                sys.exit(1)

            num_workers = min(4, os.cpu_count() or 1)
            train_loader = DataLoader(
                train_ds, batch_size=BATCH_SIZE, shuffle=True,
                num_workers=num_workers, pin_memory=(device.type == "cuda"),
            )
            val_loader = DataLoader(
                val_ds, batch_size=BATCH_SIZE, shuffle=False, num_workers=num_workers,
            ) if val_ds else None

            log_raw(f"학습: {{len(train_ds)}}장, 검증: {{len(val_ds) if val_ds else 0}}장")

            # 모델 생성
            backbone = timm.create_model("efficientnetv2_m", pretrained=True, num_classes=0)
            with torch.no_grad():
                sample = torch.zeros(1, 3, 480, 480)
                feat_dim = backbone(sample).shape[-1]
            log_raw(f"특징 차원: {{feat_dim}}")

            model = nn.Sequential(
                backbone,
                nn.Dropout(0.3),
                nn.Linear(feat_dim, num_classes),
            ).to(device)

            steps_per_epoch = math.ceil(len(train_ds) / BATCH_SIZE)
            total_steps = NUM_EPOCHS * steps_per_epoch
            criterion = nn.CrossEntropyLoss()
            global_step = 0

            for epoch in range(NUM_EPOCHS):
                if epoch < FREEZE_EPOCHS:
                    for p in backbone.parameters():
                        p.requires_grad = False
                    opt = optim.AdamW(
                        [p for p in model.parameters() if p.requires_grad],
                        lr=LEARNING_RATE * 10,
                    )
                    log_raw(f"Epoch {{epoch+1}}: backbone 동결, head만 학습")
                else:
                    for p in backbone.parameters():
                        p.requires_grad = True
                    opt = optim.AdamW(model.parameters(), lr=LEARNING_RATE)
                    if epoch == FREEZE_EPOCHS:
                        log_raw(f"Epoch {{epoch+1}}: 전체 파인튜닝 시작")

                scheduler = optim.lr_scheduler.CosineAnnealingLR(opt, T_max=steps_per_epoch)
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
                    log_raw(f"검증 정확도: {{correct/max(1,total_val)*100:.1f}}% ({{correct}}/{{total_val}})")

            # 모델 저장
            Path(MODEL_OUT).parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), MODEL_OUT)
            log_raw(f"모델 저장 완료: {{MODEL_OUT}}")

            shutil.copy(class_mapping_path, CLASS_MAP_OUT)
            log_raw(f"class_mapping 저장: {{CLASS_MAP_OUT}}")

            # Identifier 핫리로드
            try:
                resp = httpx.post(
                    f"{{IDENTIFIER_URL}}/admin/reload-efficientnet",
                    json={{"model_path": MODEL_OUT, "class_mapping_path": CLASS_MAP_OUT}},
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
        log_dir = Path(self.output_base) / "efficientnet"
        jsonl_path = log_dir / _JSONL_LOG_FILENAME
        last_entry = {}

        if jsonl_path.exists():
            try:
                lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
                if lines:
                    last_entry = json.loads(lines[-1])
            except Exception:
                pass

        status = "running" if is_running else ("done" if last_entry else "idle")

        return {
            "status": status,
            "pid": pid,
            "current_steps": last_entry.get("current_steps", 0),
            "total_steps": last_entry.get("total_steps", 0),
            "epoch": last_entry.get("epoch", 0),
            "loss": last_entry.get("loss"),
            "percentage": last_entry.get("percentage", 0),
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
        log_dir = Path(self.output_base) / "efficientnet"
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
        log_dir = Path(self.output_base) / "efficientnet"
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
