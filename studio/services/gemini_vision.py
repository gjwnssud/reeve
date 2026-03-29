"""
Google Gemini Vision API 서비스
차량 이미지 분석 (OpenAI와 교차 검증용)
"""
import base64
import json
import asyncio
from pathlib import Path
from typing import Dict, Optional
import logging
from sqlalchemy.orm import Session

from studio.config import settings

logger = logging.getLogger(__name__)


class GeminiVisionService:
    """Google Gemini Vision API를 사용한 차량 이미지 분석"""

    def __init__(self, db: Optional[Session] = None):
        if not settings.gemini_api_key:
            logger.warning("Gemini API key not configured")
            self.client = None
        else:
            try:
                import google.generativeai as genai
                genai.configure(api_key=settings.gemini_api_key)
                self.client = genai.GenerativeModel(settings.gemini_model)
            except ImportError:
                logger.error("google-generativeai 패키지가 설치되어 있지 않습니다.")
                self.client = None

        self.db = db
        self._manufacturer_cache = None
        self._model_cache = None

    def encode_image(self, image_path: str) -> bytes:
        """이미지를 바이트로 읽기"""
        with open(image_path, "rb") as f:
            return f.read()

    def _get_manufacturers_from_db(self) -> Dict:
        """DB에서 제조사 목록 가져오기 (OpenAIVisionService와 동일 로직)"""
        if self._manufacturer_cache:
            return self._manufacturer_cache

        if not self.db:
            return {
                "국산": [
                    {"code": "hyundai", "korean_name": "현대", "english_name": "Hyundai", "description": "현대자동차 (국내 생산)"},
                    {"code": "kia", "korean_name": "기아", "english_name": "Kia", "description": "기아자동차 (국내 생산)"},
                    {"code": "genesis", "korean_name": "제네시스", "english_name": "Genesis", "description": "제네시스 (현대 프리미엄 브랜드)"},
                    {"code": "ssangyong", "korean_name": "쌍용", "english_name": "SsangYong", "description": "쌍용자동차 (국내 생산)"},
                    {"code": "renaultkorea", "korean_name": "르노코리아", "english_name": "Renault Korea", "description": "르노코리아 (국내 생산)"},
                    {"code": "chevrolet_gmdaewoo", "korean_name": "쉐보레(한국GM)", "english_name": "Chevrolet (GM Korea)", "description": "한국GM (국내 생산) - 스파크, 트랙스, 말리부 등"}
                ],
                "수입": [
                    {"code": "chevrolet", "korean_name": "쉐보레(수입)", "english_name": "Chevrolet (Import)", "description": "쉐보레 수입 차량"},
                    {"code": "bmw", "korean_name": "BMW", "english_name": "BMW", "description": "BMW (독일)"},
                    {"code": "mercedesbenz", "korean_name": "메르세데스-벤츠", "english_name": "Mercedes-Benz", "description": "메르세데스-벤츠 (독일)"},
                    {"code": "audi", "korean_name": "아우디", "english_name": "Audi", "description": "아우디 (독일)"},
                    {"code": "volkswagen", "korean_name": "폭스바겐", "english_name": "Volkswagen", "description": "폭스바겐 (독일)"},
                    {"code": "toyota", "korean_name": "토요타", "english_name": "Toyota", "description": "토요타 (일본)"},
                    {"code": "honda", "korean_name": "혼다", "english_name": "Honda", "description": "혼다 (일본)"},
                    {"code": "tesla", "korean_name": "테슬라", "english_name": "Tesla", "description": "테슬라 (미국)"},
                    {"code": "ford", "korean_name": "포드", "english_name": "Ford", "description": "포드 (미국)"}
                ]
            }

        try:
            from studio.models.manufacturer import Manufacturer
            manufacturers = self.db.query(Manufacturer).all()
            result = {"국산": [], "수입": []}
            for mf in manufacturers:
                item = {
                    "code": mf.code.lower(),
                    "korean_name": mf.korean_name,
                    "english_name": mf.english_name,
                    "description": f"{mf.korean_name} ({mf.english_name})"
                }
                if mf.is_domestic:
                    result["국산"].append(item)
                else:
                    result["수입"].append(item)
            self._manufacturer_cache = result
            return result
        except Exception as e:
            logger.warning(f"Failed to load manufacturers from DB: {e}")
            return self._get_manufacturers_from_db()

    def _get_popular_models_from_db(self, limit: int = 30):
        """DB에서 인기 모델 목록 가져오기"""
        if self._model_cache:
            return self._model_cache

        if not self.db:
            return [
                {"code": "sonata", "korean_name": "쏘나타"},
                {"code": "k5", "korean_name": "K5"},
                {"code": "avante", "korean_name": "아반떼"},
                {"code": "grandeur", "korean_name": "그랜저"},
                {"code": "carnival", "korean_name": "카니발"},
            ]

        try:
            from studio.models.vehicle_model import VehicleModel
            models = self.db.query(VehicleModel).order_by(VehicleModel.id.desc()).limit(limit).all()
            result = [{"code": m.code.lower(), "korean_name": m.korean_name} for m in models if m.code and m.korean_name]
            self._model_cache = result
            return result
        except Exception as e:
            logger.warning(f"Failed to load models from DB: {e}")
            return []

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """OpenAIVisionService와 동일한 프롬프트 생성"""
        manufacturers = self._get_manufacturers_from_db()
        popular_models = self._get_popular_models_from_db(limit=20)

        manufacturer_lines = []
        for category, brands in manufacturers.items():
            manufacturer_lines.append(f'\n**{category}**:')
            for b in brands:
                manufacturer_lines.append(f'   - code: "{b["code"]}" | {b["description"]}')
        manufacturer_text = '\n'.join(manufacturer_lines)

        model_items = [f'{{code: "{m["code"]}", name: "{m["korean_name"]}"}}' for m in popular_models[:20]]
        model_examples = ', '.join(model_items)

        base_prompt = f"""이미지에서 차량의 제조사와 모델을 정확하게 식별해주세요.

**매우 중요**: 반드시 아래의 정확한 JSON 형식으로만 답변해주세요. 다른 텍스트는 포함하지 마세요.

{{
  "manufacturer_code": "hyundai",
  "model_code": "casper",
  "confidence": 0.95
}}

**식별 규칙**:
1. manufacturer_code: 아래 목록에서 정확한 **code 값(소문자 영문)**을 사용하세요.
{manufacturer_text}

**중요**: 동일 브랜드에 국산/수입 구분이 있는 경우 (예: 쉐보레):
- 국내 생산 차량 (스파크, 트랙스, 말리부 등) → "chevrolet_gmdaewoo"
- 수입 차량 (카마로, 콜벳 등) → "chevrolet"

2. model_code: 구체적인 모델의 **code 값(소문자 영문)**을 사용하세요.
   - 예시: {model_examples}
   - 목록에 없는 모델인 경우: 영문 모델명을 소문자로 변환하여 사용 (공백 제거)

3. confidence: 제조사와 모델 식별의 확실성 정도 (0.0~1.0)

**식별 불가능한 경우**:
{{
  "manufacturer_code": "unknown",
  "model_code": "unknown",
  "confidence": 0.1
}}

**중요**: manufacturer_code와 model_code는 반드시 소문자 영문으로만 작성하세요.
"""
        if additional_context:
            base_prompt += f"\n\n**추가 컨텍스트**:\n{additional_context}"
        return base_prompt

    def _parse_response(self, content: str) -> Dict:
        """Gemini 응답 파싱"""
        result = {
            "manufacturer_code": None,
            "model_code": None,
            "confidence": 0.0,
            "raw_response": content
        }

        try:
            json_content = content.strip()
            if "```json" in json_content:
                json_content = json_content.split("```json")[1].split("```")[0].strip()
            elif "```" in json_content:
                json_content = json_content.split("```")[1].split("```")[0].strip()

            data = json.loads(json_content)
            manufacturer_code = data.get("manufacturer_code", "").lower()
            model_code = data.get("model_code", "").lower()

            result["manufacturer_code"] = manufacturer_code if manufacturer_code not in ["", "unknown", "알 수 없음"] else None
            result["model_code"] = model_code if model_code not in ["", "unknown", "알 수 없음"] else None
            result["confidence"] = float(data.get("confidence", 0.0))

            logger.info(f"Gemini JSON 파싱 성공: {result}")
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Gemini JSON 파싱 실패: {e}")

        return result

    async def analyze_vehicle_image(
        self,
        image_path: str,
        additional_context: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict:
        """차량 이미지 분석"""
        if not self.client:
            raise ValueError("Gemini API key not configured")

        if db:
            self.db = db

        try:
            image_bytes = self.encode_image(image_path)
            prompt = self._build_prompt(additional_context)

            import google.generativeai as genai

            # 이미지 파트 구성
            ext = Path(image_path).suffix.lower().lstrip(".")
            mime_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
            image_part = {"mime_type": mime_type, "data": image_bytes}

            # Gemini API 호출 (스레드풀 - 동기 SDK)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.generate_content([prompt, image_part])
            )

            content = response.text.strip()
            result = self._parse_response(content)

            logger.info(f"Gemini 이미지 분석 완료: {image_path}")
            return result

        except Exception as e:
            logger.error(f"Gemini 이미지 분석 오류 {image_path}: {e}")
            raise
