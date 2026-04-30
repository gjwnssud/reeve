"""
Vision 백엔드 추상화
Protocol + Factory 패턴으로 OpenAI / Ollama / Dual(OpenAI+Gemini) 전환 지원
"""
import asyncio
import logging
from typing import Protocol, Dict, Optional, runtime_checkable
from sqlalchemy.orm import Session

from studio.config import settings

logger = logging.getLogger(__name__)


@runtime_checkable
class VisionBackend(Protocol):
    """Vision 분석 백엔드 인터페이스"""

    async def analyze_vehicle_image(
        self, image_path: str, additional_context: Optional[str] = None, db: Optional[Session] = None
    ) -> Dict:
        """
        차량 이미지 분석

        Returns:
            {
                "manufacturer_code": str,
                "model_code": str,
                "confidence": float,
                "raw_response": str,
            }
        """
        ...


class DualVisionService:
    """
    OpenAI + Gemini 교차 검증 Vision 서비스

    두 API 결과가 일치할 때만 성공으로 판정.
    어느 한쪽 실패 또는 결과 불일치 시 예외 발생.
    """

    def __init__(self):
        from studio.services.openai_vision import OpenAIVisionService
        from studio.services.gemini_vision import GeminiVisionService
        self._openai = OpenAIVisionService()
        self._gemini = GeminiVisionService()

    async def analyze_vehicle_image(
        self, image_path: str, additional_context: Optional[str] = None, db: Optional[Session] = None
    ) -> Dict:
        # 두 API 병렬 호출
        openai_result, gemini_result = await asyncio.gather(
            self._openai.analyze_vehicle_image(image_path, additional_context, db),
            self._gemini.analyze_vehicle_image(image_path, additional_context, db),
            return_exceptions=True,
        )

        openai_failed = isinstance(openai_result, Exception)
        gemini_failed = isinstance(gemini_result, Exception)

        if openai_failed and gemini_failed:
            raise ValueError(f"두 API 모두 실패 - OpenAI: {openai_result}, Gemini: {gemini_result}")
        if openai_failed:
            raise ValueError(f"ChatGPT API 실패: {openai_result}")
        if gemini_failed:
            raise ValueError(f"Gemini API 실패: {gemini_result}")

        openai_mf = openai_result.get("manufacturer_code")
        openai_mdl = openai_result.get("model_code")
        gemini_mf = gemini_result.get("manufacturer_code")
        gemini_mdl = gemini_result.get("model_code")

        if openai_mf != gemini_mf or openai_mdl != gemini_mdl:
            raise ValueError(
                f"API 결과 불일치 - ChatGPT: {openai_mf}/{openai_mdl}, Gemini: {gemini_mf}/{gemini_mdl}"
            )

        logger.info(f"교차 검증 성공: {openai_mf}/{openai_mdl}")
        # OpenAI 결과를 기반으로 반환 (calibrated confidence 평균 적용)
        avg_confidence = round((
            float(openai_result.get("confidence") or 0.0) +
            float(gemini_result.get("confidence") or 0.0)
        ) / 2, 3)
        combined_evidence = " | ".join(filter(None, [
            openai_result.get("visual_evidence", ""),
            gemini_result.get("visual_evidence", ""),
        ]))
        return {
            **openai_result,
            "confidence": avg_confidence,
            "visual_evidence": combined_evidence,
            "gemini_confidence": gemini_result.get("confidence"),
            "dual_verified": True,
        }

    def preload_db_context(self, db) -> None:
        """Vision 프롬프트용 DB 데이터를 두 백엔드에 캐싱"""
        self._openai.preload_db_context(db)
        self._gemini.preload_db_context(db)


_dual_vision_service: Optional[DualVisionService] = None


def get_vision_backend() -> VisionBackend:
    """설정에 따라 Vision 백엔드 인스턴스 반환"""
    global _dual_vision_service
    if settings.vision_backend == "ollama":
        from studio.services.ollama_vision import ollama_vision_service
        return ollama_vision_service
    elif settings.vision_backend == "local_inference":
        from studio.services.local_inference_vision import local_inference_vision_service
        return local_inference_vision_service
    elif settings.openai_api_key and settings.gemini_api_key:
        # 두 API 키가 모두 설정된 경우 교차 검증 모드 (싱글턴)
        if _dual_vision_service is None:
            _dual_vision_service = DualVisionService()
        return _dual_vision_service
    else:
        from studio.services.openai_vision import vision_service
        return vision_service
