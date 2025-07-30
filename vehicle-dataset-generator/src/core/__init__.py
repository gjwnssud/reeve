"""
핵심 로직 모듈

차량 데이터 추출 및 데이터셋 관리 클래스들
"""

from .vehicle_data_extractor import VehicleDataExtractor
from .dataset_manager import DatasetManager

__all__ = [
    "VehicleDataExtractor", 
    "DatasetManager"
]
