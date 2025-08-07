import os
import json
import base64
import time
from typing import Dict, Optional, Union, List
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import requests
from io import BytesIO
from .vehicle_detector import VehicleDetector

load_dotenv()

class VehicleDataExtractor:
    """ChatGPT API를 사용하여 LLM 파인튜닝용 차량 데이터를 추출하는 클래스"""
    
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.model = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
        self.detector = VehicleDetector()  # 차량 감지기 추가
        
    def detect_vehicles_in_image(self, image_path: str) -> List[Dict]:
        """이미지에서 차량을 감지하고 바운딩 박스 반환"""
        return self.detector.detect_vehicles(image_path)
    
    def analyze_vehicle_with_bbox(self, image_path: str, bbox: List[int] = None) -> Dict:
        """
        바운딩 박스 영역을 크롭하여 차량 분석
        
        Args:
            image_path: 원본 이미지 경로
            bbox: 바운딩 박스 [x1, y1, x2, y2]. None이면 자동 감지
            
        Returns:
            Dict: 분석 결과
        """
        try:
            # 바운딩 박스가 없으면 자동 감지
            if bbox is None:
                detected_vehicles = self.detect_vehicles_in_image(image_path)
                if detected_vehicles:
                    bbox = detected_vehicles[0]["bbox"]  # 가장 큰 차량 선택
                else:
                    # 차량이 감지되지 않으면 기본 영역 사용
                    bbox = self.detector.get_default_bbox(image_path)
                    if bbox is None:
                        return self._error_response("이미지 처리 실패")
            
            # 바운딩 박스 영역 크롭
            cropped_image = self.detector.crop_vehicle_region(image_path, bbox)
            if cropped_image is None:
                return self._error_response("영역 크롭 실패")
            
            # 크롭된 이미지를 임시 저장
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                cropped_image.save(tmp_file.name, 'JPEG')
                cropped_path = tmp_file.name
            
            try:
                # 크롭된 이미지로 분석
                result = self.analyze_vehicle_from_image(cropped_path)
                
                # 바운딩 박스 정보 추가
                result['bbox_used'] = bbox
                result['cropped'] = True
                
                return result
                
            finally:
                # 임시 파일 삭제
                try:
                    os.unlink(cropped_path)
                except:
                    pass
                    
        except Exception as e:
            print(f"바운딩 박스 분석 중 오류 발생: {e}")
            return self._error_response(str(e))

    def encode_image(self, image_path: str) -> str:
        """이미지를 base64로 인코딩"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def analyze_vehicle_from_text(self, description: str) -> Dict:
        """텍스트 설명으로부터 차량 정보 추출"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 차량 인식 전문가입니다. 
주어진 차량 설명을 바탕으로 다음 JSON 형식으로 응답해주세요:

{
    "brand_kr": "브랜드명 한글 (예: 현대, 기아, BMW, 벤츠 등)",
    "brand_en": "브랜드명 영문 (예: Hyundai, Kia, BMW, Mercedes-Benz 등)",
    "model_kr": "차종명 한글 (예: 소나타, K5, 3시리즈 등)",
    "model_en": "차종명 영문 (예: Sonata, K5, 3 Series 등)",
    "year": "연식 (예: 2023, 2022 등, 확실하지 않으면 null)",
    "year_info": "연식 추정 근거 (디자인 특징, 페이스리프트 정보 등)",
    "confidence": 85
}

연식 추정 방법:
1. 디자인 특징 (헤드램프, 그릴, 범퍼 디자인)
2. 페이스리프트 및 모델 변경 정보
3. 기술적 특징 (LED 헤드램프, DRL 등)
4. 내부 인테리어 변화

정확하지 않은 정보는 null로 표시하고, confidence는 0-100 사이의 신뢰도 점수입니다."""
                    },
                    {
                        "role": "user",
                        "content": f"다음 차량 설명을 분석해주세요: {description}"
                    }
                ],
                temperature=0.1,
                max_tokens=400
            )
            
            result = response.choices[0].message.content
            return self._parse_response(result)
            
        except Exception as e:
            print(f"텍스트 분석 중 오류 발생: {e}")
            return self._error_response(str(e))
    
    def analyze_vehicle_from_image(self, image_path: str) -> Dict:
        """이미지로부터 차량 정보 추출"""
        try:
            base64_image = self.encode_image(image_path)
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": """당신은 차량 인식 전문가입니다. 
주어진 차량 이미지를 분석하여 다음 JSON 형식으로 응답해주세요:

