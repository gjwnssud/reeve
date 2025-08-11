"""
강화된 차량 데이터 추출기
DB 기반 2단계 프롬프트 시스템 적용
"""

import base64
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Any

from PIL import Image
from openai import OpenAI

from src.core.vehicle_detector import VehicleDetector
from app.services.vehicle_db_service import vehicle_db_service

logger = logging.getLogger(__name__)


class VehicleDataExtractor:
    """향상된 차량 데이터 추출기 (DB 연동)"""

    def __init__(self):
        # OpenAI 클라이언트 초기화
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ValueError("OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")

        self.client = OpenAI(api_key=api_key)
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')

        # 차량 감지기
        try:
            self.vehicle_detector = VehicleDetector()
        except:
            self.vehicle_detector = None
            logger.warning("차량 감지기 초기화 실패 - 차량 감지 기능 비활성화")

        # DB 서비스
        self.db_service = vehicle_db_service

        print(f"✅ Enhanced Vehicle Data Extractor 초기화 완료")
        print(f"   - OpenAI 모델: {self.model}")
        print(
            f"   - 차량 감지: {'활성화' if self.vehicle_detector and hasattr(self.vehicle_detector, 'model') and self.vehicle_detector.model else '비활성화'}")

    def analyze_vehicle_from_text_v2(self, text: str) -> Dict[str, Any]:
        """텍스트에서 차량 정보 추출 (2단계 프롬프트)"""
        try:
            start_time = time.time()

            # 1단계: 제조사 식별
            manufacturer_info = self._identify_manufacturer(text)
            if not manufacturer_info:
                return self._create_error_result(text, "제조사를 식별할 수 없습니다.")

            # 2단계: 모델 식별
            model_info = self._identify_model(manufacturer_info['code'], text)
            if not model_info:
                return self._create_error_result(text,
                                                 f"제조사 '{manufacturer_info['korean_name']}'의 모델을 식별할 수 없습니다.")

            # 3단계: 연식 추정
            year_info = self._estimate_year(text, manufacturer_info, model_info)

            # 결과 구성
            result = self._create_success_result(
                input_data=text,
                source_type="text",
                manufacturer=manufacturer_info,
                model=model_info,
                year_info=year_info,
                processing_time=time.time() - start_time
            )

            return result

        except Exception as e:
            logger.error(f"텍스트 분석 오류: {e}")
            return self._create_error_result(text, str(e))

    def analyze_vehicle_from_image_v2(self, image_path: str) -> Dict[str, Any]:
        """이미지에서 차량 정보 추출 (2단계 프롬프트)"""
        try:
            start_time = time.time()

            # 이미지 전처리 및 인코딩
            base64_image = self._encode_image(image_path)
            if not base64_image:
                return self._create_error_result(image_path, "이미지 처리 실패")

            # 1단계: 제조사 식별
            manufacturer_info = self._identify_manufacturer_from_image(base64_image)
            if not manufacturer_info:
                return self._create_error_result(image_path, "이미지에서 제조사를 식별할 수 없습니다.")

            # 2단계: 모델 식별
            model_info = self._identify_model_from_image(manufacturer_info['code'], base64_image)
            if not model_info:
                return self._create_error_result(image_path,
                                                 f"제조사 '{manufacturer_info['korean_name']}'의 모델을 식별할 수 없습니다.")

            # 3단계: 연식 추정
            year_info = self._estimate_year_from_image(base64_image, manufacturer_info, model_info)

            # 결과 구성
            result = self._create_success_result(
                input_data=os.path.basename(image_path),
                source_type="image",
                manufacturer=manufacturer_info,
                model=model_info,
                year_info=year_info,
                processing_time=time.time() - start_time
            )

            return result

        except Exception as e:
            logger.error(f"이미지 분석 오류: {e}")
            return self._create_error_result(image_path, str(e))

    def _identify_manufacturer(self, text: str) -> Optional[Dict]:
        """1단계: 텍스트에서 제조사 식별"""
        try:
            # 제조사 예시 가져오기
            manufacturer_examples = self.db_service.get_manufacturer_prompt_examples(15)

            prompt = f"""다음 텍스트에서 자동차 제조사를 식별해주세요.

텍스트: "{text}"

사용 가능한 제조사 목록 (예시):
{manufacturer_examples}

응답 형식 (정확히 이 형식으로만 답변):
code: [제조사_코드]
korean_name: [한글명]
english_name: [영문명]
confidence: [1-100 신뢰도]

주의사항:
- 제조사 코드는 위 목록에서 정확히 일치하는 것만 사용
- 확실하지 않으면 confidence를 낮게 설정
- 제조사가 명확하지 않으면 confidence 50 이하로 설정"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "당신은 자동차 제조사 식별 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            # DB에서 매칭 시도
            manufacturer = self.db_service.match_manufacturer_response(response_text)
            if manufacturer:
                # confidence 추출
                confidence = self._extract_confidence(response_text)
                manufacturer['confidence'] = confidence
                return manufacturer

            return None

        except Exception as e:
            logger.error(f"제조사 식별 오류: {e}")
            return None

    def _identify_model(self, manufacturer_code: str, text: str) -> Optional[Dict]:
        """2단계: 텍스트에서 모델 식별"""
        try:
            # 해당 제조사의 모델 예시 가져오기
            model_examples = self.db_service.get_model_prompt_examples(manufacturer_code, 20)

            if not model_examples:
                return None

            manufacturer_info = self.db_service.get_all_manufacturers()
            manufacturer_name = next(
                (m['korean_name'] for m in manufacturer_info if m['code'] == manufacturer_code),
                manufacturer_code)

            prompt = f"""다음 텍스트에서 {manufacturer_name} 제조사의 차량 모델을 식별해주세요.

