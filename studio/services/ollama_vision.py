"""
Ollama Vision 서비스
폐쇄망 환경에서 Ollama 기반 차량 이미지 분석
openai_vision.py와 동일한 응답 스키마 보장
"""
import base64
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List

import httpx
from sqlalchemy.orm import Session

from studio.config import settings

logger = logging.getLogger(__name__)


class OllamaVisionService:
    """Ollama 기반 Vision 분석 서비스"""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.studio_vlm_model
        self.timeout = settings.studio_vlm_timeout
        self.db = None
        self._manufacturer_cache = None
        self._model_cache = None

    def _encode_image(self, image_path: str) -> str:
        """이미지를 base64로 인코딩"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_manufacturers_from_db(self) -> Dict[str, List[Dict[str, str]]]:
        """DB에서 제조사 목록 조회 (openai_vision.py와 동일 로직)"""
        if self._manufacturer_cache:
            return self._manufacturer_cache

        if not self.db:
            return {"국산": [], "수입": []}

        try:
            from studio.models.manufacturer import Manufacturer
            manufacturers = self.db.query(Manufacturer).all()
            result = {"국산": [], "수입": []}
            for mf in manufacturers:
                item = {
                    "code": mf.code.lower(),
                    "korean_name": mf.korean_name,
                    "english_name": mf.english_name,
                }
                if mf.is_domestic:
                    result["국산"].append(item)
                else:
                    result["수입"].append(item)
            self._manufacturer_cache = result
            return result
        except Exception as e:
            logger.warning(f"Failed to load manufacturers from DB: {e}")
            return {"국산": [], "수입": []}

    def _get_popular_models_from_db(self, limit: int = 30) -> List[Dict[str, str]]:
        """DB에서 모델 목록 조회"""
        if self._model_cache:
            return self._model_cache

        if not self.db:
            return []

        try:
            from studio.models.vehicle_model import VehicleModel
            models = self.db.query(VehicleModel).order_by(VehicleModel.id.desc()).limit(limit).all()
            result = [
                {"code": m.code.lower(), "korean_name": m.korean_name, "english_name": m.english_name}
                for m in models if m.code and (m.korean_name or m.english_name)
            ]
            self._model_cache = result
            return result
        except Exception as e:
            logger.warning(f"Failed to load models from DB: {e}")
            return []

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """분석용 프롬프트 생성 (openai_vision.py와 동일 구조)"""
        manufacturers = self._get_manufacturers_from_db()
        popular_models = self._get_popular_models_from_db(limit=20)

        manufacturer_lines = []
        for category, brands in manufacturers.items():
            if brands:
                manufacturer_lines.append(f"\n**{category}**:")
                for b in brands:
                    manufacturer_lines.append(f'   - code: "{b["code"]}" | {b["korean_name"]} ({b["english_name"]})')
        manufacturer_text = "\n".join(manufacturer_lines)

        model_items = [f'{{code: "{m["code"]}", name: "{m["korean_name"]}"}}' for m in popular_models[:20]]
        model_examples = ", ".join(model_items)

        prompt = f"""이미지에서 차량의 제조사와 모델을 정확하게 식별해주세요.

반드시 아래의 정확한 JSON 형식으로만 답변해주세요. 다른 텍스트는 포함하지 마세요.

{{"manufacturer_code": "hyundai", "model_code": "casper", "confidence": 0.95}}

식별 규칙:
1. manufacturer_code: 아래 목록에서 정확한 code 값(소문자 영문)을 사용하세요.
{manufacturer_text}

2. model_code: 구체적인 모델의 code 값(소문자 영문)을 사용하세요.
   - 예시: {model_examples}
   - 목록에 없는 모델: 영문 소문자, 공백 제거 (예: "Model 3" → "model3")

3. confidence: 식별 확실성 (0.0~1.0)

식별 불가능한 경우:
{{"manufacturer_code": "unknown", "model_code": "unknown", "confidence": 0.1}}

중요: manufacturer_code와 model_code는 반드시 소문자 영문으로만 작성하세요."""

        if additional_context:
            prompt += f"\n\n추가 컨텍스트:\n{additional_context}"

        return prompt

    async def analyze_vehicle_image(
        self,
        image_path: str,
        additional_context: Optional[str] = None,
        db: Optional[Session] = None,
    ) -> Dict:
        """
        차량 이미지 분석 (Ollama API)

        Returns:
            openai_vision.py와 동일한 스키마:
            {manufacturer_code, model_code, confidence, raw_response}
        """
        if db:
            self.db = db

        try:
            base64_image = self._encode_image(image_path)
            prompt = self._build_prompt(additional_context)

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert automotive analyst. "
                                    "Always respond with valid JSON only. No explanations, no markdown."
                                ),
                            },
                            {
                                "role": "user",
                                "content": prompt,
                                "images": [base64_image],
                            },
                        ],
                        "format": "json",
                        "stream": False,
                        "options": {"temperature": 0},
                    },
                )
                response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "").strip()

            return self._parse_response(content)

        except httpx.TimeoutException:
            logger.error(f"Ollama request timed out for {image_path}")
            raise ValueError(f"Ollama 요청 타임아웃 ({self.timeout}초)")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise ValueError(f"Ollama 서버 오류: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Ollama analysis failed for {image_path}: {e}")
            raise

    def _parse_response(self, content: str) -> Dict:
        """Ollama 응답 파싱 → openai_vision.py와 동일 스키마"""
        result = {
            "manufacturer_code": None,
            "model_code": None,
            "confidence": 0.0,
            "raw_response": content,
        }

        try:
            # JSON 코드 블록 제거
            json_content = content
            if "```json" in json_content:
                json_content = json_content.split("```json")[1].split("```")[0].strip()
            elif "```" in json_content:
                json_content = json_content.split("```")[1].split("```")[0].strip()

            data = json.loads(json_content)

            manufacturer_code = data.get("manufacturer_code", "").lower()
            model_code = data.get("model_code", "").lower()

            result["manufacturer_code"] = manufacturer_code if manufacturer_code not in ("", "unknown") else None
            result["model_code"] = model_code if model_code not in ("", "unknown") else None
            result["confidence"] = float(data.get("confidence", 0.0))

            logger.info(f"Ollama 파싱 성공: {result}")

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Ollama JSON 파싱 실패: {e}, content: {content[:200]}")

        return result

    def preload_db_context(self, db: Session) -> None:
        """Vision 프롬프트용 DB 데이터를 캐싱 (커넥션 반환 전 호출)"""
        self.db = db
        self._get_manufacturers_from_db()
        self._get_popular_models_from_db()
        self.db = None


# 전역 인스턴스
ollama_vision_service = OllamaVisionService()