{
    "brand_kr": "브랜드명 한글 (예: 현대, 기아, BMW, 벤츠 등)",
    "brand_en": "브랜드명 영문 (예: Hyundai, Kia, BMW, Mercedes-Benz 등)",
    "model_kr": "차종명 한글 (예: 소나타, K5, 3시리즈 등)",
    "model_en": "차종명 영문 (예: Sonata, K5, 3 Series 등)",
    "year": "연식 (예: 2023, 2022 등, 확실하지 않으면 null)",
    "year_info": "연식 추정 근거 (디자인 특징, 페이스리프트 정보 등)",
    "confidence": 85
}

연식 추정을 위해 다음을 분석하세요:
1. 헤드램프 디자인 (LED, DRL 패턴)
2. 프론트 그릴 모양과 크롬 장식
3. 범퍼 디자인과 에어 인테이크
4. 휠 디자인과 크기
5. 사이드미러와 도어 핸들 디자인
6. 후미등과 리어 범퍼 스타일
7. 브랜드 엠블럼과 모델명 배지

정확하지 않은 정보는 null로 표시하고, confidence는 0-100 사이의 신뢰도 점수입니다."""
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "이 차량 이미지를 분석하여 브랜드, 차종, 연식을 알려주세요. 특히 연식 추정에 도움이 되는 디자인 특징들을 자세히 설명해주세요."
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.1,
                max_tokens=500
            )
            
            result = response.choices[0].message.content
            return self._parse_response(result)
            
        except Exception as e:
            print(f"이미지 분석 중 오류 발생: {e}")
            return self._error_response(str(e))
    
    def _parse_response(self, response: str) -> Dict:
        """OpenAI 응답을 파싱하여 구조화된 데이터로 변환"""
        try:
            # JSON 부분만 추출
            start = response.find('{')
            end = response.rfind('}') + 1
            if start != -1 and end != -1:
                json_str = response[start:end]
                parsed = json.loads(json_str)
                
                # 구버전 호환성을 위해 brand, model 필드 추가
                if 'brand_kr' in parsed and 'brand' not in parsed:
                    parsed['brand'] = parsed['brand_kr']
                if 'model_kr' in parsed and 'model' not in parsed:
                    parsed['model'] = parsed['model_kr']
                    
                return parsed
            else:
                raise ValueError("JSON 형식을 찾을 수 없습니다")
                
        except (json.JSONDecodeError, ValueError) as e:
            print(f"응답 파싱 오류: {e}")
            return {
                "brand_kr": None,
                "brand_en": None,
                "brand": None,
                "model_kr": None,
                "model_en": None,
                "model": None,
                "year": None,
                "year_info": None,
                "confidence": 0,
                "error": f"파싱 오류: {str(e)}",
                "raw_response": response
            }
    
    def _error_response(self, error_message: str) -> Dict:
        """에러 응답 생성"""
        return {
            "brand_kr": None,
            "brand_en": None,
            "brand": None,
            "model_kr": None,
            "model_en": None,
            "model": None,
            "year": None,
            "year_info": None,
            "confidence": 0,
            "error": error_message
        }
    
    def analyze_multiple_images(self, image_paths: List[str], progress_callback=None) -> List[Dict]:
        """여러 이미지를 순차적으로 분석"""
        results = []
        
        for i, image_path in enumerate(image_paths):
            if progress_callback:
                progress_callback(i, len(image_paths), os.path.basename(image_path))
            
            start_time = time.time()
            result = self.analyze_vehicle_from_image(image_path)
            processing_time = time.time() - start_time
            
            # 입력 정보와 처리 시간 추가
            result['input'] = os.path.basename(image_path)
            result['input_path'] = image_path
            result['processing_time'] = round(processing_time, 2)
            
            results.append(result)
            
            # API 호출 제한을 위한 짧은 대기
            time.sleep(0.5)
        
        return results
    
    def batch_analyze(self, inputs: list, input_type: str = "text") -> list:
        """배치 분석"""
        results = []
        for i, input_data in enumerate(inputs):
            print(f"분석 중... {i+1}/{len(inputs)}")
            
            if input_type == "text":
                result = self.analyze_vehicle_from_text(input_data)
            elif input_type == "image":
                result = self.analyze_vehicle_from_image(input_data)
            else:
                result = self._error_response(f"지원하지 않는 입력 타입: {input_type}")
            
            results.append(result)
        
        return results

if __name__ == "__main__":
    # 테스트 코드
    extractor = VehicleDataExtractor()
    
    # 텍스트 분석 테스트
    test_description = "2022년식 현대 소나타 하이브리드 화이트 색상, LED 헤드램프와 카스케이딩 그릴"
    result = extractor.analyze_vehicle_from_text(test_description)
    print("텍스트 분석 결과:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
