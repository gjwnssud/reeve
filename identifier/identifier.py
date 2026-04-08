"""
차량 판별 핵심 로직
이미지 → YOLO26 차량 감지 → 크롭 → EfficientNetV2-M 분류 또는 Qdrant 벡터 검색 → 결과 반환

판별 모드 (IDENTIFIER_MODE):
  efficientnet   : EfficientNetV2-M 분류기 (기본값)
                   confidence ≥ 0.9 → 직접 반환, < 0.9 → qwen3-vl 폴백
  visual_rag     : EfficientNetV2-M+Qdrant 후보 → VLM 최종 판별
  vlm_only       : VLM만으로 판별 (Qdrant 미사용)
  embedding_only : EfficientNetV2-M 임베딩+Qdrant 투표 (레거시)
"""
import logging
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from identifier.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# 응답 모델
# ──────────────────────────────────────────────

class TopKDetail(BaseModel):
    """Top-K 개별 유사도 결과"""
    rank: int = Field(description="유사도 순위 (1이 가장 유사)")
    manufacturer_id: int = Field(description="제조사 ID")
    model_id: int = Field(description="차량 모델 ID")
    similarity: float = Field(description="코사인 유사도 (0.0~1.0, 1.0에 가까울수록 동일한 차량)")
    image_path: Optional[str] = Field(default=None, description="매칭된 학습 이미지 경로")


class VehicleDetection(BaseModel):
    """감지된 개별 차량 정보"""
    index: int = Field(default=0, description="차량 인덱스 (0부터 시작, 면적 큰 순 정렬)")
    bbox: List[int] = Field(description="바운딩 박스 좌표 [x1, y1, x2, y2] (픽셀 단위, 좌상단 기준)")
    confidence: float = Field(description="YOLO 감지 신뢰도 (0.0~1.0)")
    class_name: str = Field(description="차량 종류: car / motorcycle / bus / truck")
    area: int = Field(default=0, description="바운딩 박스 면적 (픽셀²)")


class DetectionResult(BaseModel):
    """차량 감지 응답"""
    detections: List[VehicleDetection] = Field(
        default=[],
        description="감지된 차량 목록. 면적(area) 큰 순으로 정렬됩니다."
    )
    count: int = Field(default=0, description="감지된 차량 수")
    image_width: int = Field(default=0, description="원본 이미지 너비 (픽셀)")
    image_height: int = Field(default=0, description="원본 이미지 높이 (픽셀)")


class IdentificationResult(BaseModel):
    """차량 판별 결과"""
    status: str = Field(
        description=(
            "판별 상태. "
            "`identified`: 판별 성공 — 신뢰할 수 있는 결과, "
            "`low_confidence`: 후보는 있지만 확신 부족 — 수동 확인 권장, "
            "`no_match`: 유사한 학습 데이터 없음 — 데이터 추가 필요"
        )
    )
    manufacturer_korean: Optional[str] = Field(default=None, description="제조사 한글명 (예: 현대)")
    manufacturer_english: Optional[str] = Field(default=None, description="제조사 영문명 (예: Hyundai)")
    model_korean: Optional[str] = Field(default=None, description="차량 모델 한글명 (예: 코나)")
    model_english: Optional[str] = Field(default=None, description="차량 모델 영문명 (예: Kona)")
    confidence: float = Field(default=0.0, description="판별 신뢰도 (0.0~1.0). 0.8 이상이면 신뢰할 수 있는 결과입니다.")
    message: str = Field(default="", description="판별 결과 메시지 (한국어)")
    detection: Optional[VehicleDetection] = Field(
        default=None,
        description="판별에 사용된 차량의 감지 정보 (bbox 등). YOLO가 차량을 감지한 경우에만 포함됩니다."
    )
    image_width: int = Field(default=0, description="원본 이미지 너비 (픽셀)")
    image_height: int = Field(default=0, description="원본 이미지 높이 (픽셀)")
    top_k_details: List[TopKDetail] = Field(
        default=[],
        description="유사도 상위 K개 이미지 상세 정보. identified 또는 low_confidence 상태일 때 포함됩니다."
    )


class BatchImageResult(BaseModel):
    """배치 처리 내 개별 이미지 결과"""
    image_path: str = Field(description="이미지 파일명 또는 경로")
    result: Optional[IdentificationResult] = Field(default=None, description="판별 결과 (처리 성공 시)")
    error: Optional[str] = Field(default=None, description="오류 메시지 (처리 실패 시). result와 배타적입니다.")


class BatchIdentificationResult(BaseModel):
    """배치 판별 결과"""
    items: List[BatchImageResult] = Field(description="업로드 순서대로 정렬된 이미지별 판별 결과 목록")
    total: int = Field(description="총 처리된 이미지 수")
    success_count: int = Field(description="성공한 이미지 수 (error가 없는 항목)")
    error_count: int = Field(description="실패한 이미지 수 (error가 있는 항목)")
    processing_time_ms: float = Field(description="총 처리 시간 (밀리초)")


# ──────────────────────────────────────────────
# 내부 집계 구조
# ──────────────────────────────────────────────

@dataclass
class VoteCandidate:
    """투표 집계 후보"""
    manufacturer_id: int
    model_id: int
    manufacturer_korean: Optional[str] = None
    manufacturer_english: Optional[str] = None
    model_korean: Optional[str] = None
    model_english: Optional[str] = None
    weighted_score: float = 0.0
    count: int = 0
    max_score: float = 0.0
    scores: list = field(default_factory=list)
    confidence: float = 0.0


# ──────────────────────────────────────────────
# 메인 판별 클래스
# ──────────────────────────────────────────────

