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

    def _get_all_models_by_manufacturer(self) -> Dict:
        """DB에서 전체 모델 코드를 제조사별로 그룹핑하여 반환"""
        if self._model_cache:
            return self._model_cache

        # sql/user_provided_dml.sql 기반 fallback
        fallback = {
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

            result: Dict = {}
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

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """분석용 프롬프트 생성 (DB 전체 코드 주입, 시각적 근거 기반 chain-of-thought)"""
        manufacturers = self._get_manufacturers_from_db()
        models_by_mf = self._get_all_models_by_manufacturer()

        mf_lines = []
        for brands in manufacturers.values():
            for b in brands:
                mf_lines.append(f'  "{b["code"]}": {b["korean_name"]} ({b["english_name"]})')
        manufacturer_list = "\n".join(mf_lines)

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
            multiplier = 1.0
        elif any(k in ev for k in design_keywords):
            multiplier = 0.88
        else:
            multiplier = 0.75

        return round(min(confidence * multiplier, 1.0), 3)

    def _parse_response(self, content: str) -> Dict:
        """Gemini 응답 파싱 — visual_evidence 추출 및 근거 기반 confidence 보정"""
        result = {
            "manufacturer_code": None,
            "model_code": None,
            "visual_evidence": "",
            "confidence": 0.0,
            "raw_response": content,
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
            visual_evidence = data.get("visual_evidence", "")
            raw_confidence = float(data.get("confidence", 0.0))

            result["manufacturer_code"] = manufacturer_code if manufacturer_code not in ["", "unknown"] else None
            result["model_code"] = model_code if model_code not in ["", "unknown"] else None
            result["visual_evidence"] = visual_evidence
            result["confidence"] = self._calibrate_confidence(raw_confidence, visual_evidence)

            logger.info(f"Gemini JSON 파싱 성공: mf={result['manufacturer_code']} model={result['model_code']} conf={result['confidence']} (raw={raw_confidence})")
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

    def preload_db_context(self, db: Session) -> None:
        """Vision 프롬프트용 DB 데이터를 캐싱 (커넥션 반환 전 호출)"""
        self.db = db
        self._get_manufacturers_from_db()
        self._get_all_models_by_manufacturer()
        self.db = None
