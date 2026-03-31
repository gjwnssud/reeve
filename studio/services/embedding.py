"""
임베딩 생성 서비스
EfficientNetV2-M 모델을 사용한 이미지 벡터화
"""
import logging
from typing import List

import timm
import torch
import torch.nn.functional as F
import torchvision.transforms as T
from PIL import Image

from studio.config import settings

logger = logging.getLogger(__name__)

EFFICIENTNET_DIM = 1280


class EmbeddingService:
    """이미지 임베딩 생성 서비스 (EfficientNetV2-M)"""

    def __init__(self):
        """임베딩 모델 초기화"""
        try:
            self.model = timm.create_model(
                'efficientnetv2_m', pretrained=True, num_classes=0
            )
            self.model.eval()
            self.model.to(settings.embedding_device)

            self.transform = T.Compose([
                T.Resize((480, 480)),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406],
                            std=[0.229, 0.224, 0.225]),
            ])

            logger.info(f"Image embedding model loaded: efficientnetv2_m (device={settings.embedding_device})")

        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            raise

    def _embed(self, tensor: torch.Tensor) -> "np.ndarray":
        with torch.no_grad():
            vecs = self.model(tensor)
        return F.normalize(vecs, dim=-1).cpu().numpy()

    def encode_image(self, image_path: str) -> List[float]:
        """
        이미지를 벡터로 변환

        Args:
            image_path: 이미지 파일 경로

        Returns:
            임베딩 벡터
        """
        try:
            image = Image.open(image_path).convert("RGB")
            t = self.transform(image).unsqueeze(0).to(settings.embedding_device)
            return self._embed(t)[0].tolist()

        except Exception as e:
            logger.error(f"Failed to encode image {image_path}: {e}")
            raise

    def encode_batch_images(self, image_paths: List[str]) -> List[List[float]]:
        """
        여러 이미지를 배치로 벡터화

        Args:
            image_paths: 이미지 경로 리스트

        Returns:
            임베딩 벡터 리스트
        """
        try:
            tensors = [
                self.transform(Image.open(p).convert("RGB"))
                for p in image_paths
            ]
            batch = torch.stack(tensors).to(settings.embedding_device)
            return self._embed(batch).tolist()

        except Exception as e:
            logger.error(f"Failed to encode batch images: {e}")
            raise

    def compute_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        두 임베딩 간 코사인 유사도 계산

        Args:
            embedding1: 임베딩 벡터 1
            embedding2: 임베딩 벡터 2

        Returns:
            코사인 유사도 (0-1)
        """
        try:
            import numpy as np

            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

            return float(similarity)

        except Exception as e:
            logger.error(f"Failed to compute similarity: {e}")
            return 0.0

    def get_model_info(self) -> dict:
        """임베딩 모델 정보"""
        return {
            "image_model": "efficientnetv2_m",
            "embedding_dimension": EFFICIENTNET_DIM,
            "device": settings.embedding_device
        }


# 전역 인스턴스
embedding_service = EmbeddingService()
