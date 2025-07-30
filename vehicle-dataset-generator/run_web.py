#!/usr/bin/env python3
"""
웹 인터페이스 직접 실행 스크립트
"""

# 환경변수 로드
from dotenv import load_dotenv

load_dotenv()

# 임포트 시도
try:
    from src.core.vehicle_data_extractor import VehicleDataExtractor
    from src.core.dataset_manager import DatasetManager

    # Flask 앱 실행
    from web.app import app

    if __name__ == "__main__":
        print("🌐 웹 인터페이스를 시작합니다...")
        print("📍 브라우저에서 http://localhost:4000 으로 접속하세요")
        print("⏹️  종료하려면 Ctrl+C를 누르세요")
        app.run(debug=True, host='0.0.0.0', port=4000)

except ImportError as e:
    print(f"❌ 모듈 임포트 오류: {e}")
    print("💡 다음 명령어로 실행해보세요:")
    print("   python run.py")
    print("   그리고 옵션 1번을 선택하세요.")
