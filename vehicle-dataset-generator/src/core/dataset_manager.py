import json
import os
from datetime import datetime
from typing import List, Dict
import glob
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

class DatasetManager:
    """데이터셋 JSON 파일 관리 클래스"""
    
    def __init__(self, dataset_path=None):
        # 환경변수에서 경로 가져오기, 없으면 기본값 사용
        if dataset_path is None:
            dataset_path = os.getenv('DATASET_DIR', '../../dataset')
        
        self.dataset_path = os.path.abspath(dataset_path)
        self.max_file_size_mb = 10  # 10MB 제한
        self.max_items_per_file = 1000  # 파일당 최대 항목 수
        
        # dataset 폴더 생성
        os.makedirs(self.dataset_path, exist_ok=True)
        print(f"📁 데이터셋 경로: {self.dataset_path}")
        
    def get_current_dataset_file(self):
        """현재 사용할 데이터셋 파일 경로 반환"""
        # 기존 파일들 확인
        pattern = os.path.join(self.dataset_path, "vehicle_dataset_*.json")
        existing_files = glob.glob(pattern)
        
        if not existing_files:
            # 첫 번째 파일 생성
            return os.path.join(self.dataset_path, "vehicle_dataset_001.json")
        
        # 가장 최근 파일 확인
        latest_file = max(existing_files, key=os.path.getctime)
        
        # 파일 크기 및 항목 수 확인
        if self._need_new_file(latest_file):
            # 새 파일 번호 생성
            file_numbers = []
            for file in existing_files:
                try:
                    num = int(os.path.basename(file).split('_')[-1].split('.')[0])
                    file_numbers.append(num)
                except:
                    continue
            
            next_num = max(file_numbers) + 1 if file_numbers else 1
            return os.path.join(self.dataset_path, f"vehicle_dataset_{next_num:03d}.json")
        
        return latest_file
    
    def _need_new_file(self, file_path):
        """새 파일이 필요한지 확인"""
        if not os.path.exists(file_path):
            return False
            
        # 파일 크기 확인
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb >= self.max_file_size_mb:
            return True
        
        # 항목 수 확인
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) >= self.max_items_per_file:
                    return True
        except:
            pass
            
        return False
    
    def save_results(self, results: List[Dict], source_type="image"):
        """분석 결과를 데이터셋에 저장"""
        if not results:
            return None
            
        current_file = self.get_current_dataset_file()
        
        # 기존 데이터 로드
        existing_data = []
        if os.path.exists(current_file):
            try:
                with open(current_file, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                    if not isinstance(existing_data, list):
                        existing_data = []
            except:
                existing_data = []
        
        # 새 데이터 추가
        timestamp = datetime.now().isoformat()
        for i, result in enumerate(results):
            dataset_entry = {
                "id": f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{i:03d}",
                "timestamp": timestamp,
                "source_type": source_type,
                "input": result.get("input", ""),
                "output": {
                    "brand_kr": result.get("brand_kr"),
                    "brand_en": result.get("brand_en"),
                    "model_kr": result.get("model_kr"),
                    "model_en": result.get("model_en"),
                    "year": result.get("year"),
                    "year_info": result.get("year_info"),
                    "confidence": result.get("confidence", 0)
                },
                "metadata": {
                    "has_error": "error" in result,
                    "error_message": result.get("error"),
                    "processing_time": result.get("processing_time")
                }
            }
            existing_data.append(dataset_entry)
        
        # 파일 저장
        with open(current_file, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
        
        return {
            "saved_file": current_file,
            "total_items": len(existing_data),
            "new_items": len(results),
            "file_size_mb": round(os.path.getsize(current_file) / (1024 * 1024), 2)
        }
    
    def get_dataset_stats(self):
        """데이터셋 통계 정보 반환"""
        pattern = os.path.join(self.dataset_path, "vehicle_dataset_*.json")
        files = glob.glob(pattern)
        
        total_items = 0
        total_size_mb = 0
        
        for file in files:
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        total_items += len(data)
                total_size_mb += os.path.getsize(file) / (1024 * 1024)
            except:
                continue
        
        return {
            "total_files": len(files),
            "total_items": total_items,
            "total_size_mb": round(total_size_mb, 3),
            "dataset_path": self.dataset_path
        }

if __name__ == "__main__":
    # 테스트 코드
    manager = DatasetManager()
    print("Dataset Manager 초기화 완료")
    print("통계:", manager.get_dataset_stats())
