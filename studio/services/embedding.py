"""
임베딩 생성 서비스
CLIP 모델을 사용한 이미지 벡터화
"""
import logging
from typing import List
from sentence_transformers import SentenceTransformer
from PIL import Image

from studio.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """이미지 임베딩 생성 서비스 (CLIP)"""

    def __init__(self):
        """임베딩 모델 초기화"""
        try:
            # 이미지 임베딩 모델 (CLIP)
            self.image_model = SentenceTransformer(
                'clip-ViT-B-32',
                device=settings.embedding_device
            )
            logger.info("Image embedding model loaded: clip-ViT-B-32")

        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            raise

    def encode_image(self, image_path: str) -> List[float]:
        """
        이미지를 벡터로 변환

        Args:
            image_path: 이미지 파일 경로

        Returns:
            임베딩 벡터
        """
        if not self.image_model:
            raise ValueError("Image embedding model not available")

        try:
            # 이미지 로드
            image = Image.open(image_path)

            # RGB로 변환
            if image.mode != 'RGB':
                image = image.convert('RGB')

            # 임베딩 생성
            embedding = self.image_model.encode(
                image,
                convert_to_numpy=True,
                normalize_embeddings=True
            )

            return embedding.tolist()

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
        if not self.image_model:
            raise ValueError("Image embedding model not available")

        try:
            # 이미지 로드
            images = []
            for path in image_paths:
                image = Image.open(path)
                if image.mode != 'RGB':
                    image = image.convert('RGB')
                images.append(image)

            # 배치 임베딩
            embeddings = self.image_model.encode(
                images,
                convert_to_numpy=True,
                normalize_embeddings=True,
                batch_size=8
            )

            return embeddings.tolist()

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

            # 코사인 유사도
            similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))

            return float(similarity)

        except Exception as e:
            logger.error(f"Failed to compute similarity: {e}")
            return 0.0

    def get_model_info(self) -> dict:
        """임베딩 모델 정보"""
        return {
            "image_model": "clip-ViT-B-32",
            "embedding_dimension": 512,
            "device": settings.embedding_device
        }


# 전역 인스턴스
embedding_service = EmbeddingService()
