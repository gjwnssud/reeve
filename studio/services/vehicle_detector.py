"""
차량 감지 서비스
YOLO26을 사용한 이미지 내 차량 영역 탐지
"""
import cv2
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
from ultralytics import YOLO
from studio.config import settings

logger = logging.getLogger(__name__)


class VehicleDetector:
    """YOLO26 기반 차량 감지"""

    # COCO 데이터셋의 차량 관련 클래스
    VEHICLE_CLASSES = {
        2: 'car',
        3: 'motorcycle',
        5: 'bus',
        7: 'truck'
    }

    def __init__(self, model_size: str = 'n'):
        """
        초기화

        Args:
            model_size: YOLO26 모델 크기 (n, s, m, l, x)
                - n: nano (가장 빠름, 정확도 낮음)
                - s: small
                - m: medium (권장)
                - l: large
                - x: extra large (가장 느림, 정확도 높음)
        """
        self.model_size = model_size
        self.model = None
        self._load_model()

    def _load_model(self):
        """YOLO26 모델 로드"""
        try:
            model_name = f"yolo26{self.model_size}.pt"
            device = settings.embedding_device if settings.embedding_device != "cpu" else None
            logger.info(f"Loading YOLO26 model: {model_name} (device={device or 'cpu'})")

            self.model = YOLO(model_name)
            if device:
                self.model.to(device)
            logger.info("YOLO26 model loaded successfully")

        except Exception as e:
            logger.error(f"Failed to load YOLO26 model: {e}")
            raise

    def detect_vehicles(
        self,
        image_path: str,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45
    ) -> List[Dict]:
        """
        이미지에서 차량 감지

        Args:
            image_path: 이미지 파일 경로
            confidence_threshold: 신뢰도 임계값 (0-1)
            iou_threshold: NMS IOU 임계값

        Returns:
            감지된 차량 정보 리스트
            [
                {
                    "bbox": [x1, y1, x2, y2],  # 바운딩 박스 좌표
                    "confidence": 0.95,
                    "class_id": 2,
                    "class_name": "car",
                    "area": 50000  # 박스 면적 (픽셀)
                },
                ...
            ]
        """
        if not self.model:
            raise RuntimeError("Model not loaded")

        try:
            # 이미지 읽기
            image = cv2.imread(image_path)
            if image is None:
                raise ValueError(f"Failed to load image: {image_path}")

            # YOLO 추론
            results = self.model.predict(
                image,
                conf=confidence_threshold,
                iou=iou_threshold,
                classes=list(self.VEHICLE_CLASSES.keys()),  # 차량 클래스만 감지
                verbose=False
            )

            # 결과 파싱
            detections = []

            if len(results) > 0 and results[0].boxes is not None:
                boxes = results[0].boxes

                for i in range(len(boxes)):
                    box = boxes[i]

                    # 바운딩 박스 좌표 (x1, y1, x2, y2)
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0].cpu().numpy())
                    class_id = int(box.cls[0].cpu().numpy())

                    # 면적 계산
                    area = (x2 - x1) * (y2 - y1)

                    detections.append({
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": round(confidence, 3),
                        "class_id": class_id,
                        "class_name": self.VEHICLE_CLASSES.get(class_id, "unknown"),
                        "area": int(area)
                    })

            # 면적 기준 내림차순 정렬 (가장 큰 차량이 먼저)
            detections.sort(key=lambda x: x["area"], reverse=True)

            logger.info(f"Detected {len(detections)} vehicles in {image_path}")
            return detections

        except Exception as e:
            logger.error(f"Vehicle detection failed for {image_path}: {e}")
            raise

    def crop_vehicle(
        self,
        image_path: str,
        bbox: List[int],
        padding: int = 10
    ) -> np.ndarray:
        """
        바운딩 박스 영역을 크롭

        Args:
            image_path: 원본 이미지 경로
            bbox: [x1, y1, x2, y2] 바운딩 박스
            padding: 크롭 시 추가할 여백 (픽셀)

        Returns:
            크롭된 이미지 (numpy array)
        """
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")

        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox

        # 패딩 적용 (이미지 경계를 넘지 않도록)
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(w, x2 + padding)
        y2 = min(h, y2 + padding)

        cropped = image[y1:y2, x1:x2]
        return cropped

    def save_cropped_image(
        self,
        image_path: str,
        bbox: List[int],
        output_path: str,
        padding: int = 10
    ) -> str:
        """
        크롭된 이미지를 파일로 저장

        Args:
            image_path: 원본 이미지 경로
            bbox: [x1, y1, x2, y2] 바운딩 박스
            output_path: 저장할 경로
            padding: 크롭 시 추가할 여백

        Returns:
            저장된 파일 경로
        """
        cropped = self.crop_vehicle(image_path, bbox, padding)

        # 디렉토리 생성
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        # 저장
        cv2.imwrite(output_path, cropped)
        logger.info(f"Cropped image saved to {output_path}")

        return output_path

    def draw_detections(
        self,
        image_path: str,
        detections: List[Dict],
        output_path: Optional[str] = None
    ) -> np.ndarray:
        """
        감지된 차량에 바운딩 박스 그리기

        Args:
            image_path: 원본 이미지 경로
            detections: detect_vehicles() 결과
            output_path: 저장할 경로 (None이면 저장 안 함)

        Returns:
            바운딩 박스가 그려진 이미지
        """
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Failed to load image: {image_path}")

        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            confidence = det["confidence"]
            class_name = det["class_name"]

            # 바운딩 박스 그리기
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # 레이블 텍스트
            label = f"{class_name} {confidence:.2f}"

            # 텍스트 배경
            (text_width, text_height), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
            )
            cv2.rectangle(
                image,
                (x1, y1 - text_height - 10),
                (x1 + text_width, y1),
                (0, 255, 0),
                -1
            )

            # 텍스트
            cv2.putText(
                image,
                label,
                (x1, y1 - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 0),
                2
            )

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(output_path, image)
            logger.info(f"Detection visualization saved to {output_path}")

        return image


# 전역 인스턴스 (싱글톤)
_detector_instance = None

def get_vehicle_detector(model_size: str = 'm') -> VehicleDetector:
    """
    VehicleDetector 싱글톤 인스턴스 반환

    Args:
        model_size: YOLO26 모델 크기 (n, s, m, l, x)
    """
    global _detector_instance

    if _detector_instance is None:
        _detector_instance = VehicleDetector(model_size=model_size)

    return _detector_instance
