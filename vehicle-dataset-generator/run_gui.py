#!/usr/bin/env python3
"""
GUI 인터페이스 직접 실행 스크립트
"""

# 환경변수 로드
from dotenv import load_dotenv

load_dotenv()

# 임포트 시도
try:
    from src.core.vehicle_data_extractor import VehicleDataExtractor
    from src.core.dataset_manager import DatasetManager
    from src.interfaces.gui import main as gui_main

    if __name__ == "__main__":
        gui_main()

except ImportError as e:
    print(f"❌ 모듈 임포트 오류: {e}")
    print("💡 다음 명령어로 실행해보세요:")
    print("   python run.py")
    print("   그리고 옵션 2번을 선택하세요.")
