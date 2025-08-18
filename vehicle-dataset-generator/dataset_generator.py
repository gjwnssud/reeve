import json
import os
import glob
from datetime import datetime
from config import Config

class DatasetGenerator:
    def __init__(self):
        self.config = Config()
        self.ensure_dataset_folder()
    
    def ensure_dataset_folder(self):
        """데이터셋 폴더 생성"""
        os.makedirs(self.config.DATASET_FOLDER, exist_ok=True)
    
    def get_current_dataset_file(self):
        """현재 사용할 데이터셋 파일 경로 반환"""
        # 기존 데이터셋 파일들 확인
        pattern = os.path.join(self.config.DATASET_FOLDER, "llava_dataset_*.json")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            # 첫 번째 파일 생성
            return os.path.join(self.config.DATASET_FOLDER, "llava_dataset_001.json")
        
        # 가장 최근 파일 확인
        latest_file = max(existing_files, key=os.path.getctime)
        
        # 파일 크기 확인 (데이터 개수 확인)
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if len(data) >= self.config.MAX_DATASET_SIZE:
                    # 새 파일 생성 필요
                    file_number = len(existing_files) + 1
                    return os.path.join(self.config.DATASET_FOLDER, f"llava_dataset_{file_number:03d}.json")
                else:
                    return latest_file
        except:
            # 파일 읽기 실패시 새 파일 생성
            file_number = len(existing_files) + 1
            return os.path.join(self.config.DATASET_FOLDER, f"llava_dataset_{file_number:03d}.json")
    
    def load_existing_data(self, file_path):
        """기존 데이터셋 파일 로드"""
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def generate_llava_entry(self, image_path, analysis_result, bbox=None):
        """LLaVa 형식의 데이터 엔트리 생성"""
        if analysis_result['status'] != 'success':
            return None
        
        # 상대 경로로 변환
        relative_image_path = os.path.relpath(image_path, self.config.DATASET_FOLDER)
        
        # 대화 형식 데이터 생성
        conversations = [
            {
                "from": "human",
                "value": "이 이미지에 있는 차량의 제조사와 모델을 알려주세요."
            },
            {
                "from": "gpt", 
                "value": f"이 차량은 {analysis_result['manufacturer_korean_name']}({analysis_result['manufacturer_english_name']})의 {analysis_result['model_korean_name']}({analysis_result['model_english_name']}) 모델입니다."
            }
        ]
        
        entry = {
            "id": f"vehicle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.basename(image_path)}",
            "image": relative_image_path,
            "conversations": conversations,
            "metadata": {
                "manufacturer_code": analysis_result['manufacturer_code'],
                "manufacturer_english_name": analysis_result['manufacturer_english_name'],
                "manufacturer_korean_name": analysis_result['manufacturer_korean_name'],
                "manufacturer_confidence": analysis_result['manufacturer_confidence'],
                "model_code": analysis_result['model_code'],
                "model_english_name": analysis_result['model_english_name'],
                "model_korean_name": analysis_result['model_korean_name'],
                "model_confidence": analysis_result['model_confidence'],
                "created_at": datetime.now().isoformat(),
                "bbox": bbox
            }
        }
        
        return entry
    
    def add_to_dataset(self, image_path, analysis_result, bbox=None):
        """데이터셋에 새 엔트리 추가"""
        try:
            # LLaVa 엔트리 생성
            entry = self.generate_llava_entry(image_path, analysis_result, bbox)
            if not entry:
                return False
            
            # 현재 데이터셋 파일 경로
            dataset_file = self.get_current_dataset_file()
            
            # 기존 데이터 로드
            existing_data = self.load_existing_data(dataset_file)
            
            # 새 엔트리 추가
            existing_data.append(entry)
            
            # 파일에 저장
            with open(dataset_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
            print(f"Added entry to dataset: {dataset_file}")
            return True
            
        except Exception as e:
            print(f"Error adding to dataset: {e}")
            return False
    
    def get_dataset_statistics(self):
        """데이터셋 통계 정보 반환"""
        try:
            pattern = os.path.join(self.config.DATASET_FOLDER, "llava_dataset_*.json")
            dataset_files = glob.glob(pattern)
            
            total_entries = 0
            file_info = []
            
            for file_path in dataset_files:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        entries = len(data)
                        total_entries += entries
                        
                        file_info.append({
                            'file': os.path.basename(file_path),
                            'entries': entries,
                            'created': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat()
                        })
                except:
                    continue
            
            return {
                'total_files': len(dataset_files),
                'total_entries': total_entries,
                'files': file_info
            }
            
        except Exception as e:
            print(f"Error getting dataset statistics: {e}")
            return {
                'total_files': 0,
                'total_entries': 0,
                'files': []
            }
    
    def create_custom_entry(self, image_path, manufacturer_code, manufacturer_english, 
                          manufacturer_korean, model_code, model_english, model_korean, bbox=None):
        """수동 입력된 데이터로 엔트리 생성"""
        try:
            analysis_result = {
                'status': 'success',
                'manufacturer_code': manufacturer_code,
                'manufacturer_english_name': manufacturer_english,
                'manufacturer_korean_name': manufacturer_korean,
                'manufacturer_confidence': 1.0,
                'model_code': model_code,
                'model_english_name': model_english,
                'model_korean_name': model_korean,
                'model_confidence': 1.0
            }
            
            return self.add_to_dataset(image_path, analysis_result, bbox)
            
        except Exception as e:
            print(f"Error creating custom entry: {e}")
            return False

# 전역 데이터셋 생성기 인스턴스
dataset_generator = DatasetGenerator()