텍스트: "{text}"

{manufacturer_name} 사용 가능한 모델 목록:
{model_examples}

응답 형식 (정확히 이 형식으로만 답변):
code: [모델_코드]
korean_name: [한글명]
english_name: [영문명]
confidence: [1-100 신뢰도]

주의사항:
- 모델 코드는 위 목록에서 정확히 일치하는 것만 사용
- {manufacturer_name} 브랜드의 모델만 식별
- 확실하지 않으면 confidence를 낮게 설정"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"당신은 {manufacturer_name} 차량 모델 식별 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            # DB에서 매칭 시도
            model = self.db_service.match_model_response(manufacturer_code, response_text)
            if model:
                # confidence 추출
                confidence = self._extract_confidence(response_text)
                model['confidence'] = confidence
                return model

            return None

        except Exception as e:
            logger.error(f"모델 식별 오류: {e}")
            return None

    def _identify_manufacturer_from_image(self, base64_image: str) -> Optional[Dict]:
        """1단계: 이미지에서 제조사 식별"""
        try:
            manufacturer_examples = self.db_service.get_manufacturer_prompt_examples(15)

            prompt = f"""이 자동차 이미지에서 제조사를 식별해주세요.

사용 가능한 제조사 목록 (예시):
{manufacturer_examples}

응답 형식 (정확히 이 형식으로만 답변):
code: [제조사_코드]
korean_name: [한글명]
english_name: [영문명]
confidence: [1-100 신뢰도]
visual_clues: [식별 근거]

주의사항:
- 제조사 코드는 위 목록에서 정확히 일치하는 것만 사용
- 로고, 그릴, 헤드라이트 등 시각적 특징을 근거로 판단
- 확실하지 않으면 confidence를 낮게 설정"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "당신은 자동차 이미지에서 제조사를 식별하는 전문가입니다."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=400,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            # DB에서 매칭 시도
            manufacturer = self.db_service.match_manufacturer_response(response_text)
            if manufacturer:
                confidence = self._extract_confidence(response_text)
                visual_clues = self._extract_visual_clues(response_text)
                manufacturer['confidence'] = confidence
                manufacturer['visual_clues'] = visual_clues
                return manufacturer

            return None

        except Exception as e:
            logger.error(f"이미지 제조사 식별 오류: {e}")
            return None

    def _identify_model_from_image(self, manufacturer_code: str, base64_image: str) -> Optional[
        Dict]:
        """2단계: 이미지에서 모델 식별"""
        try:
            model_examples = self.db_service.get_model_prompt_examples(manufacturer_code, 20)

            if not model_examples:
                return None

            manufacturer_info = self.db_service.get_all_manufacturers()
            manufacturer_name = next(
                (m['korean_name'] for m in manufacturer_info if m['code'] == manufacturer_code),
                manufacturer_code)

            prompt = f"""이 {manufacturer_name} 차량 이미지에서 정확한 모델을 식별해주세요.

{manufacturer_name} 사용 가능한 모델 목록:
{model_examples}

응답 형식 (정확히 이 형식으로만 답변):
code: [모델_코드]
korean_name: [한글명]
english_name: [영문명]
confidence: [1-100 신뢰도]
visual_clues: [식별 근거]

