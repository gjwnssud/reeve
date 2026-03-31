"""
EfficientNetV2-M 분류기 + 특징 추출기

두 가지 동작 모드:
1. 부트스트랩 모드 (model_path=None 또는 파일 없음):
   - pretrained EfficientNetV2-M (num_classes=0) 로드
   - has_classification_head = False
   - classify() 호출 불가, extract_features()만 사용 가능

2. 파인튜닝 모드 (model_path 유효):
   - 파인튜닝된 전체 모델 (backbone + Dropout + Linear) 로드
   - has_classification_head = True
   - classify()로 직접 분류 가능
"""
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import timm
import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision.transforms as T
from PIL import Image

logger = logging.getLogger(__name__)

FEATURE_DIM = 1280
IMAGE_SIZE = 480


def _select_device() -> torch.device:
    """사용 가능한 최적 디바이스 선택"""
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


class EfficientNetClassifier:
    """EfficientNetV2-M 기반 차량 분류기 + 특징 추출기"""

    def __init__(
        self,
        model_path: Optional[str] = None,
        class_mapping_path: Optional[str] = None,
        device: Optional[str] = None,
    ):
        self._lock = threading.Lock()
        self._device = torch.device(device) if device else _select_device()
        self._transform = T.Compose([
            T.Resize((IMAGE_SIZE, IMAGE_SIZE)),
            T.ToTensor(),
            T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ])

        self.has_classification_head: bool = False
        self.num_classes: int = 0
        self.class_mapping: Dict = {}
        self._model: nn.Module = None

        self._load(model_path, class_mapping_path)

    def _load(self, model_path: Optional[str], class_mapping_path: Optional[str]) -> None:
        """모델 로드 (내부 전용). Lock 없이 호출됨."""
        model_file = Path(model_path) if model_path else None
        mapping_file = Path(class_mapping_path) if class_mapping_path else None

        if model_file and model_file.exists() and mapping_file and mapping_file.exists():
            # 파인튜닝 모드: 전체 모델 (backbone + head) 로드
            try:
                with open(mapping_file, encoding="utf-8") as f:
                    class_mapping = json.load(f)
                num_classes = class_mapping["num_classes"]

                backbone = timm.create_model("efficientnetv2_m", pretrained=False, num_classes=0)
                model = nn.Sequential(
                    backbone,
                    nn.Dropout(0.3),
                    nn.Linear(FEATURE_DIM, num_classes),
                )
                state = torch.load(model_path, map_location=self._device, weights_only=True)
                model.load_state_dict(state)
                model.eval()
                model.to(self._device)

                self._model = model
                self._backbone = backbone
                self.class_mapping = class_mapping
                self.num_classes = num_classes
                self.has_classification_head = True

                logger.info(
                    f"EfficientNetV2-M 파인튜닝 모델 로드: {model_path} "
                    f"(classes={num_classes}, device={self._device})"
                )
            except Exception as e:
                logger.error(f"파인튜닝 모델 로드 실패, 사전학습 모드로 폴백: {e}")
                self._load_pretrained()
        else:
            if model_path and not (model_file and model_file.exists()):
                logger.info(f"모델 파일 없음 ({model_path}), 사전학습 부트스트랩 모드로 시작")
            self._load_pretrained()

    def _load_pretrained(self) -> None:
        """사전학습 EfficientNetV2-M (특징 추출기 전용)"""
        backbone = timm.create_model("efficientnetv2_m", pretrained=True, num_classes=0)
        backbone.eval()
        backbone.to(self._device)
        self._model = backbone
        self._backbone = backbone
        self.has_classification_head = False
        self.num_classes = 0
        self.class_mapping = {}
        logger.info(f"EfficientNetV2-M 사전학습 모드 (특징 추출만, device={self._device})")

    def reload(self, model_path: str, class_mapping_path: str) -> None:
        """파인튜닝 완료 후 핫리로드 (thread-safe)"""
        with self._lock:
            logger.info(f"EfficientNetV2-M 핫리로드 시작: {model_path}")
            self._load(model_path, class_mapping_path)
            logger.info("EfficientNetV2-M 핫리로드 완료")

    def extract_features(self, images: List[Image.Image]) -> np.ndarray:
        """
        이미지 리스트 → L2 정규화된 1280d 특징 벡터 배열 반환.
        파인튜닝 모드에서도 backbone만 사용.

        Returns:
            np.ndarray shape (N, 1280), float32
        """
        if not images:
            return np.zeros((0, FEATURE_DIM), dtype=np.float32)

        with self._lock:
            tensors = torch.stack([self._transform(img) for img in images]).to(self._device)
            with torch.no_grad():
                if self.has_classification_head:
                    # backbone (첫 번째 레이어)만 사용
                    feats = self._backbone(tensors)
                else:
                    feats = self._model(tensors)
                feats = F.normalize(feats, dim=-1)
            return feats.cpu().numpy().astype(np.float32)

    def classify(self, images: List[Image.Image]) -> List[Tuple[int, float]]:
        """
        이미지 분류 → [(class_idx, softmax_confidence), ...]

        Raises:
            RuntimeError: 분류 헤드가 없는 경우 (부트스트랩 모드)
        """
        if not self.has_classification_head:
            raise RuntimeError(
                "분류 헤드가 없습니다. EfficientNetV2-M 파인튜닝 후 핫리로드를 실행하세요."
            )
        if not images:
            return []

        with self._lock:
            tensors = torch.stack([self._transform(img) for img in images]).to(self._device)
            with torch.no_grad():
                logits = self._model(tensors)
                probs = torch.softmax(logits, dim=-1)
                top_probs, top_idxs = probs.max(dim=-1)

            results = []
            for idx, prob in zip(top_idxs.cpu().tolist(), top_probs.cpu().tolist()):
                results.append((int(idx), float(prob)))
            return results

    def health_check(self) -> dict:
        """모델 상태 정보 반환"""
        return {
            "model": "efficientnetv2_m",
            "has_classification_head": self.has_classification_head,
            "num_classes": self.num_classes,
            "feature_dim": FEATURE_DIM,
            "device": str(self._device),
        }
