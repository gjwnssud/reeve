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

    def _save_current_output_dir(self, output_dir: str) -> None:
        try:
            (Path(settings.trainer_log_dir) / "current.txt").write_text(output_dir, encoding="utf-8")
        except Exception:
            pass

    def _load_current_output_dir(self) -> str:
        try:
            p = Path(settings.trainer_log_dir) / "current.txt"
            return p.read_text(encoding="utf-8").strip() if p.exists() else "efficientnet"
        except Exception:
            return "efficientnet"

    async def start_training(
        self,
        learning_rate: float = 1e-4,
        num_epochs: int = 20,
        batch_size: int = 16,
        freeze_epochs: int = 3,
        output_dir: str = "efficientnet",
        studio_url: Optional[str] = None,
        max_per_class: Optional[int] = None,
        min_per_class: Optional[int] = None,
        gradient_accumulation: int = 1,
        use_ema: bool = False,
        use_mixup: bool = False,
        num_workers: Optional[int] = None,
        early_stopping_patience: int = 7,
    ) -> dict:
        """EfficientNetV2-M 파인튜닝 시작 (백그라운드 프로세스)"""
        self._save_current_output_dir(output_dir)
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
            min_per_class=min_per_class,
            gradient_accumulation=gradient_accumulation,
            use_ema=use_ema,
            use_mixup=use_mixup,
            num_workers=num_workers,
            early_stopping_patience=early_stopping_patience,
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
        min_per_class: Optional[int] = None,
        gradient_accumulation: int = 1,
        use_ema: bool = False,
        use_mixup: bool = False,
        num_workers: Optional[int] = None,
        early_stopping_patience: int = 7,
    ) -> str:
        """학습 스크립트를 파라미터와 함께 빌드."""
        max_per_class_val = max_per_class if max_per_class else "None"
        min_per_class_val = min_per_class if min_per_class else "None"
        num_workers_val = num_workers if num_workers is not None else "None"
        return textwrap.dedent(f"""\
            import json, csv, sys, os, time, math, random, shutil, copy, contextlib
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

            # ── 하이퍼파라미터 ──────────────────────────────────────
            STUDIO_URL = "{studio_url}"
            IDENTIFIER_URL = "{settings.identifier_url}"
            LEARNING_RATE = {learning_rate}
            NUM_EPOCHS = {num_epochs}
            BATCH_SIZE = {batch_size}
            FREEZE_EPOCHS = {freeze_epochs}
            MAX_PER_CLASS = {max_per_class_val}
            MIN_PER_CLASS = {min_per_class_val}
            GRAD_ACCUM = {gradient_accumulation}
            USE_EMA = {use_ema}
            USE_MIXUP = {use_mixup}
            NUM_WORKERS_OVERRIDE = {num_workers_val}
            PATIENCE = {early_stopping_patience}
            MODEL_OUT = "{model_out}"
            MODEL_BEST = MODEL_OUT.replace(".pth", ".best.pth")
            CLASS_MAP_OUT = "{class_map_out}"
            JSONL_LOG = "{jsonl_log}"
            RAW_LOG = "{raw_log}"
            IDENTIFIER_MODEL_PATH = "{settings.identifier_efficientnet_model_path}"
            IDENTIFIER_CLASS_MAP_PATH = "{settings.identifier_class_mapping_path}"

            # ── 로깅 ──────────────────────────────────────────────
            def log_raw(msg):
                Path(RAW_LOG).parent.mkdir(parents=True, exist_ok=True)
                with open(RAW_LOG, "a", encoding="utf-8") as f:
                    f.write(msg + "\\n")

            def log_jsonl(step, total_steps, epoch, loss, val_acc=None, worst_classes=None):
                entry = {{
                    "current_steps": step,
                    "total_steps": total_steps,
                    "epoch": round(epoch, 2),
                    "loss": round(loss, 4),
                    "percentage": round(step / total_steps * 100, 1) if total_steps else 0,
                }}
                if val_acc is not None:
                    entry["val_acc"] = round(val_acc, 2)
                if worst_classes is not None:
                    entry["worst_classes"] = worst_classes
                Path(JSONL_LOG).parent.mkdir(parents=True, exist_ok=True)
                with open(JSONL_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\\n")

            # ── EMA 클래스 ──────────────────────────────────────────
            class EMAModel:
                def __init__(self, model, decay=0.999):
                    self.module = copy.deepcopy(model)
                    self.module.eval()
                    self.decay = decay

                @torch.no_grad()
                def update(self, model):
                    for ema_p, p in zip(self.module.parameters(), model.parameters()):
                        ema_p.data.mul_(self.decay).add_(p.data, alpha=1 - self.decay)

                def state_dict(self):
                    return self.module.state_dict()

            # ── 디바이스 감지 ────────────────────────────────────────
            cc_major = 0
            vram_gb = 0
            if torch.backends.mps.is_available():
                device = torch.device("mps")
                log_raw("디바이스: MPS (Apple Silicon)")
            elif torch.cuda.is_available():
                device = torch.device("cuda")
                cc_major, _ = torch.cuda.get_device_capability(0)
                vram_gb = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                log_raw(f"디바이스: CUDA {{torch.cuda.get_device_name(0)}} ({{vram_gb:.0f}} GB, sm_{{cc_major}})")
            else:
                device = torch.device("cpu")
                log_raw("디바이스: CPU")

            # ── Mixed Precision 설정 ────────────────────────────────
            if device.type == "cuda":
                if cc_major >= 8 and torch.cuda.is_bf16_supported():
                    autocast_ctx = lambda: torch.autocast("cuda", dtype=torch.bfloat16)
                    scaler = None
                    log_raw("Mixed Precision: bf16 (GradScaler 불필요)")
                else:
                    autocast_ctx = lambda: torch.autocast("cuda", dtype=torch.float16)
                    scaler = torch.amp.GradScaler()
                    log_raw("Mixed Precision: fp16 + GradScaler")
            elif device.type == "mps":
                try:
                    _test_ctx = torch.autocast("mps", dtype=torch.float16)
                    autocast_ctx = lambda: torch.autocast("mps", dtype=torch.float16)
                    scaler = None
                    log_raw("Mixed Precision: MPS fp16 autocast")
                except Exception:
                    autocast_ctx = lambda: contextlib.nullcontext()
                    scaler = None
                    log_raw("Mixed Precision: 미지원, fp32 폴백")
            else:
                autocast_ctx = lambda: contextlib.nullcontext()
                scaler = None
                log_raw("Mixed Precision: 없음 (CPU fp32)")

            # ── Studio에서 학습 데이터 내보내기 ─────────────────────
            log_raw("Studio에서 학습 데이터 내보내기 요청...")
            export_body = {{"split": 0.9}}
            if MAX_PER_CLASS is not None:
                export_body["max_per_class"] = MAX_PER_CLASS
            if MIN_PER_CLASS is not None:
                export_body["min_per_class"] = MIN_PER_CLASS
            try:
                resp = httpx.post(
                    f"{{STUDIO_URL}}/finetune/export-efficientnet",
                    json=export_body,
                    timeout=120.0,
                    verify=False,
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

            # ── Dataset ──────────────────────────────────────────────
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

            # ── Data Augmentation (강화) ─────────────────────────────
            train_transform = T.Compose([
                T.RandomResizedCrop(480, scale=(0.6, 1.0), interpolation=T.InterpolationMode.BICUBIC),
                T.RandomHorizontalFlip(),
                T.TrivialAugmentWide(),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
                T.RandomErasing(p=0.25, scale=(0.02, 0.15)),
            ])
            val_transform = T.Compose([
                T.Resize(512, interpolation=T.InterpolationMode.BICUBIC),
                T.CenterCrop(480),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            train_ds = VehicleDataset(train_dir, train_transform)
            val_ds = VehicleDataset(val_dir, val_transform) if val_dir and os.path.isdir(val_dir) else None

            if len(train_ds) == 0:
                log_raw("오류: 유효한 학습 이미지가 없습니다.")
                sys.exit(1)

            # ── 모델 생성 (DataLoader 전 — worker 시그널 간섭 방지) ──
            backbone = timm.create_model("tf_efficientnetv2_m.in21k_ft_in1k", pretrained=True, num_classes=0)
            with torch.no_grad():
                sample = torch.zeros(1, 3, 480, 480)
                feat_dim = backbone(sample).shape[-1]
            log_raw(f"특징 차원: {{feat_dim}}")

            # ── CutMix/MixUp (배치 레벨) ─────────────────────────────
            cutmix_or_mixup = None
            if USE_MIXUP:
                try:
                    from torchvision.transforms import v2
                    cutmix_or_mixup = v2.RandomChoice([
                        v2.CutMix(num_classes=num_classes),
                        v2.MixUp(num_classes=num_classes),
                    ])
                    log_raw("CutMix/MixUp 활성화")
                except Exception as e:
                    log_raw(f"CutMix/MixUp 초기화 실패 (비활성): {{e}}")

            # ── DataLoader 최적화 ────────────────────────────────────
            if device.type == "mps":
                _num_workers = NUM_WORKERS_OVERRIDE if NUM_WORKERS_OVERRIDE is not None else 2
                worker_kwargs = {{"multiprocessing_context": "fork", "persistent_workers": True}} if _num_workers > 0 else {{}}
            elif device.type == "cuda":
                _num_workers = NUM_WORKERS_OVERRIDE if NUM_WORKERS_OVERRIDE is not None else min(8, os.cpu_count() or 1)
                worker_kwargs = {{"pin_memory": True, "persistent_workers": True, "prefetch_factor": 2}} if _num_workers > 0 else {{"pin_memory": True}}
            else:
                _num_workers = 0
                worker_kwargs = {{}}

            try:
                train_loader = DataLoader(
                    train_ds, batch_size=BATCH_SIZE, shuffle=True,
                    num_workers=_num_workers, **worker_kwargs,
                )
                # 테스트 이터레이션으로 멀티프로세스 정상 작동 확인
                if _num_workers > 0:
                    _test_iter = iter(train_loader)
                    next(_test_iter)
                    del _test_iter
            except Exception as e:
                log_raw(f"DataLoader 멀티프로세스 실패 (num_workers=0 폴백): {{e}}")
                _num_workers = 0
                worker_kwargs = {{}}
                train_loader = DataLoader(
                    train_ds, batch_size=BATCH_SIZE, shuffle=True,
                    num_workers=0,
                )

            val_loader = None
            if val_ds:
                val_worker_kwargs = {{"pin_memory": True}} if device.type == "cuda" else ({{"multiprocessing_context": "fork"}} if device.type == "mps" and _num_workers > 0 else {{}})
                val_loader = DataLoader(
                    val_ds, batch_size=BATCH_SIZE, shuffle=False,
                    num_workers=min(_num_workers, 2),
                    **val_worker_kwargs,
                )

            log_raw(f"학습: {{len(train_ds)}}장, 검증: {{len(val_ds) if val_ds else 0}}장, workers={{_num_workers}}")

            # ── 클래스 가중치 (불균형 보정) ──────────────────────────
            label_counts = Counter(label for _, label in train_ds.items)
            total_samples = len(train_ds.items)
            class_weights = torch.zeros(num_classes)
            for cls_idx in range(num_classes):
                count = label_counts.get(cls_idx, 0)
                class_weights[cls_idx] = (total_samples / (num_classes * count)) ** 0.5 if count > 0 else 1.0
            class_weights = class_weights.to(device)
            log_raw(f"클래스 가중치: min={{class_weights.min():.3f}}, max={{class_weights.max():.3f}}")

            criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=0.1)

            model = nn.Sequential(
                backbone,
                nn.Dropout(0.3),
                nn.Linear(feat_dim, num_classes),
            ).to(device)

            # ── channels_last 메모리 포맷 (CUDA/MPS 컨볼루션 최적화) ─
            use_channels_last = device.type in ("cuda", "mps")
            if use_channels_last:
                model = model.to(memory_format=torch.channels_last)
                log_raw("channels_last 메모리 포맷 적용")

            # ── 기존 모델 이어 학습 ──────────────────────────────────
            head_reinitialized = False
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
                        head_reinitialized = True
                except Exception as e:
                    log_raw(f"기존 모델 로드 실패, 처음부터 학습: {{e}}")
                    head_reinitialized = True
            else:
                log_raw("기존 모델 없음 — ImageNet 사전학습 가중치로 시작")
                head_reinitialized = True

            # head 재초기화 시 freeze_epochs=0이면 자동 보정
            if head_reinitialized and FREEZE_EPOCHS == 0:
                FREEZE_EPOCHS = 1
                log_raw("head 재초기화 감지 → freeze_epochs 자동 보정: 1")

            # ── torch.compile (CUDA 전용) ─────────────────────────────
            # sm_12x(Blackwell): NGC 25.03 Triton이 LLVM 서브프로세스를 C 레벨에서 crash
            # suppress_errors로는 못 막음 → sm_120+ 에서는 완전 비활성
            if device.type == "cuda":
                _major, _minor = torch.cuda.get_device_capability(device)
                _sm_cap = _major * 10 + _minor
                if _sm_cap >= 120:
                    log_raw(f"torch.compile 비활성 (sm_{{_sm_cap}}, Blackwell — NGC Triton 미지원)")
                else:
                    import torch._dynamo
                    torch._dynamo.config.suppress_errors = True
                    compile_mode = "reduce-overhead"
                    try:
                        model = torch.compile(model, mode=compile_mode)
                        log_raw(f"torch.compile 적용 (mode={{compile_mode}})")
                    except Exception as e:
                        log_raw(f"torch.compile 실패 (무시): {{e}}")

            # ── EMA 초기화 ───────────────────────────────────────────
            ema = EMAModel(model) if USE_EMA else None
            if ema:
                log_raw("EMA 활성화 (decay=0.999)")

            # ── 학습 스케줄 계산 (Gradient Accumulation 반영) ────────
            steps_per_epoch = math.ceil(len(train_ds) / BATCH_SIZE)
            optim_steps_per_epoch = math.ceil(steps_per_epoch / GRAD_ACCUM)
            total_optim_steps = NUM_EPOCHS * optim_steps_per_epoch
            total_steps = NUM_EPOCHS * steps_per_epoch  # 로깅용 전체 스텝
            global_step = 0
            optim_step = 0
            best_val_acc = 0.0
            no_improve = 0
            opt = None
            scheduler = None

            log_raw(f"Gradient Accumulation: {{GRAD_ACCUM}} (effective batch={{BATCH_SIZE * GRAD_ACCUM}})")
            log_raw(f"총 optim steps: {{total_optim_steps}} (steps/epoch={{steps_per_epoch}}, optim_steps/epoch={{optim_steps_per_epoch}})")

            for epoch in range(NUM_EPOCHS):
                # ── Optimizer / Scheduler 초기화 (freeze → unfreeze 전환 시 재생성) ──
                if epoch == 0 and FREEZE_EPOCHS > 0:
                    for p in backbone.parameters():
                        p.requires_grad = False
                    opt = optim.AdamW(
                        [p for p in model.parameters() if p.requires_grad],
                        lr=LEARNING_RATE * 10, weight_decay=0.05,
                    )
                    scheduler = optim.lr_scheduler.OneCycleLR(
                        opt, max_lr=LEARNING_RATE * 10,
                        total_steps=total_optim_steps, pct_start=0.1, anneal_strategy="cos",
                    )
                    log_raw(f"Epoch 1: backbone 동결, head lr={{LEARNING_RATE * 10:.2e}}")
                elif epoch == 0 and FREEZE_EPOCHS == 0:
                    for p in backbone.parameters():
                        p.requires_grad = True
                    opt = optim.AdamW([
                        {{"params": list(model[2].parameters()), "lr": LEARNING_RATE,       "weight_decay": 0.05}},
                        {{"params": list(backbone.parameters()),  "lr": LEARNING_RATE * 0.1, "weight_decay": 0.05}},
                    ])
                    scheduler = optim.lr_scheduler.OneCycleLR(
                        opt,
                        max_lr=[LEARNING_RATE, LEARNING_RATE * 0.1],
                        total_steps=total_optim_steps, pct_start=0.1, anneal_strategy="cos",
                    )
                    log_raw(f"Epoch 1: freeze 없이 전체 파인튜닝 — head lr={{LEARNING_RATE:.2e}}, backbone lr={{LEARNING_RATE * 0.1:.2e}}")
                elif epoch == FREEZE_EPOCHS:
                    for p in backbone.parameters():
                        p.requires_grad = True
                    opt = optim.AdamW([
                        {{"params": list(model[2].parameters()), "lr": LEARNING_RATE,       "weight_decay": 0.05}},
                        {{"params": list(backbone.parameters()),  "lr": LEARNING_RATE * 0.1, "weight_decay": 0.05}},
                    ])
                    remaining_optim_steps = max(1, total_optim_steps - optim_step)
                    scheduler = optim.lr_scheduler.OneCycleLR(
                        opt,
                        max_lr=[LEARNING_RATE, LEARNING_RATE * 0.1],
                        total_steps=remaining_optim_steps, pct_start=0.1, anneal_strategy="cos",
                    )
                    log_raw(f"Epoch {{epoch+1}}: 전체 파인튜닝 시작 — head lr={{LEARNING_RATE:.2e}}, backbone lr={{LEARNING_RATE * 0.1:.2e}}")

                model.train()
                epoch_loss = 0.0
                log_interval = max(1, steps_per_epoch // 10)
                opt.zero_grad()

                for batch_idx, (imgs, labels) in enumerate(train_loader):
                    if use_channels_last:
                        imgs = imgs.to(device, memory_format=torch.channels_last)
                    else:
                        imgs = imgs.to(device)
                    labels = labels.to(device)

                    # CutMix/MixUp 적용
                    if cutmix_or_mixup is not None:
                        imgs, labels = cutmix_or_mixup(imgs, labels)

                    with autocast_ctx():
                        loss = criterion(model(imgs), labels) / GRAD_ACCUM

                    if scaler is not None:
                        scaler.scale(loss).backward()
                        if (batch_idx + 1) % GRAD_ACCUM == 0 or (batch_idx + 1) == steps_per_epoch:
                            scaler.unscale_(opt)
                            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                            scaler.step(opt)
                            scaler.update()
                            opt.zero_grad()
                            scheduler.step()
                            optim_step += 1
                            if ema:
                                ema.update(model)
                    else:
                        loss.backward()
                        if (batch_idx + 1) % GRAD_ACCUM == 0 or (batch_idx + 1) == steps_per_epoch:
                            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                            opt.step()
                            opt.zero_grad()
                            scheduler.step()
                            optim_step += 1
                            if ema:
                                ema.update(model)

                    global_step += 1
                    epoch_loss += loss.item() * GRAD_ACCUM

                    if batch_idx % log_interval == 0:
                        cur_epoch = epoch + (batch_idx + 1) / steps_per_epoch
                        log_raw(f"Ep{{epoch+1}} step{{global_step}}/{{total_steps}} loss={{loss.item() * GRAD_ACCUM:.4f}}")
                        log_jsonl(global_step, total_steps, cur_epoch, loss.item() * GRAD_ACCUM)

                avg_loss = epoch_loss / max(1, len(train_loader))
                log_raw(f"Epoch {{epoch+1}}/{{NUM_EPOCHS}} 완료 avg_loss={{avg_loss:.4f}}")

                # ── 검증 (EMA 모델 사용) ─────────────────────────────
                if val_loader:
                    eval_model = ema.module if ema else model
                    eval_model.eval()
                    correct = total_val = 0
                    class_correct = defaultdict(int)
                    class_total = defaultdict(int)

                    with torch.no_grad():
                        for imgs, labels in val_loader:
                            if use_channels_last:
                                imgs = imgs.to(device, memory_format=torch.channels_last)
                            else:
                                imgs = imgs.to(device)
                            labels = labels.to(device)
                            preds = eval_model(imgs).argmax(dim=1)
                            correct += (preds == labels).sum().item()
                            total_val += len(labels)
                            for p, l in zip(preds, labels):
                                class_total[l.item()] += 1
                                if p == l:
                                    class_correct[l.item()] += 1

                    val_acc = correct / max(1, total_val) * 100
                    per_class_acc = {{c: round(class_correct[c] / class_total[c] * 100, 1) for c in class_total if class_total[c] > 0}}
                    worst_5 = sorted(per_class_acc.items(), key=lambda x: x[1])[:5]

                    log_raw(f"검증 정확도: {{val_acc:.1f}}% ({{correct}}/{{total_val}})")
                    log_raw(f"최저 5개 클래스: {{worst_5}}")
                    worst_classes_log = [{{"class": c, "acc": a}} for c, a in worst_5]
                    log_jsonl(global_step, total_steps, epoch + 1, avg_loss,
                              val_acc=val_acc, worst_classes=worst_classes_log)

                    # Best model 저장
                    if val_acc > best_val_acc:
                        best_val_acc = val_acc
                        no_improve = 0
                        Path(MODEL_BEST).parent.mkdir(parents=True, exist_ok=True)
                        save_state = ema.state_dict() if ema else model.state_dict()
                        torch.save(save_state, MODEL_BEST)
                        log_raw(f"Best model 저장 (val_acc={{val_acc:.1f}}%): {{MODEL_BEST}}")
                    else:
                        no_improve += 1
                        log_raw(f"개선 없음 ({{no_improve}}/{{PATIENCE}})")
                        if PATIENCE > 0 and no_improve >= PATIENCE:
                            log_raw(f"Early stopping: {{PATIENCE}} epoch 동안 개선 없음")
                            break

            # ── 최종 모델 저장 ────────────────────────────────────────
            Path(MODEL_OUT).parent.mkdir(parents=True, exist_ok=True)
            if os.path.exists(MODEL_BEST):
                shutil.copy(MODEL_BEST, MODEL_OUT)
                log_raw(f"Best model → 최종 모델 복사 (best_val_acc={{best_val_acc:.1f}}%): {{MODEL_OUT}}")
            else:
                save_state = ema.state_dict() if ema else model.state_dict()
                torch.save(save_state, MODEL_OUT)
                log_raw(f"모델 저장 완료 (val 없음, 마지막 epoch): {{MODEL_OUT}}")

            shutil.copy(class_mapping_path, CLASS_MAP_OUT)
            log_raw(f"class_mapping 저장: {{CLASS_MAP_OUT}}")

            # ── Identifier 핫리로드 ──────────────────────────────────
            try:
                resp = httpx.post(
                    f"{{IDENTIFIER_URL}}/admin/reload-efficientnet",
                    json={{"model_path": IDENTIFIER_MODEL_PATH, "class_mapping_path": IDENTIFIER_CLASS_MAP_PATH}},
                    timeout=30.0,
                    verify=False,
                )
                log_raw(f"Identifier 핫리로드: {{resp.status_code}}")
            except Exception as e:
                log_raw(f"Identifier 핫리로드 실패 (무시): {{e}}")

            log_raw("EfficientNetV2-M 파인튜닝 완료!")
        """)

    async def get_status(self) -> dict:
        """학습 진행 상태 조회"""
        import time
        pid = None
        is_running = False
        try:
            proc = await asyncio.create_subprocess_shell(
                f"pgrep -f '{_SCRIPT_FILENAME}' | head -1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            pid = stdout.decode().strip()
            if pid:
                # 좀비 프로세스 제외 (ps stat 확인)
                ps_proc = await asyncio.create_subprocess_shell(
                    f"ps -p {pid} -o stat= 2>/dev/null",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                ps_out, _ = await asyncio.wait_for(ps_proc.communicate(), timeout=3)
                stat = ps_out.decode().strip()
                is_running = bool(stat) and "Z" not in stat
        except Exception:
            is_running = False
            pid = None

        # 로그 파싱
        log_dir = self._log_dir(self._load_current_output_dir())
        jsonl_path = log_dir / _JSONL_LOG_FILENAME
        raw_log_path = log_dir / _RAW_LOG_FILENAME
        last_entry = {}
        last_val_acc = None

        if jsonl_path.exists():
            try:
                lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
                if lines:
                    last_entry = json.loads(lines[-1])
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

        # 프로세스가 살아있지만 120초 이상 JSONL 로그가 없으면 → failed
        if is_running and not last_entry and raw_log_path.exists():
            try:
                age = time.time() - raw_log_path.stat().st_mtime
                if age > 120:
                    is_running = False
            except Exception:
                pass

        if is_running:
            status = "running"
        elif last_entry:
            status = "done"
        else:
            status = "idle"

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
        """학습 중지 (SIGTERM 후 SIGKILL)"""
        try:
            proc = await asyncio.create_subprocess_shell(
                f"pkill -f '{_SCRIPT_FILENAME}' ; sleep 2 ; pkill -9 -f '{_SCRIPT_FILENAME}' ; true",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=15)
            return {"status": "stopped"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def get_logs(self, tail: int = 50) -> list:
        """trainer_log.jsonl 파싱 로그 반환"""
        log_dir = self._log_dir(self._load_current_output_dir())
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
        log_dir = self._log_dir(self._load_current_output_dir())
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