주의사항:
- 모델 코드는 위 목록에서 정확히 일치하는 것만 사용
- {manufacturer_name} 브랜드의 모델만 식별
- 차체 형태, 디자인, 크기 등을 종합적으로 고려
- 확실하지 않으면 confidence를 낮게 설정"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": f"당신은 {manufacturer_name} 차량 모델을 이미지에서 식별하는 전문가입니다."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=400,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            # DB에서 매칭 시도
            model = self.db_service.match_model_response(manufacturer_code, response_text)
            if model:
                confidence = self._extract_confidence(response_text)
                visual_clues = self._extract_visual_clues(response_text)
                model['confidence'] = confidence
                model['visual_clues'] = visual_clues
                return model

            return None

        except Exception as e:
            logger.error(f"이미지 모델 식별 오류: {e}")
            return None

    def _estimate_year(self, text: str, manufacturer: Dict, model: Dict) -> Dict:
        """연식 추정 (텍스트 기반)"""
        try:
            prompt = f"""다음 텍스트에서 {manufacturer['korean_name']} {model['korean_name']} 차량의 연식을 추정해주세요.

텍스트: "{text}"

응답 형식:
year: [연식 예: 2020]
year_range: [연식 범위 예: 2018-2020]
confidence: [1-100 신뢰도]
reasoning: [추정 근거]

주의사항:
- 명시적인 연식이 있으면 그대로 사용
- 불분명하면 연식 범위로 표현
- 추정 근거를 명확히 제시"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "당신은 자동차 연식 추정 전문가입니다."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            return self._parse_year_response(response_text)

        except Exception as e:
            logger.error(f"연식 추정 오류: {e}")
            return {"year": "unknown", "confidence": 0, "reasoning": "연식 추정 실패"}

    def _estimate_year_from_image(self, base64_image: str, manufacturer: Dict, model: Dict) -> Dict:
        """연식 추정 (이미지 기반)"""
        try:
            prompt = f"""이 {manufacturer['korean_name']} {model['korean_name']} 차량 이미지에서 연식을 추정해주세요.

응답 형식:
year: [연식 예: 2020]
year_range: [연식 범위 예: 2018-2020]
confidence: [1-100 신뢰도]
reasoning: [추정 근거 - 헤드라이트, 그릴, 범퍼 등 변경사항 기반]

