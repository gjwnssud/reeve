from difflib import SequenceMatcher
from typing import Dict, List, Optional

from .vehicle_info_service import VehicleInfoService


class VehicleMatchingService:
    """ChatGPT 분석 결과와 데이터베이스 매칭 서비스"""
    
    def __init__(self):
        self.vehicle_service = VehicleInfoService()
        self.similarity_threshold = 0.6  # 유사도 임계값
    
    def match_chatgpt_result(self, chatgpt_result: Dict) -> Dict:
        """
        ChatGPT 분석 결과를 데이터베이스와 매칭
        
        Args:
            chatgpt_result: ChatGPT API 응답 결과
            
        Returns:
            Dict: 매칭 결과와 추천 정보
        """
        result = {
            'chatgpt_result': chatgpt_result,
            'manufacturer_match': None,
            'model_match': None,
            'manufacturer_candidates': [],
            'model_candidates': [],
            'match_confidence': 0.0,
            'recommendations': {
                'manufacturer_id': None,
                'model_id': None,
                'manufacturer_code': None,
                'model_code': None
            }
        }
        
        # 제조사 매칭
        manufacturer_match = self._match_manufacturer(chatgpt_result)
        if manufacturer_match:
            result['manufacturer_match'] = manufacturer_match['best_match']
            result['manufacturer_candidates'] = manufacturer_match['candidates']
            result['recommendations']['manufacturer_id'] = manufacturer_match['best_match']['id']
            result['recommendations']['manufacturer_code'] = manufacturer_match['best_match']['code']
            
            # 모델 매칭 (제조사가 매칭된 경우에만)
            model_match = self._match_model(chatgpt_result, manufacturer_match['best_match']['id'])
            if model_match:
                result['model_match'] = model_match['best_match']
                result['model_candidates'] = model_match['candidates']
                result['recommendations']['model_id'] = model_match['best_match']['id']
                result['recommendations']['model_code'] = model_match['best_match']['code']
                
                # 전체 매칭 신뢰도 계산
                result['match_confidence'] = (
                    manufacturer_match['confidence'] * 0.4 + 
                    model_match['confidence'] * 0.6
                )
            else:
                result['match_confidence'] = manufacturer_match['confidence'] * 0.4
        
        return result
    
    def _match_manufacturer(self, chatgpt_result: Dict) -> Optional[Dict]:
        """제조사 매칭"""
        brand_kr = chatgpt_result.get('brand_kr', '')
        brand_en = chatgpt_result.get('brand_en', '')
        
        if not brand_kr and not brand_en:
            return None
        
        # 모든 제조사 조회
        all_manufacturers = self.vehicle_service.get_all_manufacturers()
        
        candidates = []
        
        for manufacturer in all_manufacturers:
            # 한글명 매칭
            kr_similarity = 0
            if brand_kr and manufacturer['korean_name']:
                kr_similarity = self._calculate_similarity(
                    brand_kr.lower(), 
                    manufacturer['korean_name'].lower()
                )
            
            # 영문명 매칭
            en_similarity = 0
            if brand_en and manufacturer['english_name']:
                en_similarity = self._calculate_similarity(
                    brand_en.lower(), 
                    manufacturer['english_name'].lower()
                )
            
            # 최대 유사도 사용
            max_similarity = max(kr_similarity, en_similarity)
            
            if max_similarity >= self.similarity_threshold:
                candidates.append({
                    **manufacturer,
                    'similarity': max_similarity,
                    'kr_similarity': kr_similarity,
                    'en_similarity': en_similarity
                })
        
        if not candidates:
            return None
        
        # 유사도 순으로 정렬
        candidates.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'best_match': candidates[0],
            'candidates': candidates[:5],  # 상위 5개만
            'confidence': candidates[0]['similarity']
        }
    
    def _match_model(self, chatgpt_result: Dict, manufacturer_id: int) -> Optional[Dict]:
        """모델 매칭"""
        model_kr = chatgpt_result.get('model_kr', '')
        model_en = chatgpt_result.get('model_en', '')
        
        if not model_kr and not model_en:
            return None
        
        # 해당 제조사의 모든 모델 조회
        models = self.vehicle_service.get_models_by_manufacturer_id(manufacturer_id)
        
        candidates = []
        
        for model in models:
            # 한글명 매칭
            kr_similarity = 0
            if model_kr and model['korean_name']:
                kr_similarity = self._calculate_similarity(
                    model_kr.lower(), 
                    model['korean_name'].lower()
                )
            
            # 영문명 매칭
            en_similarity = 0
            if model_en and model['english_name']:
                en_similarity = self._calculate_similarity(
                    model_en.lower(), 
                    model['english_name'].lower()
                )
            
            # 최대 유사도 사용
            max_similarity = max(kr_similarity, en_similarity)
            
            if max_similarity >= self.similarity_threshold:
                candidates.append({
                    **model,
                    'similarity': max_similarity,
                    'kr_similarity': kr_similarity,
                    'en_similarity': en_similarity
                })
        
        if not candidates:
            return None
        
        # 유사도 순으로 정렬
        candidates.sort(key=lambda x: x['similarity'], reverse=True)
        
        return {
            'best_match': candidates[0],
            'candidates': candidates[:5],  # 상위 5개만
            'confidence': candidates[0]['similarity']
        }
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """텍스트 유사도 계산"""
        if not text1 or not text2:
            return 0.0
        
        # 기본 문자열 매칭
        basic_similarity = SequenceMatcher(None, text1, text2).ratio()
        
        # 단어 포함 여부 체크 (부분 매칭)
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if words1 and words2:
            word_intersection = len(words1.intersection(words2))
            word_union = len(words1.union(words2))
            word_similarity = word_intersection / word_union if word_union > 0 else 0
        else:
            word_similarity = 0
        
        # 조합된 유사도 (문자열 매칭 70% + 단어 매칭 30%)
        combined_similarity = basic_similarity * 0.7 + word_similarity * 0.3
        
        return combined_similarity
    
    def get_manufacturer_candidates(self, search_term: str, limit: int = 10) -> List[Dict]:
        """제조사 후보 검색"""
        if not search_term:
            return []
        
        candidates = self.vehicle_service.search_manufacturers(search_term)
        return candidates[:limit]
    
    def get_model_candidates(self, manufacturer_id: int, search_term: str = "", limit: int = 10) -> List[Dict]:
        """모델 후보 검색"""
        if search_term:
            candidates = self.vehicle_service.search_vehicle_models(search_term, manufacturer_id)
        else:
            candidates = self.vehicle_service.get_models_by_manufacturer_id(manufacturer_id)
        
        return candidates[:limit]
    
    def validate_selection(self, manufacturer_id: int, model_id: int) -> Dict:
        """사용자 선택 검증"""
        # 제조사 검증
        manufacturer = self.vehicle_service.get_manufacturer_by_id(manufacturer_id)
        if not manufacturer:
            return {'valid': False, 'error': '존재하지 않는 제조사입니다.'}
        
        # 모델 검증
        model = self.vehicle_service.get_vehicle_model_by_id(model_id)
        if not model:
            return {'valid': False, 'error': '존재하지 않는 모델입니다.'}
        
        # 제조사-모델 관계 검증
        if model['manufacturer_id'] != manufacturer_id:
            return {'valid': False, 'error': '제조사와 모델이 일치하지 않습니다.'}
        
        return {
            'valid': True,
            'manufacturer': manufacturer,
            'model': model
        }