class VehicleIdentifier:
    """
    차량 이미지 판별기

    EfficientNetV2-M 분류기로 차량을 직접 판별한다.
    신뢰도 < classifier_confidence_threshold 시 qwen3-vl로 폴백.
    """

    COLLECTION_NAME = "training_images"
    VECTOR_DIM = 1280  # EfficientNetV2-M 특징 차원

    # COCO 데이터셋의 차량 관련 클래스
    VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck

    def __init__(self):
        """분류기, Qdrant 클라이언트, YOLO 모델 초기화"""
        self.classifier = None  # EfficientNetClassifier
        self.qdrant: Optional[QdrantClient] = None
        self.yolo_model = None
        self.vlm_service = None  # VLMService (visual_rag / vlm_only / 폴백)

    def initialize(self):
        """서비스 시작 시 호출 — 무거운 리소스 로드"""
        self._load_efficientnet()
        self._connect_qdrant()
        self._load_yolo_model()

        # VLM 서비스: efficientnet 모드에서도 폴백용으로 초기화
        if settings.identifier_mode in ("visual_rag", "vlm_only", "efficientnet"):
            self._init_vlm_service()

    # ──────────────────────────────────────────
    # 초기화
    # ──────────────────────────────────────────

    def _load_efficientnet(self):
        """EfficientNetV2-M 분류기 로드 (파인튜닝 모델 없으면 부트스트랩 모드)"""
        import torch
        from identifier.efficientnet_classifier import EfficientNetClassifier

        # CPU 스레드 최적화
        if hasattr(torch.backends, "opt_einsum"):
            torch.backends.opt_einsum.enabled = True
        torch.set_num_threads(settings.torch_threads)

        self.classifier = EfficientNetClassifier(
            model_path=settings.efficientnet_model_path,
            class_mapping_path=settings.efficientnet_class_mapping_path,
            device=settings.embedding_device if settings.embedding_device != "cpu" else None,
        )
        logger.info(
            f"EfficientNetV2-M 로드 완료: "
            f"has_head={self.classifier.has_classification_head}, "
            f"classes={self.classifier.num_classes}"
        )

    def _encode_images(self, images: list) -> np.ndarray:
        """이미지 리스트를 L2-정규화된 1280d 특징 벡터 배열로 변환 (Qdrant 검색용)"""
        rgb_images = [img.convert("RGB") for img in images]
        return self.classifier.extract_features(rgb_images)

    def _connect_qdrant(self):
        """Qdrant 클라이언트 연결"""
        try:
            self.qdrant = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=30
            )
            # 연결 확인
            collections = self.qdrant.get_collections().collections
            names = [c.name for c in collections]
            if self.COLLECTION_NAME not in names:
                logger.warning(
                    f"Collection '{self.COLLECTION_NAME}' not found. "
                    f"Available: {names}"
                )
            logger.info(f"Qdrant connected: {settings.qdrant_host}:{settings.qdrant_port}")
        except Exception as e:
            logger.error(f"Failed to connect Qdrant: {e}")
            raise

    def _init_vlm_service(self):
        """VLM 서비스 초기화 (vlm_fallback_to_embedding=true이면 실패해도 계속 진행)"""
        try:
            from identifier.vlm_service import VLMService
            self.vlm_service = VLMService()
            self.vlm_service.initialize()
            logger.info(f"VLM service initialized (mode={settings.identifier_mode})")
        except Exception as e:
            logger.error(f"Failed to initialize VLM service: {e}")
            if not settings.vlm_fallback_to_embedding:
                raise
            logger.warning("VLM unavailable — will use embedding-only as fallback")
            self.vlm_service = None

    def _load_yolo_model(self):
        """YOLO26m 차량 감지 모델 로드 (실패 시 서비스 중단 없이 경고만)"""
        if not settings.vehicle_detection:
            logger.info("Vehicle detection disabled by config")
            return

        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO("yolo26m.pt")
            logger.info("YOLO26m model loaded for vehicle detection")
        except Exception as e:
            logger.warning(f"Failed to load YOLO26 model, will use full images: {e}")
            self.yolo_model = None

    # ──────────────────────────────────────────
    # 상태 확인
    # ──────────────────────────────────────────

    def health_check(self) -> dict:
        """서비스 상태 확인"""
        classifier_info = self.classifier.health_check() if self.classifier else {"model": "not_loaded"}
        result = {
            "status": "healthy",
            "identifier_mode": settings.identifier_mode,
            "efficientnet_classifier": classifier_info,
            "yolo_model": "loaded" if self.yolo_model else ("disabled" if not settings.vehicle_detection else "not_loaded"),
            "qdrant": "disconnected",
            "training_images_count": 0,
        }

        try:
            if self.qdrant:
                info = self.qdrant.get_collection(self.COLLECTION_NAME)
                result["qdrant"] = "connected"
                result["training_images_count"] = info.points_count
        except Exception as e:
            result["qdrant"] = f"error: {e}"
            result["status"] = "degraded"

        if self.classifier is None:
            result["status"] = "unhealthy"

        if self.vlm_service:
            result.update(self.vlm_service.health_check())

        return result

    # ──────────────────────────────────────────
    # 핵심: 차량 감지
    # ──────────────────────────────────────────

    def detect_vehicles(self, image_path: str) -> DetectionResult:
        """
        이미지에서 모든 차량을 감지한다.

        Args:
            image_path: 분석할 이미지 파일 경로

        Returns:
            DetectionResult (모든 감지된 차량 목록)
        """
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        w, h = image.size

        if not self.yolo_model or not settings.vehicle_detection:
            return DetectionResult(
                detections=[],
                count=0,
                image_width=w,
                image_height=h,
            )

        try:
            results = self.yolo_model.predict(
                image,
                conf=settings.yolo_confidence,
                classes=list(self.VEHICLE_CLASSES),
                verbose=False,
            )

            if not results or results[0].boxes is None or len(results[0].boxes) == 0:
                return DetectionResult(
                    detections=[],
                    count=0,
                    image_width=w,
                    image_height=h,
                )

            # 모든 차량 감지 결과 수집
            detections = []
            boxes = results[0].boxes
            class_names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}

            for i in range(len(boxes)):
                x1, y1, x2, y2 = boxes[i].xyxy[0].cpu().numpy()
                conf = float(boxes[i].conf[0].cpu().numpy())
                class_id = int(boxes[i].cls[0].cpu().numpy())
                area = int((x2 - x1) * (y2 - y1))

                detections.append(VehicleDetection(
                    index=i,
                    bbox=[int(x1), int(y1), int(x2), int(y2)],
                    confidence=round(conf, 3),
                    class_name=class_names.get(class_id, "vehicle"),
                    area=area,
                ))

            # 면적 기준 내림차순 정렬 (가장 큰 차량이 먼저)
            detections.sort(key=lambda d: d.area, reverse=True)
            for i, det in enumerate(detections):
                det.index = i  # 인덱스 재할당

            logger.info(f"Detected {len(detections)} vehicles in {image_path}")
            return DetectionResult(
                detections=detections,
                count=len(detections),
                image_width=w,
                image_height=h,
            )

        except Exception as e:
            logger.warning(f"Vehicle detection failed: {e}")
            return DetectionResult(
                detections=[],
                count=0,
                image_width=w,
                image_height=h,
            )

    # ──────────────────────────────────────────
    # 핵심: 이미지 판별
    # ──────────────────────────────────────────

    def identify(
        self,
        image_path: str,
        bbox: Optional[List[int]] = None
    ) -> IdentificationResult:
        """
        차량 이미지를 판별한다.

        Args:
            image_path: 분석할 이미지 파일 경로
            bbox: 선택된 차량의 바운딩 박스 [x1, y1, x2, y2] (없으면 자동 감지)

        Returns:
            IdentificationResult
        """
        mode = settings.identifier_mode

        if mode == "efficientnet":
            return self._identify_efficientnet(image_path, bbox)
        elif mode == "visual_rag" and self.vlm_service is not None:
            return self._identify_visual_rag(image_path, bbox)
        elif mode == "vlm_only" and self.vlm_service is not None:
            return self._identify_vlm_only(image_path, bbox)
        else:
            # embedding_only 또는 VLM 미초기화 시 기존 경로
            embedding, detection, img_w, img_h = self._encode_image(image_path, bbox)
            search_results = self._search_qdrant(embedding)
            return self._build_identification_result(search_results, detection, img_w, img_h)

    def _identify_efficientnet(
        self,
        image_path: str,
        bbox: Optional[List[int]] = None,
    ) -> IdentificationResult:
        """EfficientNetV2-M 분류기로 판별.
        confidence ≥ classifier_confidence_threshold → identified 반환.
        미만이면 qwen3-vl 폴백, VLM도 없으면 Qdrant 검색 폴백.
        """
        image = Image.open(image_path).convert("RGB")
        img_w, img_h = image.size

        if bbox:
            x1, y1, x2, y2 = bbox
            crop = image.crop((x1, y1, x2, y2))
            detection = VehicleDetection(
                index=0,
                bbox=bbox,
                confidence=1.0,
                class_name="selected",
                area=(x2 - x1) * (y2 - y1),
            )
        else:
            crop, detection = self._detect_and_crop(image)
            if detection is None:
                return IdentificationResult(
                    status="yolo_failed",
                    confidence=0.0,
                    message="차량이 감지되지 않았습니다. 차량이 포함된 이미지를 사용해 주세요.",
                    detection=None,
                    image_width=img_w,
                    image_height=img_h,
                )

        # 1. EfficientNetV2-M 분류기 시도
        if self.classifier and self.classifier.has_classification_head:
            try:
                results = self.classifier.classify([crop])
                class_idx, confidence = results[0]
                entry = self.classifier.class_mapping["classes"][str(class_idx)]

                # identified 기준: 고정값 > 0이면 사용, 아니면 confidence_threshold (0.80)
                clf_identified = (
                    settings.classifier_confidence_threshold
                    if settings.classifier_confidence_threshold > 0
                    else settings.confidence_threshold
                )
                # VLM 폴백 기준
                clf_vlm_fallback = settings.classifier_low_confidence_threshold

                if confidence >= clf_identified:
                    # 충분한 신뢰도 → identified (YOLO 미감지 or 모델정보 누락 시 low_confidence 다운그레이드)
                    model_korean_val = entry.get("model_korean")
                    if detection is None:
                        result_status = "low_confidence"
                        message = "차량 자동 감지 실패 - 분류기 결과이지만 신뢰도를 낮춥니다."
                    elif not model_korean_val:
                        result_status = "low_confidence"
                        message = "모델 정보가 없는 학습 데이터로 판별되었습니다. 학습 데이터를 확인해 주세요."
                    else:
                        result_status = "identified"
                        message = "EfficientNetV2-M이 차량을 판별하였습니다."
                    return IdentificationResult(
                        status=result_status,
                        manufacturer_korean=entry.get("manufacturer_korean"),
                        manufacturer_english=entry.get("manufacturer_english"),
                        model_korean=entry.get("model_korean"),
                        model_english=entry.get("model_english"),
                        confidence=round(confidence, 4),
                        message=message,
                        detection=detection,
                        image_width=img_w,
                        image_height=img_h,
                    )

                elif confidence >= clf_vlm_fallback:
                    # 중간 신뢰도 → 분류기 결과를 low_confidence로 반환 (VLM 없음)
                    logger.info(
                        f"분류기 중간 신뢰도 ({confidence*100:.1f}%), "
                        f"low_confidence 반환 (VLM 없음)"
                    )
                    return IdentificationResult(
                        status="low_confidence",
                        manufacturer_korean=entry.get("manufacturer_korean"),
                        manufacturer_english=entry.get("manufacturer_english"),
                        model_korean=entry.get("model_korean"),
                        model_english=entry.get("model_english"),
                        confidence=round(confidence, 4),
                        message=f"분류기 신뢰도 낮음 ({confidence*100:.1f}%) - 가장 유사한 후보를 표시합니다.",
                        detection=detection,
                        image_width=img_w,
                        image_height=img_h,
                    )

                # confidence < clf_vlm_fallback → low_confidence로 직접 반환 (VLM 폴백 비활성화)
                logger.info(
                    f"분류기 신뢰도 미달 ({confidence*100:.1f}% < "
                    f"{clf_vlm_fallback*100:.0f}%), low_confidence 반환"
                )
                return IdentificationResult(
                    status="low_confidence",
                    manufacturer_korean=entry.get("manufacturer_korean"),
                    manufacturer_english=entry.get("manufacturer_english"),
                    model_korean=entry.get("model_korean"),
                    model_english=entry.get("model_english"),
                    confidence=round(confidence, 4),
                    message=f"분류기 신뢰도 부족 ({confidence*100:.1f}%) - 가장 유사한 후보를 표시합니다.",
                    detection=detection,
                    image_width=img_w,
                    image_height=img_h,
                )
            except Exception as e:
                logger.warning(f"EfficientNet 분류 실패: {e}")
                return IdentificationResult(
                    status="no_match",
                    confidence=0.0,
                    message="분류기 오류가 발생했습니다.",
                    detection=detection,
                    image_width=img_w,
                    image_height=img_h,
                )

        return IdentificationResult(
            status="no_match",
            confidence=0.0,
            message="분류기가 로드되지 않았습니다.",
            detection=detection,
            image_width=img_w,
            image_height=img_h,
        )

    def _identify_visual_rag(
        self,
        image_path: str,
        bbox: Optional[List[int]] = None,
    ) -> IdentificationResult:
        """Visual RAG: EfficientNet+Qdrant 후보 → VLM 최종 판별"""
        from identifier.vlm_service import VLMCandidate

        # 1. YOLO 크롭 + EfficientNet 임베딩
        embedding, detection, img_w, img_h = self._encode_image(image_path, bbox)
        search_results = self._search_qdrant(embedding)

        if not search_results:
            return IdentificationResult(
                status="no_match",
                confidence=0.0,
                message="학습 데이터가 없습니다. 관리자에게 문의하세요.",
                detection=detection,
                image_width=img_w,
                image_height=img_h,
            )

        # 2. Qdrant 후보 집계 → 상위 N개 VLMCandidate 변환
        candidates_vote = self._aggregate_votes(search_results)
        top_candidates = candidates_vote[:settings.vlm_max_candidates]

        vlm_candidates = [
            VLMCandidate(
                manufacturer_id=c.manufacturer_id,
                model_id=c.model_id,
                manufacturer_korean=c.manufacturer_korean or "",
                manufacturer_english=c.manufacturer_english or "",
                model_korean=c.model_korean or "",
                model_english=c.model_english or "",
                similarity=c.max_score,
            )
            for c in top_candidates
        ]

        # 3. 크롭 이미지 로드 (VLM 전송용)
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        if bbox:
            x1, y1, x2, y2 = bbox
            crop_image = image.crop((x1, y1, x2, y2))
        elif detection:
            x1, y1, x2, y2 = detection.bbox
            crop_image = image.crop((x1, y1, x2, y2))
        else:
            crop_image = image

        # 4. VLM 호출
        try:
            vlm_result = self.vlm_service.identify_with_candidates(crop_image, vlm_candidates)
            return self._build_vlm_result(vlm_result, detection, img_w, img_h, search_results)
        except Exception as e:
            logger.error(f"VLM failed in visual_rag mode: {e}")
            if settings.vlm_fallback_to_embedding:
                logger.warning("Falling back to embedding result")
                return self._build_identification_result(search_results, detection, img_w, img_h)
            raise

    def _identify_vlm_only(
        self,
        image_path: str,
        bbox: Optional[List[int]] = None,
    ) -> IdentificationResult:
        """VLM-only: 후보 없이 이미지만으로 판별"""
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")
        img_w, img_h = image.size

        if bbox:
            x1, y1, x2, y2 = bbox
            crop_image = image.crop((x1, y1, x2, y2))
            detection = VehicleDetection(
                index=0,
                bbox=bbox,
                confidence=1.0,
                class_name="selected",
                area=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]),
            )
        else:
            crop_image, detection = self._detect_and_crop(image)

        try:
            vlm_result = self.vlm_service.identify_freeform(crop_image)
            return self._build_vlm_result(vlm_result, detection, img_w, img_h, [])
        except Exception as e:
            logger.error(f"VLM failed in vlm_only mode: {e}")
            if settings.vlm_fallback_to_embedding:
                logger.warning("VLM failed, falling back to EfficientNet+Qdrant")
                optimized = self._optimize_image_for_embedding(crop_image)
                embedding = self._encode_images([optimized])[0]
                search_results = self._search_qdrant(embedding.tolist())
                return self._build_identification_result(search_results, detection, img_w, img_h)
            raise

    def _build_vlm_result(
        self,
        vlm,
        detection: Optional[VehicleDetection],
        img_w: int,
        img_h: int,
        search_results: List[Tuple[Dict, float]],
    ) -> IdentificationResult:
        """VLMResult → IdentificationResult 변환"""
        if vlm.manufacturer_korean and vlm.confidence >= settings.confidence_threshold:
            status = "identified"
            message = "VLM이 차량을 판별하였습니다."
        elif vlm.manufacturer_korean:
            status = "low_confidence"
            message = f"VLM 판별 신뢰도 낮음 ({vlm.confidence:.0%}). 가장 유사한 후보를 표시합니다."
        else:
            status = "no_match"
            message = "VLM이 차량을 판별하지 못했습니다."

        # YOLO 미감지 패널티 (기존 safeguard 유지)
        if detection is None and status == "identified":
            status = "low_confidence"
            message = "차량이 자동 감지되지 않아 전체 이미지로 판별하였습니다. 결과를 확인해 주세요."

        return IdentificationResult(
            status=status,
            manufacturer_korean=vlm.manufacturer_korean,
            manufacturer_english=vlm.manufacturer_english,
            model_korean=vlm.model_korean,
            model_english=vlm.model_english,
            confidence=round(vlm.confidence, 4),
            message=message,
            detection=detection,
            image_width=img_w,
            image_height=img_h,
            top_k_details=self._build_top_k_details(search_results),
        )

    # ──────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────

    def _optimize_image_for_embedding(self, image: Image.Image) -> Image.Image:
        """
        EfficientNet-B3 입력을 위한 이미지 최적화
        - 최대 크기 제한 (불필요한 고해상도 연산 방지)
        - 종횡비 유지하며 리사이즈
        """
        max_size = 800  # EfficientNet-B3는 내부적으로 300×300으로 변환하므로 이 이상 불필요

        w, h = image.size
        if w <= max_size and h <= max_size:
            return image

        # 종횡비 유지하며 축소
        scale = max_size / max(w, h)
        new_w = int(w * scale)
        new_h = int(h * scale)

        return image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    def _extract_best_vehicle(
        self, image: Image.Image, yolo_result
    ) -> Tuple[Image.Image, Optional[VehicleDetection]]:
        """단일 YOLO 결과에서 가장 큰 차량을 크롭 (배치/단건 공통)"""
        w, h = image.size

        if yolo_result.boxes is None or len(yolo_result.boxes) == 0:
            if settings.require_vehicle_detection:
                raise ValueError("No vehicle detected in the image")
            return image, None

        boxes = yolo_result.boxes
        best_idx = 0
        best_area = 0

        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes[i].xyxy[0].cpu().numpy()
            area = (x2 - x1) * (y2 - y1)
            if area > best_area:
                best_area = area
                best_idx = i

        orig_x1, orig_y1, orig_x2, orig_y2 = boxes[best_idx].xyxy[0].cpu().numpy()
        conf = float(boxes[best_idx].conf[0].cpu().numpy())
        class_id = int(boxes[best_idx].cls[0].cpu().numpy())

        class_names = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
        class_name = class_names.get(class_id, "vehicle")

        area = int((orig_x2 - orig_x1) * (orig_y2 - orig_y1))
        detection = VehicleDetection(
            index=0,
            bbox=[int(orig_x1), int(orig_y1), int(orig_x2), int(orig_y2)],
            confidence=round(conf, 3),
            class_name=class_name,
            area=area,
        )

        padding = settings.crop_padding
        x1 = max(0, int(orig_x1) - padding)
        y1 = max(0, int(orig_y1) - padding)
        x2 = min(w, int(orig_x2) + padding)
        y2 = min(h, int(orig_y2) + padding)

        cropped = image.crop((x1, y1, x2, y2))
        return cropped, detection

    def _detect_and_crop(self, image: Image.Image) -> Tuple[Image.Image, Optional[VehicleDetection]]:
        """이미지에서 가장 큰 차량을 감지하고 크롭"""
        if not self.yolo_model or not settings.vehicle_detection:
            if settings.require_vehicle_detection:
                raise ValueError("Vehicle detection is required but not available")
            return image, None

        try:
            results = self.yolo_model.predict(
                image,
                conf=settings.yolo_confidence,
                classes=list(self.VEHICLE_CLASSES),
                verbose=False,
            )
            if not results:
                if settings.require_vehicle_detection:
                    raise ValueError("No vehicle detected in the image")
                return image, None
            return self._extract_best_vehicle(image, results[0])
        except ValueError:
            raise
        except Exception as e:
            logger.warning(f"Vehicle detection failed, using full image: {e}")
            return image, None

    def _encode_image(
        self,
        image_path: str,
        bbox: Optional[List[int]] = None
    ) -> Tuple[List[float], Optional[VehicleDetection], int, int]:
        """
        이미지를 EfficientNet-B3 임베딩 벡터로 변환

        Args:
            image_path: 이미지 파일 경로
            bbox: 사용자가 선택한 bbox [x1, y1, x2, y2] (없으면 자동 감지)

        Returns:
            (임베딩 벡터, 감지 정보, 이미지 너비, 이미지 높이) 튜플
        """
        image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        w, h = image.size

        if bbox is not None:
            # 사용자가 선택한 bbox 사용
            x1, y1, x2, y2 = bbox
            # 패딩 적용
            padding = settings.crop_padding
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(w, x2 + padding)
            y2 = min(h, y2 + padding)

            cropped_image = image.crop((x1, y1, x2, y2))
            detection = VehicleDetection(
                index=0,
                bbox=bbox,  # 원본 bbox 저장
                confidence=1.0,  # 사용자 선택이므로 100%
                class_name="selected",
                area=(bbox[2] - bbox[0]) * (bbox[3] - bbox[1]),
            )
            logger.info(f"Using user-selected bbox: {bbox}")
        else:
            # 자동 감지
            cropped_image, detection = self._detect_and_crop(image)

        # 이미지 최적화 (고해상도 불필요 연산 제거)
        optimized_image = self._optimize_image_for_embedding(cropped_image)

        embedding = self._encode_images([optimized_image])[0]
        return embedding.tolist(), detection, w, h

    def _search_qdrant(
        self, embedding: List[float]
    ) -> List[Tuple[Dict, float]]:
        """Qdrant training_images 컬렉션 검색"""
        try:
            results = self.qdrant.search(
                collection_name=self.COLLECTION_NAME,
                query_vector=embedding,
                limit=settings.top_k,
            )
            return [
                (point.payload, point.score)
                for point in results
            ]
        except Exception as e:
            logger.error(f"Qdrant search failed: {e}")
            return []

    def _aggregate_votes(
        self, results: List[Tuple[Dict, float]]
    ) -> List[VoteCandidate]:
        """
        하이브리드 Weighted k-NN 알고리즘으로 제조사/모델 후보를 집계한다.

        ■ 알고리즘:

        1) Top-K 결과에서 동일 (manufacturer_id, model_id)별로 집계
           → weighted_score = Σ similarity_i
           → max_score = 가장 높은 유사도

        2) 정렬 기준 (하이브리드):
           → 1차: max_score (1% 단위로 반올림하여 비교)
           → 2차: weighted_score (max_score가 1% 이내로 같을 때)

        3) 신뢰도 = 해당 클래스의 최고 유사도 (max_score)

        ■ 예시:
           - 코나: max=0.9759 (→0.98), weighted=2.79
           - 아반떼: max=0.9455 (→0.95), weighted=2.80
           → 코나 승리 (반올림된 max_score 0.98 > 0.95)

           - 모델A: max=0.9113 (→0.91), weighted=2.71
           - 모델B: max=0.9150 (→0.92), weighted=0.91
           → 모델B 승리 (반올림된 max_score 0.92 > 0.91)

           - 모델A: max=0.9113 (→0.91), weighted=2.71
           - 모델B: max=0.9113 (→0.91), weighted=0.91
           → 모델A 승리 (max_score 동점, weighted_score 2.71 > 0.91)
        """
        votes: Dict[Tuple[int, int], VoteCandidate] = {}

        for metadata, score in results:
            key = (metadata["manufacturer_id"], metadata["model_id"])

            if key not in votes:
                votes[key] = VoteCandidate(
                    manufacturer_id=key[0],
                    model_id=key[1],
                    manufacturer_korean=metadata.get("manufacturer_korean"),
                    manufacturer_english=metadata.get("manufacturer_english"),
                    model_korean=metadata.get("model_korean"),
                    model_english=metadata.get("model_english"),
                )

            candidate = votes[key]
            candidate.weighted_score += score
            candidate.count += 1
            candidate.max_score = max(candidate.max_score, score)
            candidate.scores.append(score)

        # 신뢰도 = 해당 클래스의 최고 유사도 (사용자 친화적)
        # (선택 기준은 weighted_score이지만, 표시되는 신뢰도는 max_score 사용)
        for candidate in votes.values():
            candidate.confidence = candidate.max_score

        # 디버깅: 모든 후보 출력
        for candidate in votes.values():
            logger.info(
                f"Candidate: ({candidate.manufacturer_id},{candidate.model_id}) "
                f"weighted_score={candidate.weighted_score:.4f}, count={candidate.count}, "
                f"max_score={candidate.max_score:.4f}"
            )

        # 하이브리드 정렬: max_score 우선, 근소한 차이(1% 미만)일 때만 weighted_score 적용
        # - max_score를 소수점 2자리로 반올림 (1% 단위로 구분)
        # - 반올림된 max_score가 같으면 weighted_score로 결정
        # 예: 0.9759 → 0.98, 0.9455 → 0.95 → 0.98이 더 높으므로 max_score 높은 쪽 선택
        sorted_candidates = sorted(
            votes.values(),
            key=lambda c: (round(c.max_score, 2), c.weighted_score),
            reverse=True,
        )
        winner = sorted_candidates[0]
        logger.info(
            f"Final winner: ({winner.manufacturer_id},{winner.model_id}) "
            f"max_score={winner.max_score:.4f}, weighted_score={winner.weighted_score:.4f}"
        )
        return sorted_candidates

    def _build_identification_result(
        self,
        search_results: List[Tuple[Dict, float]],
        detection: Optional[VehicleDetection],
        img_w: int,
        img_h: int,
    ) -> IdentificationResult:
        """검색 결과로부터 판별 결과 생성 (단건/배치 공통)"""
        if not search_results:
            return IdentificationResult(
                status="no_match",
                confidence=0.0,
                message="학습 데이터가 없습니다. 관리자에게 문의하세요.",
                detection=detection,
                image_width=img_w,
                image_height=img_h,
            )

        candidates = self._aggregate_votes(search_results)
        best = candidates[0]

        if best.max_score < settings.min_similarity:
            return IdentificationResult(
                status="no_match",
                confidence=round(best.confidence, 4),
                message="판별 불가 - 유사한 차량 데이터를 찾을 수 없습니다.",
                detection=detection,
                image_width=img_w,
                image_height=img_h,
                top_k_details=self._build_top_k_details(search_results),
            )

        if best.confidence >= settings.confidence_threshold:
            status = "identified"
            message = "차량이 판별되었습니다."
        else:
            status = "low_confidence"
            message = "판별 불가 - 신뢰도가 낮습니다. 가장 유사한 후보를 표시합니다."

        # ── 보정 1: 투표 집중도 (Vote Concentration) ──
        # Top-K 결과 중 winner의 득표 비율이 낮으면 여러 차종으로 분산된 것 → low_confidence
        concentration = best.count / len(search_results)
        if concentration < settings.vote_concentration_threshold and status == "identified":
            status = "low_confidence"
            message = (
                f"판별 불가 - 상위 결과가 여러 차종으로 분산됩니다. "
                f"(집중도 {concentration:.0%})"
            )
            logger.info(
                f"Vote concentration too low: {concentration:.2f} "
                f"(threshold={settings.vote_concentration_threshold}), "
                f"winner=({best.manufacturer_id},{best.model_id}) "
                f"count={best.count}/{len(search_results)}"
            )

        # ── 보정 2: 모델 정보 누락 패널티 ──
        # Qdrant payload에 model_korean이 없으면 불완전한 학습 데이터 → identified 차단
        if not best.model_korean and status == "identified":
            status = "low_confidence"
            message = "모델 정보가 없는 학습 데이터로 판별되었습니다. 학습 데이터를 확인해 주세요."

        # ── 보정 3: YOLO 미감지 패널티 ──
        # detection이 None이면 전체 이미지(배경 포함)로 임베딩한 상태 → identified 차단
        if detection is None and status == "identified":
            status = "low_confidence"
            message = "차량 자동 감지 실패 - 전체 이미지로 판별한 결과이므로 신뢰도가 낮습니다."
            logger.info(
                f"No vehicle detection — downgraded to low_confidence "
                f"(was identified with confidence={best.confidence:.4f})"
            )

        return IdentificationResult(
            status=status,
            manufacturer_korean=best.manufacturer_korean,
            manufacturer_english=best.manufacturer_english,
            model_korean=best.model_korean,
            model_english=best.model_english,
            confidence=round(best.confidence, 4),
            message=message,
            detection=detection,
            image_width=img_w,
            image_height=img_h,
            top_k_details=self._build_top_k_details(search_results),
        )

    # ──────────────────────────────────────────
    # 배치 처리
    # ──────────────────────────────────────────

    def identify_batch(
        self,
        image_paths: List[str],
        batch_size: int = 32,
    ) -> BatchIdentificationResult:
        """
        여러 이미지를 배치로 처리하여 성능 극대화.
        YOLO, EfficientNet-B3, Qdrant 각 단계를 배치로 실행.

        Args:
            image_paths: 이미지 파일 경로 리스트
            batch_size: 한 번에 처리할 이미지 수

        Returns:
            BatchIdentificationResult
        """
        start = time.time()
        all_items: List[BatchImageResult] = []

        for i in range(0, len(image_paths), batch_size):
            chunk = image_paths[i:i + batch_size]
            items = self._process_batch(chunk)
            all_items.extend(items)
            logger.info(
                f"Batch progress: {min(i + batch_size, len(image_paths))}/{len(image_paths)}"
            )

        elapsed = (time.time() - start) * 1000
        success = sum(1 for item in all_items if item.error is None)

        return BatchIdentificationResult(
            items=all_items,
            total=len(all_items),
            success_count=success,
            error_count=len(all_items) - success,
            processing_time_ms=round(elapsed, 1),
        )

    def _process_batch(self, image_paths: List[str]) -> List[BatchImageResult]:
        """
        한 배치(N장)를 파이프라인으로 처리. 모드별 파이프라인:

        - efficientnet:   YOLO → EfficientNet 분류 → VLM 폴백 → Qdrant 폴백
        - visual_rag:     YOLO → EfficientNet 임베딩 → Qdrant 검색 → VLM 최종 판별
        - embedding_only: YOLO → EfficientNet 임베딩 → Qdrant 검색 → 투표
        - vlm_only:       YOLO → VLM 직접 판별 → Qdrant 폴백
        """
        n = len(image_paths)

        # ── 1. 이미지 로드 ──
        images: List[Optional[Image.Image]] = []
        sizes: List[Tuple[int, int]] = []
        errors: List[Optional[str]] = [None] * n

        for idx, path in enumerate(image_paths):
            try:
                img = Image.open(path)
                if img.mode != "RGB":
                    img = img.convert("RGB")
                images.append(img)
                sizes.append(img.size)
            except Exception as e:
                images.append(None)
                sizes.append((0, 0))
                errors[idx] = f"이미지 로드 실패: {e}"

        valid_indices = [i for i in range(n) if images[i] is not None]
        if not valid_indices:
            return [
                BatchImageResult(image_path=image_paths[i], error=errors[i])
                for i in range(n)
            ]

        # ── 2. YOLO 배치 감지 + 크롭 ──
        cropped_images: List[Optional[Image.Image]] = [None] * n
        detections: List[Optional[VehicleDetection]] = [None] * n

        if self.yolo_model and settings.vehicle_detection:
            valid_imgs = [images[i] for i in valid_indices]
            try:
                yolo_results = self.yolo_model.predict(
                    valid_imgs,
                    conf=settings.yolo_confidence,
                    classes=list(self.VEHICLE_CLASSES),
                    verbose=False,
                )
                for batch_idx, orig_idx in enumerate(valid_indices):
                    try:
                        cropped, det = self._extract_best_vehicle(
                            images[orig_idx], yolo_results[batch_idx]
                        )
                        cropped_images[orig_idx] = cropped
                        detections[orig_idx] = det
                    except ValueError as e:
                        errors[orig_idx] = str(e)
            except Exception as e:
                logger.warning(f"Batch YOLO failed, using full images: {e}")
                for idx in valid_indices:
                    cropped_images[idx] = images[idx]
        else:
            for idx in valid_indices:
                cropped_images[idx] = images[idx]

        mode = settings.identifier_mode

        # ──────────────────────────────────────────
        # efficientnet 모드: 분류기 → VLM 폴백 → Qdrant 폴백
        # ──────────────────────────────────────────
        if mode == "efficientnet":
            classify_indices = [
                i for i in valid_indices
                if cropped_images[i] is not None and errors[i] is None
            ]
            result_map: Dict[int, IdentificationResult] = {}
            vlm_fallback_indices: List[int] = []

            # 3a. EfficientNet 배치 분류
            if classify_indices and self.classifier and self.classifier.has_classification_head:
                clf_identified = (
                    settings.classifier_confidence_threshold
                    if settings.classifier_confidence_threshold > 0
                    else settings.confidence_threshold
                )
                clf_vlm_fallback = settings.classifier_low_confidence_threshold
                try:
                    clf_results = self.classifier.classify(
                        [cropped_images[i] for i in classify_indices]
                    )
                    for batch_idx, orig_idx in enumerate(classify_indices):
                        class_idx, confidence = clf_results[batch_idx]
                        entry = self.classifier.class_mapping["classes"][str(class_idx)]
                        detection = detections[orig_idx]
                        w, h = sizes[orig_idx]

                        if confidence >= clf_identified:
                            # 충분한 신뢰도 → identified
                            status = "identified" if detection is not None else "low_confidence"
                            message = (
                                "EfficientNetV2-M이 차량을 판별하였습니다."
                                if detection is not None
                                else "차량 자동 감지 실패 - 분류기 결과이지만 신뢰도를 낮춥니다."
                            )
                            result_map[orig_idx] = IdentificationResult(
                                status=status,
                                manufacturer_korean=entry.get("manufacturer_korean"),
                                manufacturer_english=entry.get("manufacturer_english"),
                                model_korean=entry.get("model_korean"),
                                model_english=entry.get("model_english"),
                                confidence=round(confidence, 4),
                                message=message,
                                detection=detection,
                                image_width=w,
                                image_height=h,
                            )
                        elif confidence >= clf_vlm_fallback:
                            # 중간 신뢰도 → low_confidence 반환 (VLM 없음)
                            result_map[orig_idx] = IdentificationResult(
                                status="low_confidence",
                                manufacturer_korean=entry.get("manufacturer_korean"),
                                manufacturer_english=entry.get("manufacturer_english"),
                                model_korean=entry.get("model_korean"),
                                model_english=entry.get("model_english"),
                                confidence=round(confidence, 4),
                                message=f"분류기 신뢰도 낮음 ({confidence*100:.1f}%) - 가장 유사한 후보를 표시합니다.",
                                detection=detection,
                                image_width=w,
                                image_height=h,
                            )
                        else:
                            # 신뢰도 미달 → VLM 폴백
                            vlm_fallback_indices.append(orig_idx)
                except Exception as e:
                    logger.warning(f"EfficientNet 배치 분류 실패, VLM 폴백: {e}")
                    vlm_fallback_indices = classify_indices[:]
            else:
                vlm_fallback_indices = classify_indices[:]

            # 3b. VLM 폴백 (concurrent)
            qdrant_fallback_indices: List[int] = []
            if vlm_fallback_indices and self.vlm_service is not None:
                from concurrent.futures import ThreadPoolExecutor

                def _run_vlm_freeform(idx: int):
                    try:
                        vlm_res = self.vlm_service.identify_freeform(cropped_images[idx])
                        return idx, vlm_res
                    except Exception as e:
                        logger.warning(f"VLM 폴백 실패 idx={idx}: {e}")
                        return idx, None

                with ThreadPoolExecutor(max_workers=settings.vlm_batch_concurrency) as executor:
                    futures = {executor.submit(_run_vlm_freeform, idx): idx for idx in vlm_fallback_indices}
                    for future in futures:
                        idx, vlm_res = future.result()
                        if vlm_res is not None:
                            w, h = sizes[idx]
                            result_map[idx] = self._build_vlm_result(
                                vlm_res, detections[idx], w, h, []
                            )
                        else:
                            qdrant_fallback_indices.append(idx)
            else:
                qdrant_fallback_indices = vlm_fallback_indices[:]

            # 3c. Qdrant 최후 폴백
            if qdrant_fallback_indices:
                try:
                    from qdrant_client.models import SearchRequest

                    fallback_inputs = [
                        self._optimize_image_for_embedding(cropped_images[i])
                        for i in qdrant_fallback_indices
                    ]
                    fallback_embeddings = self._encode_images(fallback_inputs)
                    requests = [
                        SearchRequest(vector=fallback_embeddings[bi].tolist(), limit=settings.top_k)
                        for bi in range(len(qdrant_fallback_indices))
                    ]
                    batch_results = self.qdrant.search_batch(
                        collection_name=self.COLLECTION_NAME,
                        requests=requests,
                    )
                    for bi, orig_idx in enumerate(qdrant_fallback_indices):
                        w, h = sizes[orig_idx]
                        search_results = [
                            (point.payload, point.score)
                            for point in batch_results[bi]
                            if point.payload is not None
                        ]
                        result_map[orig_idx] = self._build_identification_result(
                            search_results, detections[orig_idx], w, h
                        )
                except Exception as e:
                    logger.error(f"Qdrant 배치 폴백 실패: {e}")
                    for orig_idx in qdrant_fallback_indices:
                        w, h = sizes[orig_idx]
                        result_map[orig_idx] = IdentificationResult(
                            status="low_confidence",
                            confidence=0.0,
                            message="판별에 실패했습니다.",
                            detection=detections[orig_idx],
                            image_width=w,
                            image_height=h,
                        )

            items: List[BatchImageResult] = []
            for idx in range(n):
                if errors[idx]:
                    items.append(BatchImageResult(image_path=image_paths[idx], error=errors[idx]))
                    continue
                result = result_map.get(idx)
                if result is None:
                    w, h = sizes[idx]
                    result = IdentificationResult(
                        status="low_confidence",
                        confidence=0.0,
                        message="판별에 실패했습니다.",
                        detection=detections[idx],
                        image_width=w,
                        image_height=h,
                    )
                items.append(BatchImageResult(image_path=image_paths[idx], result=result))
            return items

        # ──────────────────────────────────────────
        # vlm_only 모드: VLM 직접 판별 → Qdrant 폴백
        # ──────────────────────────────────────────
        if mode == "vlm_only":
            vlm_indices = [
                i for i in valid_indices
                if cropped_images[i] is not None and errors[i] is None
            ]
            result_map: Dict[int, IdentificationResult] = {}
            qdrant_fallback_indices: List[int] = []

            if vlm_indices and self.vlm_service is not None:
                from concurrent.futures import ThreadPoolExecutor

                def _run_vlm_only(idx: int):
                    try:
                        vlm_res = self.vlm_service.identify_freeform(cropped_images[idx])
                        return idx, vlm_res
                    except Exception as e:
                        logger.warning(f"VLM 판별 실패 idx={idx}: {e}")
                        return idx, None

                with ThreadPoolExecutor(max_workers=settings.vlm_batch_concurrency) as executor:
                    futures = {executor.submit(_run_vlm_only, idx): idx for idx in vlm_indices}
                    for future in futures:
                        idx, vlm_res = future.result()
                        if vlm_res is not None:
                            w, h = sizes[idx]
                            result_map[idx] = self._build_vlm_result(
                                vlm_res, detections[idx], w, h, []
                            )
                        elif settings.vlm_fallback_to_embedding:
                            qdrant_fallback_indices.append(idx)
                        else:
                            w, h = sizes[idx]
                            result_map[idx] = IdentificationResult(
                                status="low_confidence",
                                confidence=0.0,
                                message="VLM 판별에 실패했습니다.",
                                detection=detections[idx],
                                image_width=w,
                                image_height=h,
                            )

            if qdrant_fallback_indices:
                try:
                    from qdrant_client.models import SearchRequest

                    fallback_inputs = [
                        self._optimize_image_for_embedding(cropped_images[i])
                        for i in qdrant_fallback_indices
                    ]
                    fallback_embeddings = self._encode_images(fallback_inputs)
                    requests = [
                        SearchRequest(vector=fallback_embeddings[bi].tolist(), limit=settings.top_k)
                        for bi in range(len(qdrant_fallback_indices))
                    ]
                    batch_results = self.qdrant.search_batch(
                        collection_name=self.COLLECTION_NAME,
                        requests=requests,
                    )
                    for bi, orig_idx in enumerate(qdrant_fallback_indices):
                        w, h = sizes[orig_idx]
                        search_results = [
                            (point.payload, point.score)
                            for point in batch_results[bi]
                            if point.payload is not None
                        ]
                        result_map[orig_idx] = self._build_identification_result(
                            search_results, detections[orig_idx], w, h
                        )
                except Exception as e:
                    logger.error(f"Qdrant 배치 폴백 실패 (vlm_only): {e}")
                    for orig_idx in qdrant_fallback_indices:
                        w, h = sizes[orig_idx]
                        result_map[orig_idx] = IdentificationResult(
                            status="low_confidence",
                            confidence=0.0,
                            message="판별에 실패했습니다.",
                            detection=detections[orig_idx],
                            image_width=w,
                            image_height=h,
                        )

            items: List[BatchImageResult] = []
            for idx in range(n):
                if errors[idx]:
                    items.append(BatchImageResult(image_path=image_paths[idx], error=errors[idx]))
                    continue
                result = result_map.get(idx)
                if result is None:
                    w, h = sizes[idx]
                    result = IdentificationResult(
                        status="low_confidence",
                        confidence=0.0,
                        message="판별에 실패했습니다.",
                        detection=detections[idx],
                        image_width=w,
                        image_height=h,
                    )
                items.append(BatchImageResult(image_path=image_paths[idx], result=result))
            return items

        # ──────────────────────────────────────────
        # embedding_only / visual_rag 모드
        # ──────────────────────────────────────────

        # ── 3. EfficientNet 배치 임베딩 ──
        embedding_indices = [
            i for i in valid_indices
            if cropped_images[i] is not None and errors[i] is None
        ]
        embeddings_map: Dict[int, List[float]] = {}

        if embedding_indices:
            embedding_inputs = [
                self._optimize_image_for_embedding(cropped_images[i])
                for i in embedding_indices
            ]
            batch_embeddings = self._encode_images(embedding_inputs)
            for batch_idx, orig_idx in enumerate(embedding_indices):
                embeddings_map[orig_idx] = batch_embeddings[batch_idx].tolist()

        # ── 4. Qdrant 배치 검색 ──
        search_map: Dict[int, List[Tuple[Dict, float]]] = {}

        if embeddings_map:
            from qdrant_client.models import SearchRequest

            request_indices = sorted(embeddings_map.keys())
            requests = [
                SearchRequest(
                    vector=embeddings_map[idx],
                    limit=settings.top_k,
                )
                for idx in request_indices
            ]
            try:
                batch_results = self.qdrant.search_batch(
                    collection_name=self.COLLECTION_NAME,
                    requests=requests,
                )
                for batch_idx, orig_idx in enumerate(request_indices):
                    search_map[orig_idx] = [
                        (point.payload, point.score)
                        for point in batch_results[batch_idx]
                        if point.payload is not None
                    ]
            except Exception as e:
                logger.error(f"Batch Qdrant search failed: {e}")

        # ── 5. VLM 배치 (visual_rag 모드) ──
        vlm_result_map: Dict[int, object] = {}

        if (
            mode == "visual_rag"
            and self.vlm_service is not None
            and embeddings_map
        ):
            from concurrent.futures import ThreadPoolExecutor
            from identifier.vlm_service import VLMCandidate

            def _run_vlm(idx: int):
                try:
                    search_results = search_map.get(idx, [])
                    if not search_results:
                        return idx, None
                    candidates_vote = self._aggregate_votes(search_results)
                    top_candidates = candidates_vote[:settings.vlm_max_candidates]
                    vlm_candidates = [
                        VLMCandidate(
                            manufacturer_id=c.manufacturer_id,
                            model_id=c.model_id,
                            manufacturer_korean=c.manufacturer_korean or "",
                            manufacturer_english=c.manufacturer_english or "",
                            model_korean=c.model_korean or "",
                            model_english=c.model_english or "",
                            similarity=c.max_score,
                        )
                        for c in top_candidates
                    ]
                    crop = cropped_images[idx]
                    vlm_res = self.vlm_service.identify_with_candidates(crop, vlm_candidates)
                    return idx, vlm_res
                except Exception as e:
                    logger.warning(f"VLM failed for batch index {idx}: {e}")
                    return idx, None

            vlm_indices = [i for i in embedding_indices if not errors[i]]
            with ThreadPoolExecutor(max_workers=settings.vlm_batch_concurrency) as executor:
                futures = {executor.submit(_run_vlm, idx): idx for idx in vlm_indices}
                for future in futures:
                    idx, vlm_res = future.result()
                    if vlm_res is not None:
                        vlm_result_map[idx] = vlm_res

        # ── 6. 결과 조립 ──
        items: List[BatchImageResult] = []

        for idx in range(n):
            if errors[idx]:
                items.append(BatchImageResult(
                    image_path=image_paths[idx],
                    error=errors[idx],
                ))
                continue

            w, h = sizes[idx]
            detection = detections[idx]
            search_results = search_map.get(idx, [])

            if idx in vlm_result_map:
                result = self._build_vlm_result(vlm_result_map[idx], detection, w, h, search_results)
            else:
                result = self._build_identification_result(search_results, detection, w, h)

            items.append(BatchImageResult(
                image_path=image_paths[idx],
                result=result,
            ))

        return items

    def _build_top_k_details(
        self, results: List[Tuple[Dict, float]]
    ) -> List[TopKDetail]:
        """Top-K 결과를 응답 포맷으로 변환"""
        details = []
        for rank, (metadata, score) in enumerate(results, start=1):
            details.append(TopKDetail(
                rank=rank,
                manufacturer_id=metadata.get("manufacturer_id", 0),
                model_id=metadata.get("model_id", 0),
                similarity=round(score, 4),
                image_path=metadata.get("image_path"),
            ))
        return details
