import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
import os
from config import Config

class VehicleDetector:
    def __init__(self):
        self.config = Config()
        self.model = None
        self.load_model()
    
    def load_model(self):
        """YOLO 모델 로드"""
        yolo_model = self.config.YOLO_MODEL_PATH + self.config.YOLO_MODEL
        try:
            if os.path.exists(yolo_model):
                self.model = YOLO(yolo_model)
                print(f"{self.config.YOLO_MODEL} model loaded successfully")
            else:
                # 모델이 없으면 자동으로 다운로드
                print(f"{self.config.YOLO_MODEL} model not found, downloading...")
                self.model = YOLO(self.config.YOLO_MODEL)  # 자동 다운로드
                print(f"{self.config.YOLO_MODEL} model downloaded and loaded successfully")
        except Exception as e:
            print(f"Error loading {self.config.YOLO_MODEL} model: {e}")
    
    def detect_vehicles(self, image_path):
        """이미지에서 차량 탐지"""
        if not self.model:
            return []
        
        try:
            # 이미지 로드
            image = cv2.imread(image_path)
            if image is None:
                return []
            
            # YOLO 예측
            results = self.model(image_path)
            
            vehicles = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        # 차량 관련 클래스만 필터링 (COCO 데이터셋 기준)
                        # 2: car, 3: motorcycle, 5: bus, 7: truck
                        if int(box.cls[0]) in [2, 3, 5, 7]:
                            # 바운딩 박스 좌표 (x1, y1, x2, y2)
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            confidence = float(box.conf[0])
                            class_id = int(box.cls[0])
                            
                            vehicles.append({
                                'bbox': [x1, y1, x2, y2],
                                'confidence': confidence,
                                'class_id': class_id,
                                'class_name': self.get_class_name(class_id)
                            })
            
            return vehicles
        except Exception as e:
            print(f"Error detecting vehicles: {e}")
            return []
    
    def get_class_name(self, class_id):
        """클래스 ID를 이름으로 변환"""
        class_names = {
            2: 'car',
            3: 'motorcycle', 
            5: 'bus',
            7: 'truck'
        }
        return class_names.get(class_id, 'vehicle')
    
    def crop_vehicle_image(self, image_path, bbox, padding=10):
        """바운딩 박스 기준으로 차량 이미지 크롭"""
        try:
            image = cv2.imread(image_path)
            if image is None:
                return None
            
            h, w = image.shape[:2]
            x1, y1, x2, y2 = bbox
            
            # 패딩 적용
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(w, x2 + padding)
            y2 = min(h, y2 + padding)
            
            # 이미지 크롭
            cropped = image[y1:y2, x1:x2]
            
            return cropped
        except Exception as e:
            print(f"Error cropping vehicle image: {e}")
            return None
    
    def save_cropped_image(self, cropped_image, output_path):
        """크롭된 이미지 저장"""
        try:
            cv2.imwrite(output_path, cropped_image)
            return True
        except Exception as e:
            print(f"Error saving cropped image: {e}")
            return False

# 전역 탐지기 인스턴스
detector = VehicleDetector()
