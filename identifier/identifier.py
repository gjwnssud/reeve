"""
차량 판별 핵심 로직
이미지 → YOLO26 차량 감지 → 크롭 → EfficientNetV2-M 분류 또는 VLM 판별 → 결과 반환

판별 모드 (IDENTIFIER_MODE):
  efficientnet : EfficientNetV2-M 분류기 (기본값)
                 confidence ≥ classifier_confidence_threshold(기본 0.80) → identified
                 그 미만 구간은 모두 low_confidence로 반환 (VLM 폴백 없음, 단건/배치 동일)
  vlm_only     : VLM만으로 판별
"""
import logging
import time
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

from PIL import Image
from pydantic import BaseModel, Field

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
# 메인 판별 클래스
# ──────────────────────────────────────────────

class VehicleIdentifier:
    """
    차량 이미지 판별기

    EfficientNetV2-M 분류기로 차량을 직접 판별한다.
    신뢰도 ≥ classifier_confidence_threshold → identified,
    그 미만 구간은 모두 low_confidence 반환 (VLM 폴백 없음).
    """

    # COCO 데이터셋의 차량 관련 클래스
    VEHICLE_CLASSES = {2, 3, 5, 7}  # car, motorcycle, bus, truck

    def __init__(self):
        """분류기, YOLO 모델 초기화"""
        self.classifier = None  # EfficientNetClassifier
        self.yolo_model = None
        self.vlm_service = None  # VLMService (vlm_only / efficientnet 폴백)

    def initialize(self):
        """서비스 시작 시 호출 — 무거운 리소스 로드"""
        self._load_efficientnet()
        self._load_yolo_model()

        # VLM 서비스: efficientnet 모드에서도 폴백용으로 초기화
        if settings.identifier_mode in ("vlm_only", "efficientnet"):
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

    def _init_vlm_service(self):
        """VLM 서비스 초기화 (실패해도 서비스 중단 없이 None으로 둔다)"""
        try:
            from identifier.vlm_service import VLMService
            self.vlm_service = VLMService()
            self.vlm_service.initialize()
            logger.info(f"VLM service initialized (mode={settings.identifier_mode})")
        except Exception as e:
            logger.error(f"Failed to initialize VLM service: {e}")
            logger.warning("VLM unavailable — identify() will fall back to low_confidence")
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
        }

        if self.classifier is None:
            result["status"] = "unhealthy"

        if self.vlm_service:
            result.update(self.vlm_service.health_check())

        return result

    # ──────────────────────────────────────────
    # 핵심: 차량 감지
    # ──────────────────────────────────────────

    def detect_vehicles(self, image_path: str, image: Optional[Image.Image] = None) -> DetectionResult:
        """
        이미지에서 모든 차량을 감지한다.

        Args:
            image_path: 분석할 이미지 파일 경로
            image: 미리 로드된 PIL 이미지 (재사용용). 없으면 image_path에서 새로 연다.

        Returns:
            DetectionResult (모든 감지된 차량 목록)
        """
        if image is None:
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
        bbox: Optional[List[int]] = None,
        image: Optional[Image.Image] = None,
    ) -> IdentificationResult:
        """
        차량 이미지를 판별한다.

        Args:
            image_path: 분석할 이미지 파일 경로
            bbox: 선택된 차량의 바운딩 박스 [x1, y1, x2, y2] (없으면 자동 감지)
            image: 미리 로드된 PIL 이미지 (재사용용). 없으면 image_path에서 새로 연다.

        Returns:
            IdentificationResult
        """
        if image is None:
            image = Image.open(image_path)
        if image.mode != "RGB":
            image = image.convert("RGB")

        mode = settings.identifier_mode

        if mode == "vlm_only" and self.vlm_service is not None:
            return self._identify_vlm_only(image, bbox)
        # efficientnet (기본) 또는 VLM 미초기화 시 분류기 경로
        return self._identify_efficientnet(image, bbox)

    def _identify_efficientnet(
        self,
        image: Image.Image,
        bbox: Optional[List[int]] = None,
    ) -> IdentificationResult:
        """EfficientNetV2-M 분류기로 판별.
        confidence ≥ classifier_confidence_threshold → identified 반환.
        미만이면 분류기 top-1 결과를 low_confidence로 반환한다 (VLM 폴백 없음).
        """
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

                # 신뢰도 미달 → 분류기 top-1 결과를 low_confidence로 반환
                tier = "중간" if confidence >= clf_vlm_fallback else "부족"
                logger.info(
                    f"분류기 신뢰도 {tier} ({confidence*100:.1f}% < {clf_identified*100:.0f}%), "
                    f"low_confidence 반환"
                )
                return IdentificationResult(
                    status="low_confidence",
                    manufacturer_korean=entry.get("manufacturer_korean"),
                    manufacturer_english=entry.get("manufacturer_english"),
                    model_korean=entry.get("model_korean"),
                    model_english=entry.get("model_english"),
                    confidence=round(confidence, 4),
                    message=f"분류기 신뢰도 {tier} ({confidence*100:.1f}%) - 가장 유사한 후보를 표시합니다.",
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

    def _identify_vlm_only(
        self,
        image: Image.Image,
        bbox: Optional[List[int]] = None,
    ) -> IdentificationResult:
        """VLM-only: 후보 없이 이미지만으로 판별"""
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
            return self._build_vlm_result(vlm_result, detection, img_w, img_h)
        except Exception as e:
            logger.error(f"VLM failed in vlm_only mode: {e}")
            return IdentificationResult(
                status="low_confidence",
                confidence=0.0,
                message="VLM 판별에 실패했습니다.",
                detection=detection,
                image_width=img_w,
                image_height=img_h,
            )

    def _build_vlm_result(
        self,
        vlm,
        detection: Optional[VehicleDetection],
        img_w: int,
        img_h: int,
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
        )

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
        YOLO, EfficientNet 각 단계를 배치로 실행.

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

        - efficientnet: YOLO → EfficientNet 분류 (단건과 동일)
        - vlm_only:     YOLO → VLM 직접 판별
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
        # efficientnet 모드: 분류기만 사용 (단건 경로와 동일)
        # ──────────────────────────────────────────
        if mode == "efficientnet":
            classify_indices = [
                i for i in valid_indices
                if cropped_images[i] is not None and errors[i] is None
            ]
            result_map: Dict[int, IdentificationResult] = {}

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
                        model_korean_val = entry.get("model_korean")

                        if confidence >= clf_identified:
                            # 충분한 신뢰도 → identified (safeguard: YOLO 미감지/모델 누락 시 다운그레이드)
                            if detection is None:
                                status = "low_confidence"
                                message = "차량 자동 감지 실패 - 분류기 결과이지만 신뢰도를 낮춥니다."
                            elif not model_korean_val:
                                status = "low_confidence"
                                message = "모델 정보가 없는 학습 데이터로 판별되었습니다. 학습 데이터를 확인해 주세요."
                            else:
                                status = "identified"
                                message = "EfficientNetV2-M이 차량을 판별하였습니다."
                        else:
                            # 신뢰도 미달 → 분류기 top-1 결과를 low_confidence로 반환
                            tier = "중간" if confidence >= clf_vlm_fallback else "부족"
                            status = "low_confidence"
                            message = f"분류기 신뢰도 {tier} ({confidence*100:.1f}%) - 가장 유사한 후보를 표시합니다."

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
                except Exception as e:
                    logger.warning(f"EfficientNet 배치 분류 실패: {e}")
                    for orig_idx in classify_indices:
                        w, h = sizes[orig_idx]
                        result_map[orig_idx] = IdentificationResult(
                            status="no_match",
                            confidence=0.0,
                            message="분류기 오류가 발생했습니다.",
                            detection=detections[orig_idx],
                            image_width=w,
                            image_height=h,
                        )
            else:
                # 분류기 미로드 → 단건 경로와 동일하게 no_match
                for orig_idx in classify_indices:
                    w, h = sizes[orig_idx]
                    result_map[orig_idx] = IdentificationResult(
                        status="no_match",
                        confidence=0.0,
                        message="분류기가 로드되지 않았습니다.",
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
        # vlm_only 모드: VLM 직접 판별 (실패 시 low_confidence)
        # ──────────────────────────────────────────
        if mode == "vlm_only":
            vlm_indices = [
                i for i in valid_indices
                if cropped_images[i] is not None and errors[i] is None
            ]
            result_map: Dict[int, IdentificationResult] = {}

            if vlm_indices and self.vlm_service is not None and self.vlm_service.is_available():
                from concurrent.futures import ThreadPoolExecutor, as_completed

                def _run_vlm_only(idx: int):
                    try:
                        vlm_res = self.vlm_service.identify_freeform(cropped_images[idx])
                        return idx, vlm_res
                    except Exception as e:
                        logger.warning(f"VLM 판별 실패 idx={idx}: {e}")
                        return idx, None

                with ThreadPoolExecutor(max_workers=settings.vlm_batch_concurrency) as executor:
                    futures = {executor.submit(_run_vlm_only, idx): idx for idx in vlm_indices}
                    for future in as_completed(futures):
                        idx, vlm_res = future.result()
                        w, h = sizes[idx]
                        if vlm_res is not None:
                            result_map[idx] = self._build_vlm_result(
                                vlm_res, detections[idx], w, h
                            )
                        else:
                            result_map[idx] = IdentificationResult(
                                status="low_confidence",
                                confidence=0.0,
                                message="VLM 판별에 실패했습니다.",
                                detection=detections[idx],
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

        # 알 수 없는 모드 — efficientnet으로 폴백
        logger.warning(f"Unknown IDENTIFIER_MODE={mode}, falling back to efficientnet")
        return [
            BatchImageResult(image_path=image_paths[idx], error=errors[idx])
            if errors[idx]
            else BatchImageResult(
                image_path=image_paths[idx],
                result=IdentificationResult(
                    status="low_confidence",
                    confidence=0.0,
                    message=f"알 수 없는 모드: {mode}",
                    detection=detections[idx],
                    image_width=sizes[idx][0],
                    image_height=sizes[idx][1],
                ),
            )
            for idx in range(n)
        ]

