import openai
import base64
import json
from config import Config
from database import db
import time
import asyncio
from PIL import Image
import io
import re

class VehicleAnalyzer:
    def __init__(self):
        self.config = Config()
        openai.api_key = self.config.OPENAI_API_KEY
        self.client = openai.OpenAI(api_key=self.config.OPENAI_API_KEY)
    
    def crop_image_with_bbox(self, image_path, bbox):
        """바운딩 박스를 이용해 이미지 크롭"""
        try:
            with Image.open(image_path) as img:
                # bbox는 [x1, y1, x2, y2] 형태의 절대 좌표
                if len(bbox) == 4:
                    x1, y1, x2, y2 = bbox
                    # 좌표가 이미지 범위를 벗어나지 않도록 클램핑
                    x1 = max(0, min(x1, img.width))
                    y1 = max(0, min(y1, img.height))
                    x2 = max(x1, min(x2, img.width))
                    y2 = max(y1, min(y2, img.height))
                    
                    # 이미지 크롭
                    cropped = img.crop((x1, y1, x2, y2))
                    
                    # base64로 인코딩
                    buffer = io.BytesIO()
                    cropped.save(buffer, format='JPEG')
                    return base64.b64encode(buffer.getvalue()).decode('utf-8')
                else:
                    # bbox가 없거나 잘못된 경우 전체 이미지 사용
                    return self.encode_image(image_path)
        except Exception as e:
            print(f"Error cropping image with bbox: {e}")
            return self.encode_image(image_path)
    
    def encode_image(self, image_path):
        """이미지를 base64로 인코딩"""
        try:
            with open(image_path, "rb") as image_file:
                return base64.b64encode(image_file.read()).decode('utf-8')
        except Exception as e:
            print(f"Error encoding image: {e}")
            return None
    
    def analyze_manufacturer(self, image_path, bbox=None):
        """1차 분석: 제조사 식별"""
        try:
            # 데이터베이스에서 모든 제조사 코드 가져오기
            manufacturers = db.get_all_manufacturers()
            manufacturer_codes = [m['code'] for m in manufacturers]
            
            # 이미지 인코딩 (bbox 적용)
            if bbox:
                base64_image = self.crop_image_with_bbox(image_path, bbox)
            else:
                base64_image = self.encode_image(image_path)
                
            if not base64_image:
                return None
            
            # 프롬프트 생성
            prompt = f"""
            이 차량 이미지를 분석하여 제조사를 식별해주세요.
            
            다음 제조사 코드 중에서 정확히 일치하는 것을 선택해주세요:
            {', '.join(manufacturer_codes)}
            
            응답은 반드시 다음 JSON 형식으로만 제공해주세요:
            {{
                "manufacturer_code": "정확한_제조사_코드",
                "confidence": 0.0-1.0_사이의_신뢰도
            }}
            
            만약 확실하지 않다면 confidence를 낮게 설정해주세요.
            응답은 반드시 순수 JSON 형태로만 해주세요. 마크다운 코드 블록은 사용하지 마세요.
            """
            
            response = self.client.chat.completions.create(
                model=self.config.OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300
            )
            
            # 응답 파싱
            result = response.choices[0].message.content.strip()
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # JSON 파싱 실패시 텍스트에서 추출 시도
                return self.extract_manufacturer_from_text(result, manufacturer_codes)
                
        except Exception as e:
            print(f"Error analyzing manufacturer: {e}")
            return None
    
    def analyze_model(self, image_path, manufacturer_code, bbox=None):
        """2차 분석: 모델 식별"""
        try:
            # 해당 제조사의 모든 모델 코드 가져오기
            models = db.get_models_by_manufacturer(manufacturer_code)
            model_codes = [m['code'] for m in models]
            
            if not model_codes:
                return None
            
            # 이미지 인코딩 (bbox 적용)
            if bbox:
                base64_image = self.crop_image_with_bbox(image_path, bbox)
            else:
                base64_image = self.encode_image(image_path)
                
            if not base64_image:
                return None
            
            # 제조사 정보 가져오기
            manufacturer = db.get_manufacturer_by_code(manufacturer_code)
            manufacturer_name = manufacturer['english_name'] if manufacturer else manufacturer_code
            
            # 프롬프트 생성
            prompt = f"""
            이 {manufacturer_name} 차량 이미지를 분석하여 정확한 모델을 식별해주세요.
            
            다음 모델 코드 중에서 정확히 일치하는 것을 선택해주세요:
            {', '.join(model_codes)}
            
            응답은 반드시 다음 JSON 형식으로만 제공해주세요:
            {{
                "model_code": "정확한_모델_코드",
                "confidence": 0.0-1.0_사이의_신뢰도
            }}
            
            만약 확실하지 않다면 confidence를 낮게 설정해주세요.
            응답은 반드시 순수 JSON 형태로만 해주세요. 마크다운 코드 블록은 사용하지 마세요.
            """
            
            response = self.client.chat.completions.create(
                model=self.config.OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=300
            )

            # 응답 파싱
            result = response.choices[0].message.content.strip()
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                # JSON 파싱 실패시 텍스트에서 추출 시도
                return self.extract_model_from_text(result, model_codes)
                
        except Exception as e:
            print(f"Error analyzing model: {e}")
            return None
    
    def extract_manufacturer_from_text(self, text, manufacturer_codes):
        """텍스트에서 제조사 코드 추출"""
        text_lower = text.lower()
        for code in manufacturer_codes:
            if code.lower() in text_lower:
                return {"manufacturer_code": code, "confidence": 0.5}
        return None
    
    def extract_model_from_text(self, text, model_codes):
        """텍스트에서 모델 코드 추출"""
        text_lower = text.lower()
        for code in model_codes:
            if code.lower() in text_lower:
                return {"model_code": code, "confidence": 0.5}
        return None
    
    def analyze_vehicle_stream(self, image_path, bbox=None):
        """스트리밍 분석 제너레이터"""
        try:
            # 시작 메시지
            yield {
                'status': 'started',
                'message': '차량 분석을 시작합니다...',
                'progress': 0
            }

            # 1차: 제조사 분석
            yield {
                'status': 'analyzing_manufacturer',
                'message': '제조사를 분석하고 있습니다...',
                'progress': 10
            }
            
            manufacturer_result = self.analyze_manufacturer(image_path, bbox)
            
            if not manufacturer_result or 'manufacturer_code' not in manufacturer_result or manufacturer_result.get('confidence') == 0.0:
                yield {
                    'status': 'error',
                    'message': '제조사 식별에 실패했습니다.',
                    'progress': 100,
                    'file_path': image_path,
                }
                return
            
            manufacturer_code = manufacturer_result['manufacturer_code']
            manufacturer_confidence = manufacturer_result.get('confidence', 0.0)
            
            # 제조사 정보 조회
            manufacturer_info = db.get_manufacturer_by_code(manufacturer_code)
            
            yield {
                'status': 'manufacturer_completed',
                'message': f'제조사 분석 완료: {manufacturer_info["korean_name"] if manufacturer_info else manufacturer_code}',
                'manufacturer_code': manufacturer_code,
                'manufacturer_confidence': manufacturer_confidence,
                'manufacturer_english_name': manufacturer_info['english_name'] if manufacturer_info else '',
                'manufacturer_korean_name': manufacturer_info['korean_name'] if manufacturer_info else '',
                'progress': 50,
                'file_path': image_path,
            }
            
            # 2차: 모델 분석
            yield {
                'status': 'analyzing_model',
                'message': '모델을 분석하고 있습니다...',
                'progress': 60
            }
            
            model_result = self.analyze_model(image_path, manufacturer_code, bbox)
            
            if not model_result or 'model_code' not in model_result or model_result.get('confidence') == 0.0:
                yield {
                    'status': 'partial_success',
                    'message': '제조사는 식별되었지만 모델 분석에 실패했습니다.',
                    'manufacturer_code': manufacturer_code,
                    'manufacturer_confidence': manufacturer_confidence,
                    'manufacturer_english_name': manufacturer_info['english_name'] if manufacturer_info else '',
                    'manufacturer_korean_name': manufacturer_info['korean_name'] if manufacturer_info else '',
                    'progress': 100,
                    'file_path': image_path,
                }
                return
            
            model_code = model_result['model_code']
            model_confidence = model_result.get('confidence', 0.0)
            
            # 모델 정보 조회
            model_info = db.get_model_by_code(model_code)
            
            # 최종 결과
            yield {
                'status': 'success',
                'message': '차량 분석이 완료되었습니다.',
                'manufacturer_code': manufacturer_code,
                'manufacturer_confidence': manufacturer_confidence,
                'manufacturer_english_name': manufacturer_info['english_name'] if manufacturer_info else '',
                'manufacturer_korean_name': manufacturer_info['korean_name'] if manufacturer_info else '',
                'model_code': model_code,
                'model_confidence': model_confidence,
                'model_english_name': model_info['english_name'] if model_info else '',
                'model_korean_name': model_info['korean_name'] if model_info else '',
                'progress': 100,
                'bbox': bbox,
                'file_path': image_path,
            }
            
        except Exception as e:
            yield {
                'status': 'error',
                'message': f'분석 중 오류가 발생했습니다: {str(e)}',
                'progress': 100
            }

# 전역 분석기 인스턴스
analyzer = VehicleAnalyzer()
