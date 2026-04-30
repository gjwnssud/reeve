"""
차량 매칭 서비스
AI 분석 결과를 기준 DB와 매칭
"""
from typing import Optional, Tuple, Dict, List
import logging
import re
from sqlalchemy.orm import Session
from rapidfuzz import fuzz, process

from studio.models.manufacturer import Manufacturer
from studio.models.vehicle_model import VehicleModel
from studio.config import settings

logger = logging.getLogger(__name__)


class VehicleMatcher:
    """차량 제조사/모델 매칭 엔진"""

    def __init__(self, db: Session, auto_insert: bool = True):
        """
        Args:
            db: 데이터베이스 세션
            auto_insert: 매칭 실패 시 자동으로 DB에 추가할지 여부
        """
        self.db = db
        self.threshold = settings.fuzzy_match_threshold
        self.auto_insert = auto_insert

    @staticmethod
    def _sanitize_code(code: str) -> str:
        """앞뒤 공백·특수문자만 제거 (대소문자·한글 원본 보존)

        매칭은 호출 측에서 ``.lower()`` 적용으로 대소문자 무시 비교한다.
        저장 시에는 이 결과를 그대로 사용해 입력 원본을 보존한다.
        """
        return re.sub(r'[^A-Za-z0-9_가-힣]', '', code.strip())

    @staticmethod
    def _normalize_code(code: str) -> str:
        """비교용 정규화: 영문자·숫자·한글만 남기고 소문자화 (구분자·대소문자 무시)"""
        return re.sub(r'[^a-z0-9가-힣]', '', code.lower())

    def match_manufacturer_by_code(
        self,
        manufacturer_code: str
    ) -> Optional[Tuple[Manufacturer, float]]:
        """
        제조사 코드로 정확 매칭

        Args:
            manufacturer_code: 제조사 코드 (소문자 영문)

        Returns:
            (매칭된 제조사 객체, 100.0) 또는 None
        """
        if not manufacturer_code:
            return None

        # 입력 정제 (공백·특수문자 제거, 대소문자·한글 원본 보존)
        clean_code = self._sanitize_code(manufacturer_code)
        if not clean_code:
            return None

        # 코드로 정확 매칭 (대소문자 무시)
        from sqlalchemy import func
        manufacturer = self.db.query(Manufacturer).filter(
            func.lower(Manufacturer.code) == clean_code.lower()
        ).first()

        if manufacturer:
            logger.info(f"Manufacturer matched by code: '{manufacturer_code}' -> '{manufacturer.korean_name}'")
            return (manufacturer, 100.0)

        logger.warning(f"No manufacturer match found for code: '{manufacturer_code}'")
        return None

    def match_manufacturer(
        self,
        manufacturer_name: str,
        is_domestic: Optional[bool] = None
    ) -> Optional[Tuple[Manufacturer, float]]:
        """
        제조사 매칭 (Fuzzy matching - 하위 호환성 유지)

        Args:
            manufacturer_name: 분석된 제조사명
            is_domestic: 국내/해외 구분 (선택사항)

        Returns:
            (매칭된 제조사 객체, 유사도 점수) 또는 None
        """
        if not manufacturer_name:
            return None

        # 모든 제조사 조회
        query = self.db.query(Manufacturer)
        if is_domestic is not None:
            query = query.filter(Manufacturer.is_domestic == is_domestic)

        manufacturers = query.all()

        if not manufacturers:
            return None

        # 제조사명 목록 준비 (한글명 + 영문명 + 코드)
        choices = []
        for mf in manufacturers:
            choices.append((mf.korean_name, mf))
            choices.append((mf.english_name, mf))
            choices.append((mf.code, mf))

        # Fuzzy matching
        best_match = None
        best_score = 0.0

        for name, mf in choices:
            # 여러 유사도 알고리즘 사용
            ratio = fuzz.ratio(manufacturer_name.lower(), name.lower())
            partial_ratio = fuzz.partial_ratio(manufacturer_name.lower(), name.lower())
            token_sort_ratio = fuzz.token_sort_ratio(manufacturer_name.lower(), name.lower())

            # 가중 평균 (partial_ratio 가중치 증가 - 부분 매칭 중시)
            score = (ratio * 0.3 + partial_ratio * 0.5 + token_sort_ratio * 0.2)

            if score > best_score:
                best_score = score
                best_match = mf

        # 임계값 확인
        if best_score >= self.threshold:
            logger.info(f"Manufacturer matched: '{manufacturer_name}' -> '{best_match.korean_name}' (score: {best_score:.2f})")
            return (best_match, best_score)

        logger.warning(f"No manufacturer match found for '{manufacturer_name}' (best score: {best_score:.2f})")
        return None

    def match_model_by_code(
        self,
        model_code: str,
        manufacturer_id: Optional[int] = None
    ) -> Optional[Tuple[VehicleModel, float]]:
        """
        모델 코드로 정확 매칭

        Args:
            model_code: 모델 코드 (소문자 영문)
            manufacturer_id: 제조사 ID (있으면 해당 제조사 모델만 검색)

        Returns:
            (매칭된 모델 객체, 100.0) 또는 None
        """
        if not model_code:
            return None

        # 코드로 정확 매칭 (대소문자 무시)
        clean_code = self._sanitize_code(model_code)
        if not clean_code:
            return None
        from sqlalchemy import func
        query = self.db.query(VehicleModel).filter(
            func.lower(VehicleModel.code) == clean_code.lower()
        )

        if manufacturer_id:
            query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)

        model = query.first()

        if model:
            logger.info(f"Model matched by code: '{model_code}' -> '{model.korean_name}'")
            return (model, 100.0)

        logger.warning(f"No model match found for code: '{model_code}'")
        return None

    def match_model(
        self,
        model_name: str,
        manufacturer_id: Optional[int] = None
    ) -> Optional[Tuple[VehicleModel, float]]:
        """
        차량 모델 매칭 (Fuzzy matching - 하위 호환성 유지)

        Args:
            model_name: 분석된 모델명
            manufacturer_id: 제조사 ID (있으면 해당 제조사 모델만 검색)

        Returns:
            (매칭된 모델 객체, 유사도 점수) 또는 None
        """
        if not model_name:
            return None

        # 모델 조회
        query = self.db.query(VehicleModel)
        if manufacturer_id:
            query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)

        models = query.all()

        if not models:
            return None

        # 모델명 목록 준비 (한글명 + 영문명 + 코드)
        choices = []
        for model in models:
            choices.append((model.korean_name, model))
            choices.append((model.english_name, model))
            choices.append((model.code, model))

        # Fuzzy matching
        best_match = None
        best_score = 0.0

        for name, model in choices:
            # 여러 유사도 알고리즘 사용
            ratio = fuzz.ratio(model_name.lower(), name.lower())
            partial_ratio = fuzz.partial_ratio(model_name.lower(), name.lower())
            token_sort_ratio = fuzz.token_sort_ratio(model_name.lower(), name.lower())

            # 가중 평균 (partial_ratio 가중치 증가 - 부분 매칭 중시)
            score = (ratio * 0.3 + partial_ratio * 0.5 + token_sort_ratio * 0.2)

            if score > best_score:
                best_score = score
                best_match = model

        # 임계값 확인
        if best_score >= self.threshold:
            logger.info(f"Model matched: '{model_name}' -> '{best_match.korean_name}' (score: {best_score:.2f})")
            return (best_match, best_score)

        logger.warning(f"No model match found for '{model_name}' (best score: {best_score:.2f})")
        return None

    def match_vehicle(
        self,
        manufacturer_code: str,
        model_code: str,
        vision_confidence: Optional[float] = None
    ) -> Dict:
        """
        제조사 + 모델 통합 매칭 (code 기반)

        Args:
            manufacturer_code: 제조사 코드 (소문자 영문)
            model_code: 모델 코드 (소문자 영문)
            vision_confidence: Vision API의 신뢰도 (0.0 ~ 1.0)

        Returns:
            매칭 결과 딕셔너리
            {
                "manufacturer": Manufacturer 객체 또는 None,
                "manufacturer_score": float,
                "model": VehicleModel 객체 또는 None,
                "model_score": float,
                "overall_confidence": float,
                "auto_inserted_manufacturer": bool,
                "auto_inserted_model": bool
            }
        """
        result = {
            "manufacturer": None,
            "manufacturer_score": 0.0,
            "model": None,
            "model_score": 0.0,
            "overall_confidence": 0.0,
            "auto_inserted_manufacturer": False,
            "auto_inserted_model": False
        }

        # 1단계: 제조사 코드로 정확 매칭
        manufacturer_match = self.match_manufacturer_by_code(manufacturer_code)
        if manufacturer_match:
            result["manufacturer"] = manufacturer_match[0]
            result["manufacturer_score"] = 100.0  # 코드 정확 매칭은 100점
        else:
            # 매칭 실패 시 자동 삽입 시도
            new_manufacturer = self._auto_insert_manufacturer_by_code(manufacturer_code)
            if new_manufacturer:
                result["manufacturer"] = new_manufacturer
                # 자동 삽입 시에도 Vision API의 신뢰도 사용
                result["manufacturer_score"] = (vision_confidence * 100) if vision_confidence else 80.0
                result["auto_inserted_manufacturer"] = True

        # 2단계: 모델 코드로 정확 매칭 (제조사가 매칭된 경우 해당 제조사 모델만 검색)
        manufacturer_id = result["manufacturer"].id if result["manufacturer"] else None
        model_match = self.match_model_by_code(model_code, manufacturer_id)

        if model_match:
            result["model"] = model_match[0]
            result["model_score"] = 100.0  # 코드 정확 매칭은 100점

            # 모델의 제조사와 매칭된 제조사가 다른 경우 검증
            if result["manufacturer"] and model_match[0].manufacturer_id != result["manufacturer"].id:
                logger.warning(
                    f"Manufacturer-Model mismatch: {result['manufacturer'].korean_name} vs "
                    f"{model_match[0].manufacturer.korean_name}"
                )
        else:
            # 매칭 실패 시 자동 삽입 시도 (제조사가 있는 경우에만)
            if result["manufacturer"]:
                new_model = self._auto_insert_model_by_code(model_code, result["manufacturer"])
                if new_model:
                    result["model"] = new_model
                    # 자동 삽입 시에도 Vision API의 신뢰도 사용
                    result["model_score"] = (vision_confidence * 100) if vision_confidence else 80.0
                    result["auto_inserted_model"] = True

        # 전체 신뢰도 계산
        # 코드 매칭이므로 매칭 자체는 100% 정확, 신뢰도는 Vision API confidence에 의존
        if result["manufacturer"] and result["model"]:
            # Vision confidence 사용 (있으면)
            if vision_confidence:
                result["overall_confidence"] = vision_confidence * 100
            else:
                # Vision confidence 없으면 매칭 점수 기반
                result["overall_confidence"] = (
                    result["manufacturer_score"] * 0.6 +
                    result["model_score"] * 0.4
                )
        elif result["manufacturer"]:
            # 제조사만 매칭된 경우 (모델 불확실) - 신뢰도를 낮춤
            base_confidence = (vision_confidence * 100) if vision_confidence else result["manufacturer_score"] * 0.6
            # 최대 50%로 제한 (부분적 식별만 가능)
            result["overall_confidence"] = min(base_confidence * 0.6, 50.0)
        elif result["model"]:
            result["overall_confidence"] = (vision_confidence * 100) if vision_confidence else result["model_score"] * 0.4

        return result

    def get_similar_manufacturers(
        self,
        manufacturer_name: str,
        limit: int = 5
    ) -> List[Tuple[Manufacturer, float]]:
        """
        유사한 제조사 목록 (상위 N개)

        Args:
            manufacturer_name: 검색할 제조사명
            limit: 반환할 최대 개수

        Returns:
            (제조사 객체, 유사도 점수) 리스트
        """
        manufacturers = self.db.query(Manufacturer).all()

        if not manufacturers:
            return []

        # 모든 제조사와 유사도 계산
        scores = []
        for mf in manufacturers:
            # 한글명, 영문명, 코드 중 최대 유사도 사용
            names = [mf.korean_name, mf.english_name, mf.code]
            max_score = 0.0

            for name in names:
                score = fuzz.ratio(manufacturer_name.lower(), name.lower())
                max_score = max(max_score, score)

            scores.append((mf, max_score))

        # 유사도 순으로 정렬
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:limit]

    def get_similar_models(
        self,
        model_name: str,
        manufacturer_id: Optional[int] = None,
        limit: int = 5
    ) -> List[Tuple[VehicleModel, float]]:
        """
        유사한 모델 목록 (상위 N개)

        Args:
            model_name: 검색할 모델명
            manufacturer_id: 제조사 ID (선택사항)
            limit: 반환할 최대 개수

        Returns:
            (모델 객체, 유사도 점수) 리스트
        """
        query = self.db.query(VehicleModel)
        if manufacturer_id:
            query = query.filter(VehicleModel.manufacturer_id == manufacturer_id)

        models = query.all()

        if not models:
            return []

        # 모든 모델과 유사도 계산
        scores = []
        for model in models:
            # 한글명, 영문명, 코드 중 최대 유사도 사용
            names = [model.korean_name, model.english_name, model.code]
            max_score = 0.0

            for name in names:
                score = fuzz.ratio(model_name.lower(), name.lower())
                max_score = max(max_score, score)

            scores.append((model, max_score))

        # 유사도 순으로 정렬
        scores.sort(key=lambda x: x[1], reverse=True)

        return scores[:limit]

    def _generate_code(self, name: str, existing_codes: List[str]) -> str:
        """
        이름에서 코드 생성

        Args:
            name: 제조사명 또는 모델명
            existing_codes: 기존 코드 목록 (중복 방지)

        Returns:
            생성된 고유 코드
        """
        # 영문자만 추출하여 대문자로 변환
        code_base = re.sub(r'[^a-zA-Z]', '', name).upper()

        # 코드가 너무 짧으면 최소 3자 보장
        if len(code_base) < 3:
            code_base = name[:3].upper()

        # 최대 10자로 제한
        code_base = code_base[:10]

        # 중복 체크 및 번호 추가
        code = code_base
        counter = 1
        while code in existing_codes:
            code = f"{code_base}{counter}"
            counter += 1

        return code

    def _auto_insert_manufacturer_by_code(self, manufacturer_code: str) -> Optional[Manufacturer]:
        """
        매칭되지 않은 제조사를 code 기반으로 자동 추가

        Args:
            manufacturer_code: ChatGPT가 반환한 제조사 코드 (소문자 영문)

        Returns:
            생성된 Manufacturer 객체 또는 None
        """
        if not self.auto_insert or not manufacturer_code:
            return None

        # 입력 정제
        clean_code = self._sanitize_code(manufacturer_code)
        if not clean_code:
            return None

        try:
            # 정규화 기반 중복 체크 (구분자 차이 무시: hyundai == hyundai_, HYUNDAI 등)
            existing_normalized = [self._normalize_code(mf.code) for mf in self.db.query(Manufacturer).all()]
            if self._normalize_code(clean_code) in existing_normalized:
                logger.warning(f"Manufacturer code already exists (normalized): {manufacturer_code}")
                return None

            # 응답 원본을 그대로 저장 (대소문자·한글 보존)
            # 한글 포함 시 국산으로 가정. 검수에서 수정 가능.
            korean_name = clean_code
            english_name = clean_code
            is_domestic = bool(re.search(r'[가-힣]', clean_code))

            # DB에 삽입
            new_manufacturer = Manufacturer(
                code=clean_code,
                korean_name=korean_name,
                english_name=english_name,
                is_domestic=is_domestic
            )

            self.db.add(new_manufacturer)
            self.db.commit()
            self.db.refresh(new_manufacturer)

            logger.info(
                f"Auto-inserted manufacturer by code: {manufacturer_code} -> "
                f"code={clean_code}, korean={korean_name}, english={english_name}, domestic={is_domestic}"
            )

            return new_manufacturer

        except Exception as e:
            logger.error(f"Failed to auto-insert manufacturer by code '{manufacturer_code}': {e}")
            self.db.rollback()
            return None

    def _auto_insert_manufacturer(self, manufacturer_name: str) -> Optional[Manufacturer]:
        """
        매칭되지 않은 제조사를 자동으로 DB에 추가

        Args:
            manufacturer_name: ChatGPT가 인식한 제조사명

        Returns:
            생성된 Manufacturer 객체 또는 None
        """
        if not self.auto_insert or not manufacturer_name:
            return None

        try:
            # 기존 코드 목록 가져오기
            existing_codes = [mf.code for mf in self.db.query(Manufacturer).all()]

            # 코드 생성
            code = self._generate_code(manufacturer_name, existing_codes)

            # 한글/영문 구분 (간단한 휴리스틱)
            has_korean = bool(re.search(r'[가-힣]', manufacturer_name))
            has_english = bool(re.search(r'[a-zA-Z]', manufacturer_name))

            if has_korean and has_english:
                # 한글과 영문이 섞여있는 경우 (예: "현대 Hyundai")
                korean_part = re.sub(r'[^가-힣\s]', '', manufacturer_name).strip()
                english_part = re.sub(r'[^a-zA-Z\s]', '', manufacturer_name).strip()
                korean_name = korean_part if korean_part else manufacturer_name
                english_name = english_part if english_part else manufacturer_name
            elif has_korean:
                # 한글만 있는 경우 (예: "현대")
                korean_name = manufacturer_name
                english_name = code  # 영문명은 코드로 설정
            else:
                # 영문만 있는 경우 (예: "Hyundai")
                korean_name = code  # 한글명은 코드로 설정
                english_name = manufacturer_name

            # 국내/해외 판단 (한글이 있으면 국내로 추정)
            is_domestic = has_korean

            # DB에 삽입
            new_manufacturer = Manufacturer(
                code=code,
                korean_name=korean_name,
                english_name=english_name,
                is_domestic=is_domestic
            )

            self.db.add(new_manufacturer)
            self.db.commit()
            self.db.refresh(new_manufacturer)

            logger.info(
                f"Auto-inserted manufacturer: {manufacturer_name} -> "
                f"code={code}, korean={korean_name}, english={english_name}, domestic={is_domestic}"
            )

            return new_manufacturer

        except Exception as e:
            logger.error(f"Failed to auto-insert manufacturer '{manufacturer_name}': {e}")
            self.db.rollback()
            return None

    def _auto_insert_model_by_code(
        self,
        model_code: str,
        manufacturer: Manufacturer
    ) -> Optional[VehicleModel]:
        """
        매칭되지 않은 모델을 code 기반으로 자동 추가

        Args:
            model_code: ChatGPT가 반환한 모델 코드 (소문자 영문)
            manufacturer: 연결할 제조사 객체

        Returns:
            생성된 VehicleModel 객체 또는 None
        """
        if not self.auto_insert or not model_code or not manufacturer:
            return None

        # 입력 정제
        clean_code = self._sanitize_code(model_code)
        if not clean_code:
            return None

        try:
            # 정규화 기반 중복 체크 (구분자 차이 무시: model3 == model_3, MODEL3 등)
            existing_normalized = [self._normalize_code(m.code) for m in self.db.query(VehicleModel).all()]
            if self._normalize_code(clean_code) in existing_normalized:
                logger.warning(f"Model code already exists (normalized): {model_code}")
                return None

            # 응답 원본을 그대로 저장 (대소문자·한글 보존)
            korean_name = clean_code
            english_name = clean_code

            # DB에 삽입
            new_model = VehicleModel(
                code=clean_code,
                manufacturer_id=manufacturer.id,
                manufacturer_code=manufacturer.code,
                korean_name=korean_name,
                english_name=english_name
            )

            self.db.add(new_model)
            self.db.commit()
            self.db.refresh(new_model)

            logger.info(
                f"Auto-inserted model by code: {model_code} -> "
                f"code={clean_code}, korean={korean_name}, english={english_name}, "
                f"manufacturer={manufacturer.korean_name}"
            )

            return new_model

        except Exception as e:
            logger.error(f"Failed to auto-insert model by code '{model_code}': {e}")
            self.db.rollback()
            return None

    def _auto_insert_model(
        self,
        model_name: str,
        manufacturer: Manufacturer
    ) -> Optional[VehicleModel]:
        """
        매칭되지 않은 모델을 자동으로 DB에 추가

        Args:
            model_name: ChatGPT가 인식한 모델명
            manufacturer: 연결할 제조사 객체

        Returns:
            생성된 VehicleModel 객체 또는 None
        """
        if not self.auto_insert or not model_name or not manufacturer:
            return None

        try:
            # 기존 코드 목록 가져오기
            existing_codes = [m.code for m in self.db.query(VehicleModel).all()]

            # 코드 생성
            code = self._generate_code(model_name, existing_codes)

            # 한글/영문 구분
            has_korean = bool(re.search(r'[가-힣]', model_name))
            has_english = bool(re.search(r'[a-zA-Z]', model_name))

            if has_korean and has_english:
                # 한글과 영문이 섞여있는 경우 (예: "캐스퍼 Casper")
                korean_part = re.sub(r'[^가-힣\s\d]', '', model_name).strip()
                english_part = re.sub(r'[^a-zA-Z\s\d]', '', model_name).strip()
                korean_name = korean_part if korean_part else model_name
                english_name = english_part if english_part else model_name
            elif has_korean:
                # 한글만 있는 경우 (예: "캐스퍼")
                korean_name = model_name
                english_name = code  # 영문명은 코드로 설정
            else:
                # 영문만 있는 경우 (예: "Casper")
                korean_name = code  # 한글명은 코드로 설정
                english_name = model_name

            # DB에 삽입
            new_model = VehicleModel(
                code=code,
                manufacturer_id=manufacturer.id,
                manufacturer_code=manufacturer.code,
                korean_name=korean_name,
                english_name=english_name
            )

            self.db.add(new_model)
            self.db.commit()
            self.db.refresh(new_model)

            logger.info(
                f"Auto-inserted model: {model_name} -> "
                f"code={code}, korean={korean_name}, english={english_name}, "
                f"manufacturer={manufacturer.korean_name}"
            )

            return new_model

        except Exception as e:
            logger.error(f"Failed to auto-insert model '{model_name}': {e}")
            self.db.rollback()
            return None
