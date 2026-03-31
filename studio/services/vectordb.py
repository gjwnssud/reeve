"""
Qdrant 벡터 데이터베이스 서비스
임베딩 저장 및 유사도 검색 (대규모 데이터 대응)
"""
import logging
from typing import List, Dict, Optional, Tuple, Callable

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue,
    PointIdsList,
)

from studio.config import settings

logger = logging.getLogger(__name__)

# 컬렉션별 벡터 차원 정의
COLLECTION_CONFIGS = {
    "training_images": {
        "size": 1280,
        "distance": Distance.COSINE,
        "description": "학습 이미지 벡터 컬렉션"
    }
}


class VectorDBService:
    """Qdrant 기반 벡터 데이터베이스 서비스"""

    def __init__(self):
        """Qdrant 클라이언트 초기화"""
        self.client = None
        self._connect()

    def _connect(self):
        """Qdrant 연결 (초기화 및 재연결)"""
        try:
            self.client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=30
            )

            # 컬렉션 초기화
            for name, config in COLLECTION_CONFIGS.items():
                self._ensure_collection(name, config["size"], config["distance"])

            logger.info("Qdrant client initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self.client = None

    def _ensure_collection(self, name: str, size: int, distance: Distance):
        """컬렉션이 없으면 생성"""
        try:
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]

            if name not in collection_names:
                self.client.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=size,
                        distance=distance,
                        on_disk=True  # 디스크 기반 인덱스 (대규모 데이터 대응)
                    ),
                    on_disk_payload=True  # 메타데이터도 디스크에 저장
                )
                logger.info(f"Collection '{name}' created (size={size}, on_disk=True)")
            else:
                logger.info(f"Collection '{name}' ready")

        except Exception as e:
            logger.error(f"Failed to ensure collection '{name}': {e}")

    def _get_client(self):
        """클라이언트 연결 확인 후 반환"""
        if self.client is None:
            logger.info("Qdrant client not available, attempting reconnect...")
            self._connect()
        return self.client

    def add_training_image(
        self,
        training_id: int,
        image_path: str,
        manufacturer_id: int,
        model_id: int,
        embedding: List[float],
        metadata: Optional[Dict] = None,
        manufacturer_korean: Optional[str] = None,
        manufacturer_english: Optional[str] = None,
        model_korean: Optional[str] = None,
        model_english: Optional[str] = None,
    ) -> bool:
        """
        학습 이미지 임베딩 추가

        Args:
            training_id: 학습 데이터 ID
            image_path: 이미지 경로
            manufacturer_id: 제조사 ID
            model_id: 모델 ID
            embedding: 이미지 임베딩 벡터
            metadata: 추가 메타데이터
            manufacturer_korean: 제조사 한글명
            manufacturer_english: 제조사 영문명
            model_korean: 모델 한글명
            model_english: 모델 영문명

        Returns:
            성공 여부
        """
        client = self._get_client()
        if not client:
            logger.error("Training collection not available")
            return False

        try:
            payload = {
                "id": training_id,
                "image_path": image_path,
                "manufacturer_id": manufacturer_id,
                "model_id": model_id,
                "manufacturer_korean": manufacturer_korean,
                "manufacturer_english": manufacturer_english,
                "model_korean": model_korean,
                "model_english": model_english,
            }

            if metadata:
                payload.update(metadata)

            client.upsert(
                collection_name="training_images",
                points=[PointStruct(
                    id=training_id,
                    vector=embedding,
                    payload=payload
                )]
            )
            logger.info(f"Added training image: {training_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to add training image {training_id}: {e}")
            return False

    def search_training_images(
        self,
        query_embedding: List[float],
        n_results: int = 10,
        manufacturer_id: Optional[int] = None,
        model_id: Optional[int] = None
    ) -> List[Tuple[Dict, float]]:
        """
        학습 이미지 유사도 검색

        Args:
            query_embedding: 쿼리 임베딩 벡터
            n_results: 반환할 결과 수
            manufacturer_id: 제조사 ID 필터
            model_id: 모델 ID 필터

        Returns:
            (메타데이터, 유사도) 튜플 리스트
        """
        client = self._get_client()
        if not client:
            return []

        try:
            conditions = []
            if manufacturer_id:
                conditions.append(FieldCondition(
                    key="manufacturer_id",
                    match=MatchValue(value=manufacturer_id)
                ))
            if model_id:
                conditions.append(FieldCondition(
                    key="model_id",
                    match=MatchValue(value=model_id)
                ))

            query_filter = Filter(must=conditions) if conditions else None

            results = client.search(
                collection_name="training_images",
                query_vector=query_embedding,
                limit=n_results,
                query_filter=query_filter
            )

            matches = []
            for point in results:
                matches.append((point.payload, point.score))

            return matches

        except Exception as e:
            logger.error(f"Failed to search training images: {e}")
            return []

    def delete_training_image(self, training_id: int) -> bool:
        """학습 이미지 임베딩 삭제 (Qdrant에서 포인트 제거)"""
        client = self._get_client()
        if not client:
            return False
        try:
            client.delete(
                collection_name="training_images",
                points_selector=PointIdsList(points=[training_id])
            )
            logger.info(f"Deleted training image from Qdrant: {training_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete training image {training_id} from Qdrant: {e}")
            return False

    def recreate_collection_with_reembedding(
        self,
        embedding_fn: Callable[[List[str]], List[List[float]]],
        records: List[Dict],
        batch_size: int = 32,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Dict:
        """
        training_images 컬렉션을 삭제하고 새 차원(1280d)으로 재생성한 뒤
        모든 레코드를 재임베딩하여 저장.

        Args:
            embedding_fn: 이미지 경로 리스트 → 임베딩 리스트 반환 함수
            records: training_dataset 레코드 딕셔너리 리스트
                     필수 키: id, image_path, manufacturer_id, model_id
                     선택 키: manufacturer_korean, manufacturer_english, model_korean, model_english
            batch_size: 배치 크기
            progress_callback: (현재 처리 수, 전체 수) 콜백

        Returns:
            {"migrated": N, "failed": M, "new_dimension": 1280}
        """
        client = self._get_client()
        if not client:
            raise RuntimeError("Qdrant 클라이언트 연결 실패")

        # 기존 컬렉션 삭제
        try:
            client.delete_collection("training_images")
            logger.info("training_images 컬렉션 삭제 완료")
        except Exception:
            pass

        # 새 차원으로 재생성
        self._ensure_collection("training_images", 1280, Distance.COSINE)

        total = len(records)
        migrated = 0
        failed = 0

        for i in range(0, total, batch_size):
            batch = records[i:i + batch_size]
            paths = [r["image_path"] for r in batch]

            try:
                embeddings = embedding_fn(paths)
            except Exception as e:
                logger.error(f"배치 임베딩 실패 (index {i}): {e}")
                failed += len(batch)
                if progress_callback:
                    progress_callback(min(i + batch_size, total), total)
                continue

            points = []
            for r, emb in zip(batch, embeddings):
                payload = {
                    "id": r["id"],
                    "image_path": r["image_path"],
                    "manufacturer_id": r["manufacturer_id"],
                    "model_id": r["model_id"],
                    "manufacturer_korean": r.get("manufacturer_korean"),
                    "manufacturer_english": r.get("manufacturer_english"),
                    "model_korean": r.get("model_korean"),
                    "model_english": r.get("model_english"),
                }
                points.append(PointStruct(id=r["id"], vector=emb, payload=payload))

            try:
                client.upsert("training_images", points=points)
                migrated += len(batch)
            except Exception as e:
                logger.error(f"Qdrant upsert 실패 (index {i}): {e}")
                failed += len(batch)

            if progress_callback:
                progress_callback(min(i + batch_size, total), total)

        logger.info(f"재임베딩 완료: migrated={migrated}, failed={failed}")
        return {"migrated": migrated, "failed": failed, "new_dimension": 1280}

    def clear_all_collections(self) -> bool:
        """모든 컬렉션 초기화 (주의!)"""
        try:
            client = self._get_client()
            if not client:
                return False

            for name, config in COLLECTION_CONFIGS.items():
                try:
                    client.delete_collection(collection_name=name)
                except Exception:
                    pass

            # 재생성
            self._connect()
            logger.warning("All collections cleared and recreated")
            return True

        except Exception as e:
            logger.error(f"Failed to clear collections: {e}")
            return False

    def get_collection_stats(self) -> Dict:
        """컬렉션 통계 정보"""
        stats = {}

        try:
            client = self._get_client()
            if not client:
                return stats

            for name in COLLECTION_CONFIGS:
                try:
                    info = client.get_collection(collection_name=name)
                    stats[name] = info.points_count
                except Exception:
                    stats[name] = 0

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")

        return stats


# 전역 인스턴스
vectordb_service = VectorDBService()
