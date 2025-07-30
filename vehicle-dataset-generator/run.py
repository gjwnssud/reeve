#!/usr/bin/env python3
"""
차량 분석기 실행 스크립트
"""

import os
import sys


def check_requirements():
    """필수 요구사항 체크"""
    try:
        import openai
        import dotenv
        import PIL
        print("✅ 필수 패키지 확인 완료")
        return True
    except ImportError as e:
        print(f"❌ 누락된 패키지: {e}")
        print("다음 명령어로 설치하세요: pip install -r requirements.txt")
        return False


def check_api_key():
    """API 키 확인"""
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ OPENAI_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일을 생성하고 API 키를 설정해주세요.")
        return False

    print("✅ API 키 확인 완료")
    return True


def main():
    print("🚗 차량 데이터셋 생성기 시작")
    print("=" * 40)

    # 요구사항 체크
    if not check_requirements():
        return

    if not check_api_key():
        return

    # 실행 옵션 선택
    print("\n실행할 버전을 선택하세요:")
    print("1. 웹 인터페이스 (추천)")
    print("2. GUI 버전 (tkinter 필요)")
    print("3. 커맨드라인 버전")
    print("4. 간단 테스트")

    choice = input("\n선택 (1-4): ").strip()

    if choice == "1":
        print("\n🌐 웹 인터페이스를 실행합니다...")
        print("📍 브라우저에서 http://localhost:4000 으로 접속하세요")
        try:
            import subprocess
            result = subprocess.run([sys.executable, "run_web.py"], check=True)
        except Exception as e:
            print(f"❌ 웹 인터페이스 실행 오류: {e}")

    elif choice == "2":
        print("\n🖥️  GUI 버전을 실행합니다...")
        try:
            import subprocess
            result = subprocess.run([sys.executable, "run_gui.py"], check=True)
        except Exception as e:
            print(f"❌ GUI 실행 오류: {e}")
            print("💡 macOS에서는 'brew install python-tk' 명령어로 tkinter를 설치하세요")

    elif choice == "3":
        print("\n💻 커맨드라인 버전을 실행합니다...")
        try:
            import subprocess
            result = subprocess.run([sys.executable, "run_cli.py"], check=True)
        except Exception as e:
            print(f"❌ 커맨드라인 실행 오류: {e}")

    elif choice == "4":
        print("\n🧪 간단 테스트를 실행합니다...")
        run_simple_test()

    else:
        print("❌ 잘못된 선택입니다.")


def run_simple_test():
    """간단한 테스트 실행"""
    try:
        from src.core.vehicle_data_extractor import VehicleDataExtractor
        import json

        print("VehicleDataExtractor 초기화 중...")
        extractor = VehicleDataExtractor()

        test_description = "2022년식 현대 소나타 하이브리드, LED 헤드램프, 카스케이딩 그릴"
        print(f"테스트 설명: {test_description}")
        print("분석 중...")

        result = extractor.analyze_vehicle_from_text(test_description)

        print("\n=== 분석 결과 ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if result.get('confidence', 0) > 70:
            print("\n✅ 테스트 성공! 시스템이 정상 작동합니다.")
        else:
            print("\n⚠️  신뢰도가 낮습니다. API 응답을 확인해주세요.")

    except Exception as e:
        print(f"❌ 테스트 실패: {e}")


if __name__ == "__main__":
    main()
