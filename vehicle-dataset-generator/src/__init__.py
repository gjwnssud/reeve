"""
차량 데이터셋 생성기 패키지

LLM 파인튜닝을 위한 차량 데이터 추출 및 데이터셋 생성 도구
"""

__version__ = "1.0.0"
__author__ = "HZN"
__description__ = "Vehicle Dataset Generator for LLM Fine-tuning"

from src.core.vehicle_data_extractor import VehicleDataExtractor
from src.core.dataset_manager import DatasetManager

__all__ = [
    "VehicleDataExtractor",
    "DatasetManager"
]
