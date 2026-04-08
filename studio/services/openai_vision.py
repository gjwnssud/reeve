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
from openai import AsyncOpenAI, RateLimitError
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
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)

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

    def _get_all_models_by_manufacturer(self) -> Dict[str, List[str]]:
        """DB에서 전체 모델 코드를 제조사별로 그룹핑하여 반환"""
        if self._model_cache:
            return self._model_cache

        # sql/user_provided_dml.sql 기반 fallback
        fallback: Dict[str, List[str]] = {
            "hyundai": ["avante", "sonata", "grandeur", "tucson", "santafe", "casper", "veloster", "ioniq", "nexo", "staria", "starex", "porter", "galloper", "accent", "verna", "terracan", "veracruz", "i30", "i40", "aslan", "maxcruz", "genesis", "equus", "pony", "excel", "elantra", "scoupe", "tiburon", "tuscani", "xg", "dynasty", "lavita", "matrix", "click", "getz", "ix35"],
            "kia": ["k3", "k5", "k7", "k8", "k9", "sportage", "sorento", "carnival", "stinger", "niro", "stonic", "morning", "ray", "soul", "mohave", "bongo", "opirus", "lotze", "carens", "cerato", "rio", "pride", "retona", "brisa", "pregio", "visto", "spectra", "shuma", "sephia", "optima", "ceres"],
            "chevrolet_gmdeawoo": ["spark", "trax", "malibu", "equinox", "captiva", "colorado", "damas", "labo", "lacetti", "nubira", "lanos", "nexia", "alpheon", "winstorm", "orlando", "cruze", "aveo", "tosca", "kalos", "rezzo", "matiz", "magnus"],
            "ssangyong": ["tiboli", "korando", "rexton", "musso", "chairman", "rodius", "actyon", "istana", "kyron", "new_family", "rocksta"],
            "renault_samsung": ["sm3", "sm5_", "sm6", "sm7", "qm3", "qm5_", "qm6", "twizy"],
            "genesis": ["g70", "g80", "g90", "gv70", "gv80", "gv90", "eq900"],
            "bmw": ["1_series", "2_series", "3_series", "4_series", "5_series", "6_series", "7_series", "8_series", "x1", "x2", "x3", "x4", "x5", "x6", "x7", "m2", "m3", "m4", "m5", "m6", "i3", "i8", "z3", "z4", "z8"],
            "mercedes_benz": ["a_class", "b_class", "c_class", "e_class", "s_class", "cla_class", "cls_class", "sl_class", "slk_class", "slc_class", "glc_class", "gle_class", "gls_class", "gl_class", "glk_class", "g_class", "m_class", "r_class", "v_class", "sls_amg", "amg_gt", "sel_sec"],
            "audi": ["a1", "a3", "a4", "a5", "a6", "a7", "a8", "q3", "q5", "q7", "q8", "tt", "tts", "ttrs", "r8", "s3", "s4", "s5", "s6", "s7", "s8", "sq5", "rs3", "rs4", "rs5", "rs6", "rs7"],
            "volkswagen": ["golf", "polo", "passat", "tiguan", "touareg", "phaeton", "scirocco", "eos", "bora", "sharan", "vento", "cc", "t_roc", "arteon"],
            "porsche": ["911", "boxster", "cayman", "cayenne", "macan", "panamera", "918", "taycan", "carrera_gt"],
            "toyota": ["camry", "corolla", "prius", "rav4", "land_cruiser", "highlander", "sequoia", "tundra", "tacoma", "sienna", "avalon", "venza", "4runner", "supra", "gr86", "crown", "harrier", "alphard", "vellfire", "yaris_vitz"],
            "honda": ["accord", "civic", "cr_v", "pilot", "odyssey", "hr_v", "ridgeline", "passport", "insight", "fit", "legend", "s2000", "nsx", "element", "stream", "freed"],
            "lexus": ["es", "is", "gs", "ls", "rx", "nx", "gx", "lx", "ux", "rc", "lc", "sc", "ct200h"],
            "nissan": ["altima", "maxima", "sentra", "versa", "rogue", "murano", "pathfinder", "armada", "frontier", "titan", "350z", "370z", "gt_r", "leaf", "juke", "cube", "qashqai", "skyline", "march"],
            "mazda": ["mazda_3", "mazda_5", "mazda_6", "cx_5", "cx_7", "cx_9", "rx_7", "rx_8", "mx_5_miata"],
            "ford": ["mustang", "explorer", "escape", "expedition", "f150", "f250", "f350", "ranger", "bronco", "fusion", "focus", "taurus", "edge", "flex"],
            "chevrolet": ["camaro", "corvette", "equinox", "tahoe", "suburban", "silverado", "colorado", "blazer", "tracker"],
            "jeep": ["wrangler", "cherokee", "compass", "renegade", "commander", "patriot", "cj"],
            "tesla": ["model_s", "model3", "modelx", "modely"],
            "land_rover": ["range_rover", "range_rover_sport", "range_rover_evoque", "range_rover_velar", "discovery", "discovery_sport", "defender", "freelander"],
            "jaguar": ["xj", "xf", "xe", "f_type", "f_pace", "e_pace", "i_pace"],
            "volvo": ["s40", "s60", "s80", "s90", "v40", "v50", "v60", "v70", "v90", "xc40", "xc60", "xc70", "xc90", "c30", "c70"],
            "maserati": ["ghibli", "quattroporte", "granturismo", "gran_cabrio", "levante", "mc12"],
            "ferrari": ["f40", "f50", "f355", "f430", "360", "458", "488", "550", "575m", "612", "california", "portofino", "roma", "sf90"],
            "lamborghini": ["gallardo", "murcielago", "aventador", "huracan", "urus"],
            "rolls_royce": ["phantom", "ghost", "wraith", "dawn", "cullinan"],
            "bentley": ["continental", "bentayga", "mulsanne", "flying_spur"],
            "mini": ["cooper", "clubman", "countryman", "paceman", "roadster", "coupe"],
            "mitsubishi": ["lancer", "galant", "pajero", "outlander", "eclipse", "3000gt"],
            "subaru": ["impreza", "legacy", "outback", "forester", "brz", "wrx"],
            "suzuki": ["swift", "jimny", "grand_vitara", "alto", "wagon_r"],
            "dodge": ["challenger", "charger", "viper", "durango", "avenger", "caravan"],
            "cadillac": ["escalade", "cts", "ats", "xt5", "ct6", "dts"],
        }

        if not self.db:
            return fallback

        try:
            from studio.models.vehicle_model import VehicleModel

            models = self.db.query(VehicleModel).order_by(
                VehicleModel.manufacturer_code, VehicleModel.code
            ).all()

            result: Dict[str, List[str]] = {}
            for m in models:
                if not m.code or not m.manufacturer_code:
                    continue
                mf = m.manufacturer_code.lower()
                code = m.code.lower()
                if mf not in result:
                    result[mf] = []
                if code not in result[mf]:
                    result[mf].append(code)

            self._model_cache = result
            return result

        except Exception as e:
            logger.warning(f"Failed to load models from DB: {e}")
            return fallback

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
                    response = await self.client.chat.completions.create(
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
                        reasoning_effort="low",
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

            # 빈 응답 체크 (gpt-5-mini reasoning 토큰 소진 시 content가 빈 문자열)
            content = response.choices[0].message.content
            if not content or not content.strip():
                raise ValueError(f"OpenAI 빈 응답 (finish_reason: {response.choices[0].finish_reason})")

            # 응답 파싱
            result = self._parse_response(response)

            logger.info(f"Image analysis completed: {image_path}")
            return result

        except Exception as e:
            logger.error(f"Error analyzing image {image_path}: {e}")
            raise

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """분석용 프롬프트 생성 (DB 전체 코드 주입, 시각적 근거 기반 chain-of-thought)"""
        manufacturers = self._get_manufacturers_from_db()
        models_by_mf = self._get_all_models_by_manufacturer()

        # 제조사 코드 목록 (code: 한글명 형식)
        mf_lines = []
        for brands in manufacturers.values():
            for b in brands:
                mf_lines.append(f'  "{b["code"]}": {b["korean_name"]} ({b["english_name"]})')
        manufacturer_list = "\n".join(mf_lines)

        # 모델 코드 목록 (제조사별 그룹핑)
        model_lines = []
        for mf_code, model_codes in sorted(models_by_mf.items()):
            codes_str = ", ".join(f'"{c}"' for c in model_codes)
            model_lines.append(f'  {mf_code}: [{codes_str}]')
        model_list = "\n".join(model_lines)

        prompt = f"""Identify the vehicle manufacturer and model from the image.

## Step 1 — Visual Evidence (required)
Before classifying, briefly note what you can observe:
- Any logos, emblems, or badges (exact text or shape)
- Distinctive design features (grille, headlights, body shape, DRL pattern)
- Any model name lettering on the vehicle

## Step 2 — Select from the official code list

### Manufacturer codes (use EXACTLY as listed):
{manufacturer_list}

Note: Korean-market GM vehicles (Spark, Trax, Malibu, etc.) → "chevrolet_gmdeawoo"
      Imported Chevrolet (Camaro, Corvette, etc.) → "chevrolet"

### Model codes by manufacturer (use EXACTLY as listed):
{model_list}

If the exact model is not in the list: convert English model name to lowercase without spaces
  e.g. "Palisade" → "palisade", "EV6" → "ev6"

## Output — JSON only, no other text:
{{
  "visual_evidence": "<what you observed: logos/badges/design features>",
  "manufacturer_code": "<exact code from list>",
  "model_code": "<exact code from list>",
  "confidence": <0.0–1.0>
}}

## Confidence guide:
- 0.90–1.0:  Logo/badge clearly visible and model confirmed
- 0.75–0.89: Distinctive design features allow confident identification
- 0.55–0.74: Partial view or minor uncertainty
- 0.30–0.54: Manufacturer identifiable but model uncertain
- 0.0–0.29:  Cannot reliably identify

## Few-shot examples:
Image: clear front view, "H" emblem on grille, round DRL pattern, small crossover
→ {{"visual_evidence": "H emblem visible on grille, circular DRL pattern distinctive of Casper", "manufacturer_code": "hyundai", "model_code": "casper", "confidence": 0.93}}

Image: rear view, blue/white roundel badge on trunk, sedan body
→ {{"visual_evidence": "BMW roundel emblem on trunk lid, four-door sedan silhouette", "manufacturer_code": "bmw", "model_code": "3_series", "confidence": 0.82}}

Image: side view only, no visible badges, boxy SUV shape
→ {{"visual_evidence": "No badges visible, boxy SUV profile, rear styling resembles SsangYong Rexton", "manufacturer_code": "ssangyong", "model_code": "rexton", "confidence": 0.55}}

Image: blurry or vehicle not clearly visible
→ {{"visual_evidence": "Image too blurry to identify any logos or distinctive features", "manufacturer_code": "unknown", "model_code": "unknown", "confidence": 0.10}}"""

        if additional_context:
            prompt += f"\n\n## Additional context:\n{additional_context}"

        return prompt

    def _calibrate_confidence(self, confidence: float, visual_evidence: str) -> float:
        """시각적 근거의 강도에 따라 self-reported confidence 보정"""
        ev = visual_evidence.lower()
        badge_keywords = ["emblem", "logo", "badge", "lettering", "nameplate", "roundel"]
        design_keywords = ["grille", "headlight", "drl", "taillight", "bumper", "silhouette", "shape", "body"]
        weak_keywords = ["blurry", "unclear", "partial", "cannot", "no badge", "no logo", "not visible"]

        if any(k in ev for k in weak_keywords):
            multiplier = 0.60
        elif any(k in ev for k in badge_keywords):
            multiplier = 1.0   # 로고/배지 확인 → 그대로
        elif any(k in ev for k in design_keywords):
            multiplier = 0.88  # 디자인 특징만 → 소폭 하향
        else:
            multiplier = 0.75  # 근거 불명확 → 하향

        return round(min(confidence * multiplier, 1.0), 3)

    def _parse_response(self, response) -> Dict:
        """OpenAI 응답 파싱 — visual_evidence 추출 및 근거 기반 confidence 보정"""
        try:
            content = response.choices[0].message.content.strip()

            result = {
                "manufacturer_code": None,
                "model_code": None,
                "visual_evidence": "",
                "confidence": 0.0,
                "raw_response": content,
            }

            # 1차 시도: JSON 파싱
            try:
                json_content = content
                if "```json" in json_content:
                    json_content = json_content.split("```json")[1].split("```")[0].strip()
                elif "```" in json_content:
                    json_content = json_content.split("```")[1].split("```")[0].strip()

                data = json.loads(json_content)

                manufacturer_code = data.get("manufacturer_code", "").lower()
                model_code = data.get("model_code", "").lower()
                visual_evidence = data.get("visual_evidence", "")
                raw_confidence = float(data.get("confidence", 0.0))

                result["manufacturer_code"] = manufacturer_code if manufacturer_code not in ["", "unknown"] else None
                result["model_code"] = model_code if model_code not in ["", "unknown"] else None
                result["visual_evidence"] = visual_evidence
                result["confidence"] = self._calibrate_confidence(raw_confidence, visual_evidence)

                logger.info(f"JSON 파싱 성공: mf={result['manufacturer_code']} model={result['model_code']} conf={result['confidence']} (raw={raw_confidence})")
                return result

            except (json.JSONDecodeError, KeyError, ValueError) as json_error:
                logger.warning(f"JSON 파싱 실패, 텍스트 파싱 시도: {json_error}")

                # 2차 시도: 텍스트 라인 파싱 (폴백)
                raw_confidence = 0.0
                for line in content.split('\n'):
                    if ':' not in line:
                        continue
                    key, value = line.split(':', 1)
                    key = key.strip().lower()
                    value = value.strip().strip('"').strip(',')

                    if "manufacturer_code" in key:
                        result["manufacturer_code"] = value.lower() if value.lower() not in ["unknown"] else None
                    elif "model_code" in key:
                        result["model_code"] = value.lower() if value.lower() not in ["unknown"] else None
                    elif "visual_evidence" in key:
                        result["visual_evidence"] = value
                    elif "confidence" in key:
                        try:
                            raw_confidence = float(value)
                        except ValueError:
                            pass

                result["confidence"] = self._calibrate_confidence(raw_confidence, result["visual_evidence"])
                logger.info(f"텍스트 파싱 결과: {result}")
                return result

        except Exception as e:
            logger.error(f"Error parsing OpenAI response: {e}")
            return {
                "manufacturer_code": None,
                "model_code": None,
                "visual_evidence": "",
                "confidence": 0.0,
                "raw_response": str(response),
                "error": str(e),
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

    def preload_db_context(self, db: Session) -> None:
        """Vision 프롬프트용 DB 데이터를 캐싱 (커넥션 반환 전 호출)"""
        self.db = db
        self._get_manufacturers_from_db()
        self._get_all_models_by_manufacturer()
        self.db = None


# 전역 인스턴스
vision_service = OpenAIVisionService()