주의사항:
- 페이스리프트, 풀체인지 등 외관 변경사항을 근거로 판단
- 헤드라이트, 그릴, 범퍼 디자인의 세대별 특징 분석
- 불분명하면 연식 범위로 표현"""

            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system",
                     "content": f"당신은 {manufacturer['korean_name']} {model['korean_name']} 차량의 연식을 이미지에서 추정하는 전문가입니다."},
                    {"role": "user", "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}
                ],
                max_tokens=400,
                temperature=0.1
            )

            response_text = response.choices[0].message.content.strip()

            return self._parse_year_response(response_text)

        except Exception as e:
            logger.error(f"이미지 연식 추정 오류: {e}")
            return {"year": "unknown", "confidence": 0, "reasoning": "연식 추정 실패"}

    def _parse_year_response(self, response_text: str) -> Dict:
        """연식 응답 파싱"""
        try:
            result = {
                "year": "unknown",
                "year_range": "",
                "confidence": 0,
                "reasoning": ""
            }

            lines = response_text.strip().split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('year:'):
                    result['year'] = line.split(':', 1)[1].strip()
                elif line.startswith('year_range:'):
                    result['year_range'] = line.split(':', 1)[1].strip()
                elif line.startswith('confidence:'):
                    try:
                        result['confidence'] = int(line.split(':', 1)[1].strip())
                    except:
                        result['confidence'] = 50
                elif line.startswith('reasoning:'):
                    result['reasoning'] = line.split(':', 1)[1].strip()

            return result

        except Exception as e:
            logger.error(f"연식 응답 파싱 오류: {e}")
            return {"year": "unknown", "confidence": 0, "reasoning": "파싱 실패"}

    def _extract_confidence(self, response_text: str) -> int:
        """응답에서 confidence 추출"""
        try:
            lines = response_text.strip().split('\n')
            for line in lines:
                if 'confidence:' in line.lower():
                    parts = line.split(':')
                    if len(parts) >= 2:
                        return int(parts[1].strip())
        except:
            pass
        return 70  # 기본값

    def _extract_visual_clues(self, response_text: str) -> str:
        """응답에서 visual_clues 추출"""
        try:
            lines = response_text.strip().split('\n')
            for line in lines:
                if 'visual_clues:' in line.lower():
                    parts = line.split(':', 1)
                    if len(parts) >= 2:
                        return parts[1].strip()
        except:
            pass
        return ""

    def _encode_image(self, image_path: str) -> Optional[str]:
        """이미지를 base64로 인코딩"""
        try:
            with Image.open(image_path) as img:
                # 이미지 크기 조정 (API 효율성을 위해)
                max_size = (1024, 1024)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # JPEG로 변환
                from io import BytesIO
                buffer = BytesIO()
                if img.mode == 'RGBA':
                    img = img.convert('RGB')
                img.save(buffer, format='JPEG', quality=85)

                # base64 인코딩
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error(f"이미지 인코딩 오류: {e}")
            return None

    def _create_success_result(self, input_data: str, source_type: str, manufacturer: Dict,
                               model: Dict, year_info: Dict, processing_time: float) -> Dict:
        """성공 결과 생성"""
        timestamp = datetime.now().isoformat()

        # 전체 신뢰도 계산 (제조사, 모델 신뢰도의 가중평균)
        overall_confidence = round(
            (manufacturer.get('confidence', 70) * 0.4 +
             model.get('confidence', 70) * 0.4 +
             year_info.get('confidence', 50) * 0.2)
        )

        return {
            "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(input_data) % 10000:04d}",
            "timestamp": timestamp,
            "source_type": source_type,
            "input": input_data,
            "processing_time": round(processing_time, 2),
            "output": {
                "manufacturer": {
                    "code": manufacturer['code'],
                    "korean_name": manufacturer['korean_name'],
                    "english_name": manufacturer['english_name'],
                    "confidence": manufacturer.get('confidence', 70),
                    "visual_clues": manufacturer.get('visual_clues', '')
                },
                "model": {
                    "code": model['code'],
                    "korean_name": model['korean_name'],
                    "english_name": model['english_name'],
                    "confidence": model.get('confidence', 70),
                    "visual_clues": model.get('visual_clues', '')
                },
                "year": {
                    "year": year_info.get('year', 'unknown'),
                    "year_range": year_info.get('year_range', ''),
                    "confidence": year_info.get('confidence', 50),
                    "reasoning": year_info.get('reasoning', '')
                },
                "overall_confidence": overall_confidence
            },
            "metadata": {
                "api_model": self.model,
                "db_matched": True,
                "processing_steps": ["manufacturer_identification", "model_identification",
                                     "year_estimation"]
            }
        }

    def _create_error_result(self, input_data: str, error_message: str) -> Dict:
        """오류 결과 생성"""
        timestamp = datetime.now().isoformat()

        return {
            "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(input_data) % 10000:04d}",
            "timestamp": timestamp,
            "source_type": "unknown",
            "input": input_data,
            "error": error_message,
            "output": None,
            "metadata": {
                "api_model": self.model,
                "db_matched": False
            }
        }

    # 기존 메서드들과의 호환성 유지
    def analyze_vehicle_from_text(self, text: str) -> Dict[str, Any]:
        """기존 텍스트 분석 메서드 (호환성)"""
        return self.analyze_vehicle_from_text_v2(text)

    def analyze_vehicle_from_image(self, image_path: str) -> Dict[str, Any]:
        """기존 이미지 분석 메서드 (호환성)"""
        return self.analyze_vehicle_from_image_v2(image_path)

    def detect_vehicles_in_image(self, image_path: str) -> List[Dict]:
        """차량 감지 (기존 메서드 유지)"""
        if self.vehicle_detector and hasattr(self.vehicle_detector,
                                             'model') and self.vehicle_detector.model:
            return self.vehicle_detector.detect_vehicles(image_path)
        else:
            return []

    def analyze_vehicle_with_bbox(self, image_path: str, bbox: Optional[List[float]] = None) -> \
            Dict[str, Any]:
        """바운딩 박스 영역 분석 (기존 메서드 개선)"""
        try:
            if bbox and len(bbox) == 4:
                # 바운딩 박스로 이미지 크롭
                with Image.open(image_path) as img:
                    x1, y1, x2, y2 = [int(coord) for coord in bbox]
                    cropped = img.crop((x1, y1, x2, y2))

                    # 임시 파일로 저장
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                        cropped.save(tmp_file.name, 'JPEG')
                        temp_path = tmp_file.name

                    try:
                        result = self.analyze_vehicle_from_image_v2(temp_path)
                        result['bbox'] = bbox
                        return result
                    finally:
                        os.unlink(temp_path)
            else:
                # 전체 이미지 분석
                return self.analyze_vehicle_from_image_v2(image_path)

        except Exception as e:
            logger.error(f"바운딩 박스 분석 오류: {e}")
            return self._create_error_result(image_path, str(e))


# 전역 인스턴스 (호환성을 위해)
vehicle_extractor = VehicleDataExtractor()
