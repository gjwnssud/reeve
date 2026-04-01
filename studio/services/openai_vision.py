"""
OpenAI Vision API 서비스
차량 이미지 분석 (Phase 1 - 개발 환경)
"""
import base64
import json
import asyncio
from pathlib import Path
from typing import Dict, Optional, List
import logging
from openai import OpenAI, RateLimitError
from sqlalchemy.orm import Session

from studio.config import settings

logger = logging.getLogger(__name__)


class OpenAIVisionService:
    """OpenAI Vision API를 사용한 차량 이미지 분석"""

    def __init__(self, db: Optional[Session] = None):
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured")
            self.client = None
        else:
            self.client = OpenAI(api_key=settings.openai_api_key)

        self.db = db
        self._manufacturer_cache = None
        self._model_cache = None

    def encode_image(self, image_path: str) -> str:
        """이미지를 base64로 인코딩"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def _get_manufacturers_from_db(self) -> Dict[str, List[Dict[str, str]]]:
        """DB에서 제조사 목록을 가져와서 국가별로 분류 (code 포함)"""
        if self._manufacturer_cache:
            return self._manufacturer_cache

        if not self.db:
            # DB 없으면 기본값 반환
            return {
                "국산": [
                    {"code": "hyundai", "korean_name": "현대", "english_name": "Hyundai", "description": "현대자동차 (국내 생산)"},
                    {"code": "kia", "korean_name": "기아", "english_name": "Kia", "description": "기아자동차 (국내 생산)"},
                    {"code": "genesis", "korean_name": "제네시스", "english_name": "Genesis", "description": "제네시스 (현대 프리미엄 브랜드)"},
                    {"code": "ssangyong", "korean_name": "쌍용", "english_name": "SsangYong", "description": "쌍용자동차 (국내 생산)"},
                    {"code": "renaultkorea", "korean_name": "르노코리아", "english_name": "Renault Korea", "description": "르노코리아 (구 르노삼성, 국내 생산)"},
                    {"code": "chevrolet_gmdaewoo", "korean_name": "쉐보레(한국GM)", "english_name": "Chevrolet (GM Korea)", "description": "한국GM (구 대우, 국내 생산) - 스파크, 트랙스, 말리부 등"}
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

            # DB에서 모든 제조사 조회
            manufacturers = self.db.query(Manufacturer).all()

            # 국내/해외 분류
            result = {
                "국산": [],
                "수입": []
            }

            for mf in manufacturers:
                item = {
                    "code": mf.code.lower(),  # 소문자 코드
                    "korean_name": mf.korean_name,
                    "english_name": mf.english_name,
                    "description": f"{mf.korean_name} ({mf.english_name})"
                }

                # is_domestic 기준으로 분류
                if mf.is_domestic:
                    result["국산"].append(item)
                else:
                    result["수입"].append(item)

            self._manufacturer_cache = result
            return result

        except Exception as e:
            logger.warning(f"Failed to load manufacturers from DB: {e}")
            # 오류 시 기본값 반환 (위의 기본값 사용)
            return self._get_manufacturers_from_db()

    def _get_popular_models_from_db(self, limit: int = 30) -> List[Dict[str, str]]:
        """DB에서 인기 모델 목록을 가져오기 (code 포함)"""
        if self._model_cache:
            return self._model_cache

        if not self.db:
            # DB 없으면 기본값 반환
            return [
                {"code": "sonata", "korean_name": "쏘나타", "english_name": "Sonata"},
                {"code": "k5", "korean_name": "K5", "english_name": "K5"},
                {"code": "spark", "korean_name": "스파크", "english_name": "Spark"},
                {"code": "avante", "korean_name": "아반떼", "english_name": "Avante"},
                {"code": "grandeur", "korean_name": "그랜저", "english_name": "Grandeur"},
                {"code": "carnival", "korean_name": "카니발", "english_name": "Carnival"},
                {"code": "3series", "korean_name": "3시리즈", "english_name": "3 Series"},
                {"code": "sclass", "korean_name": "S클래스", "english_name": "S-Class"},
                {"code": "a6", "korean_name": "A6", "english_name": "A6"},
                {"code": "golf", "korean_name": "골프", "english_name": "Golf"}
            ]

        try:
            from studio.models.vehicle_model import VehicleModel

            # DB에서 모델 조회 (최근 등록순 또는 이름순)
            models = self.db.query(VehicleModel).order_by(VehicleModel.id.desc()).limit(limit).all()

            result = [{
                "code": m.code.lower(),  # 소문자 코드
                "korean_name": m.korean_name,
                "english_name": m.english_name
            } for m in models if m.code and (m.korean_name or m.english_name)]

            self._model_cache = result
            return result

        except Exception as e:
            logger.warning(f"Failed to load models from DB: {e}")
            # 오류 시 기본값 사용
            return self._get_popular_models_from_db.__defaults__[0]

    async def analyze_vehicle_image(
        self,
        image_path: str,
        additional_context: Optional[str] = None,
        db: Optional[Session] = None
    ) -> Dict:
        """
        차량 이미지 분석

        Args:
            image_path: 분석할 이미지 경로
            additional_context: 추가 컨텍스트 정보
            db: 데이터베이스 세션

        Returns:
            분석 결과 딕셔너리
            {
                "manufacturer_code": "hyundai",
                "model_code": "casper",
                "confidence": 0.95,
                "raw_response": {...}
            }
        """
        if not self.client:
            raise ValueError("OpenAI API key not configured")

        # DB 세션 설정 (인스턴스에 없으면 파라미터에서 사용)
        if db:
            self.db = db

        try:
            # 이미지 인코딩
            base64_image = self.encode_image(image_path)

            # 프롬프트 구성 (DB 데이터 기반)
            prompt = self._build_prompt(additional_context)

            # Vision API 호출 (재시도 로직 포함)
            max_retries = 3
            retry_delay = 2  # 초기 대기 시간 (초)

            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=settings.openai_model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are an expert automotive analyst specializing in vehicle make and model identification. "
                                    "You have extensive knowledge of all vehicle manufacturers and models worldwide, "
                                    "including subtle design differences between trim levels and model years. "
                                    "Always respond with valid JSON only. No explanations, no markdown, just the JSON object."
                                )
                            },
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": prompt
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}",
                                            "detail": "high"
                                        }
                                    }
                                ]
                            }
                        ],
                        max_completion_tokens=500,
                    )
                    break  # 성공 시 루프 탈출

                except RateLimitError as e:
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # 지수 백오프: 2s, 4s, 8s
                        logger.warning(f"Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Rate limit exceeded after {max_retries} attempts")
                        raise

            # 응답 파싱
            result = self._parse_response(response)

            logger.info(f"Image analysis completed: {image_path}")
            return result

        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {e}")
            raise

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """분석용 프롬프트 생성 (DB 데이터 기반)"""
        # DB에서 제조사/모델 목록 가져오기
        manufacturers = self._get_manufacturers_from_db()
        popular_models = self._get_popular_models_from_db(limit=20)

        # 제조사 목록 포맷팅 (code 포함, 설명 추가)
        manufacturer_lines = []
        for category, brands in manufacturers.items():
            manufacturer_lines.append(f'\n**{category}**:')
            for b in brands:
                manufacturer_lines.append(f'   - code: "{b["code"]}" | {b["description"]}')
        manufacturer_text = '\n'.join(manufacturer_lines)

        # 모델 예시 포맷팅 (code 포함)
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
차량의 생산지를 고려하여 올바른 코드를 선택하세요.

2. model_code: 구체적인 모델의 **code 값(소문자 영문)**을 사용하세요.
   - 예시: {model_examples}
   - 목록에 없는 모델인 경우: 영문 모델명을 소문자로 변환하여 사용 (공백 제거)
     예) "Model 3" → "model3", "Palisade" → "palisade"

3. confidence: 제조사와 모델 식별의 확실성 정도 (0.0~1.0)

**신뢰도(confidence) 기준**:
- 0.95~1.0: 로고/엠블럼이 선명하고 차량 디자인이 매우 명확함
- 0.85~0.94: 차량의 주요 특징(그릴, 헤드라이트, 전체 디자인)으로 확실하게 식별 가능
- 0.70~0.84: 차량 디자인 특징으로 식별 가능하나 약간의 불확실성 있음
- 0.50~0.69: 일부 특징으로 추정 가능하지만 확신 부족
- 0.30~0.49: 제조사는 추정 가능하나 모델은 불확실
- 0.0~0.29: 식별이 거의 불가능하거나 차량이 명확히 보이지 않음

**식별 불가능한 경우**:
{{
  "manufacturer_code": "unknown",
  "model_code": "unknown",
  "confidence": 0.1
}}

**좋은 예시**:
- 로고와 디자인이 명확한 현대 캐스퍼: {{"manufacturer_code": "hyundai", "model_code": "casper", "confidence": 0.95}}
- 한국GM 스파크(국내 생산): {{"manufacturer_code": "chevrolet_gmdaewoo", "model_code": "spark", "confidence": 0.92}}
- 쉐보레 카마로(수입): {{"manufacturer_code": "chevrolet", "model_code": "camaro", "confidence": 0.90}}
- BMW 3시리즈로 확실: {{"manufacturer_code": "bmw", "model_code": "3series", "confidence": 0.90}}
- 기아 K5로 확실: {{"manufacturer_code": "kia", "model_code": "k5", "confidence": 0.88}}
- 차량이 흐릿하거나 각도가 나쁨: {{"manufacturer_code": "unknown", "model_code": "unknown", "confidence": 0.15}}

**중요**: manufacturer_code와 model_code는 반드시 소문자 영문으로만 작성하세요. 한글이나 대문자를 사용하지 마세요.
"""

        if additional_context:
            base_prompt += f"\n\n**추가 컨텍스트**:\n{additional_context}"

        return base_prompt

    def _parse_response(self, response) -> Dict:
        """OpenAI 응답 파싱 (JSON 우선, 폴백으로 텍스트 파싱)"""
        try:
            content = response.choices[0].message.content.strip()

            # 기본 값
            result = {
                "manufacturer_code": None,
                "model_code": None,
                "confidence": 0.0,
                "raw_response": content
            }

            # 1차 시도: JSON 파싱
            try:
                # JSON 코드 블록 제거 (```json ... ``` 형식 대응)
                json_content = content
                if "```json" in json_content:
                    json_content = json_content.split("```json")[1].split("```")[0].strip()
                elif "```" in json_content:
                    json_content = json_content.split("```")[1].split("```")[0].strip()

                # JSON 파싱
                data = json.loads(json_content)

                manufacturer_code = data.get("manufacturer_code", "").lower()
                model_code = data.get("model_code", "").lower()

                result["manufacturer_code"] = manufacturer_code if manufacturer_code not in ["", "unknown", "알 수 없음"] else None
                result["model_code"] = model_code if model_code not in ["", "unknown", "알 수 없음"] else None
                result["confidence"] = float(data.get("confidence", 0.0))

                logger.info(f"JSON 파싱 성공: {result}")
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as json_error:
                logger.warning(f"JSON 파싱 실패, 텍스트 파싱 시도: {json_error}")

                # 2차 시도: 텍스트 라인 파싱 (폴백)
                lines = content.split('\n')
                for line in lines:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip(',').lower()

                        if "manufacturer_code" in key.lower():
                            result["manufacturer_code"] = value if value not in ["unknown", "알 수 없음"] else None
                        elif "model_code" in key.lower():
                            result["model_code"] = value if value not in ["unknown", "알 수 없음"] else None
                        elif any(keyword in key.lower() for keyword in ['신뢰도', 'confidence']):
                            try:
                                result["confidence"] = float(value)
                            except ValueError:
                                result["confidence"] = 0.0

                logger.info(f"텍스트 파싱 결과: {result}")
                return result

        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return {
                "manufacturer_code": None,
                "model_code": None,
                "confidence": 0.0,
                "raw_response": str(response),
                "error": str(e)
            }

    async def batch_analyze(
        self,
        image_paths: list[str],
        progress_callback: Optional[callable] = None
    ) -> list[Dict]:
        """
        여러 이미지 일괄 분석

        Args:
            image_paths: 이미지 경로 리스트
            progress_callback: 진행상황 콜백 함수

        Returns:
            분석 결과 리스트
        """
        results = []

        for idx, image_path in enumerate(image_paths):
            try:
                result = await self.analyze_vehicle_image(image_path)
                result["image_path"] = image_path
                results.append(result)

                if progress_callback:
                    progress_callback(idx + 1, len(image_paths))

            except Exception as e:
                logger.error(f"Failed to analyze {image_path}: {e}")
                results.append({
                    "image_path": image_path,
                    "error": str(e),
                    "manufacturer": None,
                    "model": None,
                    "confidence": 0.0
                })

        return results


# 전역 인스턴스
vision_service = OpenAIVisionService()
