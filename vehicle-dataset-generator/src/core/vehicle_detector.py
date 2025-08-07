import cv2
import numpy as np
from ultralytics import YOLO
from PIL import Image
import os
from typing import List, Dict, Tuple, Optional

class VehicleDetector:
    """YOLO를 사용한 차량 객체 감지 클래스"""
    
    def __init__(self):
        """YOLO 모델 초기화"""
        try:
            # YOLOv8 nano 모델 로드 (빠르고 가벼움)
            self.model = YOLO('yolov8n.pt')
            print("✅ YOLO 모델 로드 완료")
        except Exception as e:
            print(f"❌ YOLO 모델 로드 실패: {e}")
            self.model = None
    
    def detect_vehicles(self, image_path: str, confidence_threshold: float = 0.3) -> List[Dict]:
        """
        이미지에서 차량을 감지하고 바운딩 박스 반환
        
        Args:
            image_path: 이미지 파일 경로
            confidence_threshold: 신뢰도 임계값
            
        Returns:
            List[Dict]: 감지된 차량들의 바운딩 박스 정보
            [
                {
                    "bbox": [x1, y1, x2, y2],  # 바운딩 박스 좌표
                    "confidence": 0.85,         # 신뢰도
                    "class_name": "car",        # 클래스명
                    "area": 12000              # 영역 크기
                }
            ]
        """
        if self.model is None:
            return []
        
        try:
            # 이미지 로드 및 크기 확인
            image = cv2.imread(image_path)
            if image is None:
                print(f"❌ 이미지 로드 실패: {image_path}")
                return []
            
            height, width = image.shape[:2]
            
            # YOLO 추론
            results = self.model(image_path, verbose=False)
            
            # 차량 관련 클래스 ID (COCO dataset 기준)
            vehicle_classes = {
                2: 'car',
                3: 'motorcycle', 
                5: 'bus',
                7: 'truck'
            }
            
            detected_vehicles = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for i in range(len(boxes)):
                        # 바운딩 박스 좌표 (xyxy 형식)
                        bbox = boxes.xyxy[i].cpu().numpy()
                        confidence = float(boxes.conf[i].cpu().numpy())
                        class_id = int(boxes.cls[i].cpu().numpy())
                        
                        # 차량 클래스이고 신뢰도가 임계값 이상인 경우만
                        if class_id in vehicle_classes and confidence >= confidence_threshold:
                            x1, y1, x2, y2 = bbox
                            
                            # 좌표 정수로 변환 및 이미지 경계 내로 제한
                            x1 = max(0, int(x1))
                            y1 = max(0, int(y1))
                            x2 = min(width, int(x2))
                            y2 = min(height, int(y2))
                            
                            # 바운딩 박스 크기 계산
                            area = (x2 - x1) * (y2 - y1)
                            
                            # 너무 작은 영역은 제외
                            if area > 1000:  # 최소 1000 픽셀
                                detected_vehicles.append({
                                    "bbox": [x1, y1, x2, y2],
                                    "confidence": confidence,
                                    "class_name": vehicle_classes[class_id],
                                    "area": area
                                })
            
            # 면적 기준으로 정렬 (큰 것부터)
            detected_vehicles.sort(key=lambda x: x["area"], reverse=True)
            
            print(f"✅ 차량 {len(detected_vehicles)}대 감지됨")
            return detected_vehicles
            
        except Exception as e:
            print(f"❌ 차량 감지 중 오류: {e}")
            return []
    
    def crop_vehicle_region(self, image_path: str, bbox: List[int], padding: int = 10) -> Optional[Image.Image]:
        """
        바운딩 박스 영역을 크롭하여 PIL Image로 반환
        
        Args:
            image_path: 원본 이미지 경로
            bbox: 바운딩 박스 [x1, y1, x2, y2]
            padding: 여백 픽셀
            
        Returns:
            PIL.Image: 크롭된 이미지 또는 None
        """
        try:
            # 이미지 로드
            image = Image.open(image_path)
            width, height = image.size
            
            x1, y1, x2, y2 = bbox
            
            # 패딩 추가 및 경계 확인
            x1 = max(0, x1 - padding)
            y1 = max(0, y1 - padding)
            x2 = min(width, x2 + padding)
            y2 = min(height, y2 + padding)
            
            # 크롭
            cropped = image.crop((x1, y1, x2, y2))
            
            print(f"✅ 차량 영역 크롭 완료: {x2-x1}x{y2-y1}")
            return cropped
            
        except Exception as e:
            print(f"❌ 이미지 크롭 중 오류: {e}")
            return None
    
    def get_default_bbox(self, image_path: str) -> Optional[List[int]]:
        """
        차량이 감지되지 않은 경우 기본 바운딩 박스 반환
        (이미지 중앙 80% 영역)
        """
        try:
            image = Image.open(image_path)
            width, height = image.size
            
            # 이미지 중앙 80% 영역
            margin_w = int(width * 0.1)
            margin_h = int(height * 0.1)
            
            default_bbox = [
                margin_w,
                margin_h,
                width - margin_w,
                height - margin_h
            ]
            
            return default_bbox
            
        except Exception as e:
            print(f"❌ 기본 바운딩 박스 생성 실패: {e}")
            return None
    
    def visualize_detection(self, image_path: str, save_path: str = None) -> str:
        """
        감지된 차량에 바운딩 박스를 그려서 시각화
        
        Args:
            image_path: 원본 이미지 경로
            save_path: 저장할 경로 (None이면 자동 생성)
            
        Returns:
            str: 시각화된 이미지 경로
        """
        try:
            detected_vehicles = self.detect_vehicles(image_path)
            
            # 이미지 로드
            image = cv2.imread(image_path)
            
            # 바운딩 박스 그리기
            for i, vehicle in enumerate(detected_vehicles):
                bbox = vehicle["bbox"]
                confidence = vehicle["confidence"]
                class_name = vehicle["class_name"]
                
                x1, y1, x2, y2 = bbox
                
                # 색상 (BGR)
                color = (0, 255, 0) if i == 0 else (255, 0, 0)  # 첫 번째는 초록, 나머지는 빨강
                
                # 바운딩 박스 그리기
                cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
                
                # 라벨 텍스트
                label = f"{class_name} {confidence:.2f}"
                cv2.putText(image, label, (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
            
            # 저장 경로 설정
            if save_path is None:
                base_name = os.path.splitext(os.path.basename(image_path))[0]
                save_path = f"web/static/detected_{base_name}.jpg"
            
            # 저장
            cv2.imwrite(save_path, image)
            print(f"✅ 시각화 이미지 저장: {save_path}")
            
            return save_path
            
        except Exception as e:
            print(f"❌ 시각화 중 오류: {e}")
            return image_path  # 실패시 원본 반환

if __name__ == "__main__":
    # 테스트 코드
    detector = VehicleDetector()
    
    # 테스트 이미지가 있다면
    test_image = "test_car.jpg"
    if os.path.exists(test_image):
        vehicles = detector.detect_vehicles(test_image)
        print("감지된 차량들:")
        for i, vehicle in enumerate(vehicles):
            print(f"{i+1}. {vehicle}")
    else:
        print("테스트 이미지가 없습니다.")
