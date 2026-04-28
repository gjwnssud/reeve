"""
자체 추론 API Vision 서비스

VISION_BACKEND=local_inference 일 때 사용.
외부 추론 API(POST /infer)에 multipart/form-data로 이미지를 보내고
{vehicles[], count, inference_time_ms} 응답을 받아 VisionBackend Protocol 스키마로 정규화한다.

기존 OpenAI/Gemini/Ollama 백엔드와 달리 자체 API는 내부에서 YOLO+분류를 모두 수행하므로
Studio가 별도 YOLO를 돌리지 않는다. 응답의 vehicles[i].bbox를 selected_bbox로 사용한다.
제조사/모델은 한글명으로 반환되며, 그대로 raw 결과의 manufacturer_code/model_code에 매핑된다.
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import httpx
from sqlalchemy.orm import Session

from studio.config import settings

logger = logging.getLogger(__name__)


class LocalInferenceVisionService:
    """자체 추론 API 기반 Vision 분석 서비스"""

    def __init__(self):
        self.base_url = settings.local_inference_url.rstrip("/")
        self.timeout = settings.local_inference_timeout

    async def analyze_vehicle_image(
        self,
        image_path: str,
        additional_context: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict:
        """원본 이미지를 자체 추론 API에 전달하고 결과를 정규화해 반환"""
        url = f"{self.base_url}/infer"
        path = Path(image_path)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                with open(path, "rb") as f:
                    files = {"file": (path.name, f, "image/jpeg")}
                    response = await client.post(url, files=files)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"자체 추론 API 호출 실패 ({url}): {e}")
            raise ValueError(f"자체 추론 API 호출 실패: {e}") from e

        vehicles = data.get("vehicles") or []
        raw_response = json.dumps(data, ensure_ascii=False)

        if not vehicles:
            logger.warning(f"자체 추론 API에서 차량을 탐지하지 못함: {path.name}")
            return {
                "manufacturer_code": None,
                "model_code": None,
                "confidence": 0.0,
                "raw_response": raw_response,
                "_local_inference": True,
                "selected_bbox": None,
                "visual_evidence": "",
            }

        # classification_confidence 최댓값 1대만 선택
        best = max(
            vehicles,
            key=lambda v: float(v.get("classification_confidence") or 0.0),
        )
        bb = best.get("bbox") or {}
        x = int(bb.get("x", 0))
        y = int(bb.get("y", 0))
        w = int(bb.get("w", 0))
        h = int(bb.get("h", 0))
        # 자체 API의 {x,y,w,h} → 기존 코드 호환 [x1,y1,x2,y2]로 변환
        selected_bbox = [x, y, x + w, y + h]

        manufacturer = best.get("manufacturer")
        model = best.get("model")
        cls_conf = float(best.get("classification_confidence") or 0.0)
        det_conf = float(best.get("detection_confidence") or 0.0)

        logger.info(
            f"자체 추론 결과: {manufacturer}/{model} "
            f"(cls={cls_conf:.3f}, det={det_conf:.3f}, vehicles={len(vehicles)})"
        )

        return {
            "manufacturer_code": manufacturer,
            "model_code": model,
            "confidence": cls_conf,
            "raw_response": raw_response,
            "_local_inference": True,
            "selected_bbox": selected_bbox,
            "vehicle_type": best.get("vehicle_type"),
            "detection_confidence": det_conf,
            "inference_time_ms": data.get("inference_time_ms"),
            "visual_evidence": "",
        }

    def preload_db_context(self, db: Session) -> None:
        """자체 추론 API는 프롬프트 컨텍스트 주입이 없으므로 no-op"""
        return None


# 전역 인스턴스
local_inference_vision_service = LocalInferenceVisionService()
