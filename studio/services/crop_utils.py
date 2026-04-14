"""크롭 이미지 보장 유틸.

학습 데이터로 적재되는 모든 경로에서 image_path가 반드시 bbox 크롭 이미지를
가리키도록 보장한다. 원본 경로가 들어있고 bbox 정보가 있으면 즉석에서 크롭을
생성하고 DB 필드를 갱신한다.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2

from studio.models.analyzed_vehicle import AnalyzedVehicle

logger = logging.getLogger(__name__)


def _pick_bbox(analyzed: AnalyzedVehicle) -> Optional[list]:
    if analyzed.selected_bbox:
        return analyzed.selected_bbox
    if analyzed.yolo_detections:
        first = analyzed.yolo_detections[0]
        if isinstance(first, dict) and first.get("bbox"):
            return first["bbox"]
    return None


def ensure_cropped_image(analyzed: AnalyzedVehicle) -> bool:
    """analyzed.image_path가 원본 경로면 bbox로 크롭 생성 후 image_path 갱신.

    호출자가 db.commit() 해야 변경 사항이 영속화된다.

    Returns:
        True  - 이미 크롭이거나 새로 크롭을 생성해 갱신 성공
        False - bbox 부재 / 원본 누락 / 크롭 실패 → image_path 미변경
    """
    if not analyzed.image_path or not analyzed.original_image_path:
        return False
    if analyzed.image_path != analyzed.original_image_path:
        return True

    bbox = _pick_bbox(analyzed)
    if not bbox:
        return False

    src = analyzed.original_image_path
    if not os.path.exists(src):
        logger.warning(f"ensure_cropped_image: 원본 이미지 없음 - {src}")
        return False

    image = cv2.imread(src)
    if image is None:
        logger.warning(f"ensure_cropped_image: 이미지 로드 실패 - {src}")
        return False

    h, w = image.shape[:2]
    try:
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
    except (TypeError, ValueError, IndexError):
        logger.warning(f"ensure_cropped_image: bbox 파싱 실패 - {bbox}")
        return False

    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        logger.warning(f"ensure_cropped_image: 유효하지 않은 bbox {bbox} (이미지 {w}x{h})")
        return False

    cropped = image[y1:y2, x1:x2]
    if cropped.size == 0:
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    crop_dir = Path(f"data/crops/{date_str}")
    crop_dir.mkdir(parents=True, exist_ok=True)
    crop_path = crop_dir / f"{os.urandom(16).hex()}_crop.jpg"
    if not cv2.imwrite(str(crop_path), cropped):
        logger.warning(f"ensure_cropped_image: 크롭 파일 저장 실패 - {crop_path}")
        return False

    analyzed.image_path = str(crop_path)
    analyzed.selected_bbox = bbox
    return True
