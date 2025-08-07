#!/bin/bash

# =============================================================================
# 차량 데이터셋 생성기 - macOS/Linux 실행 스크립트
# =============================================================================

echo "🚗 차량 데이터셋 생성기 시작"
echo "=========================="

# 스크립트 디렉토리로 이동
cd "$(dirname "$0")"

# Python 설치 확인
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3가 설치되지 않았습니다."
    echo "🔗 https://www.python.org/downloads/ 에서 Python 3.8+ 설치"
    read -p "엔터를 눌러 종료..."
    exit 1
fi

echo "✅ Python 확인됨: $(python3 --version)"

# 가상환경 확인 및 생성
if [ ! -d ".venv" ]; then
    echo "📦 가상환경을 생성합니다..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "❌ 가상환경 생성 실패"
        read -p "엔터를 눌러 종료..."
        exit 1
    fi
fi

# 가상환경 활성화
echo "🔧 가상환경 활성화 중..."
source .venv/bin/activate

# 의존성 설치/업데이트
echo "📚 필수 패키지 설치 중..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

if [ $? -ne 0 ]; then
    echo "❌ 패키지 설치 실패"
    echo "💡 수동 설치 명령어: pip install -r requirements.txt"
    read -p "엔터를 눌러 종료..."
    exit 1
fi

# macOS tkinter 확인
if [[ "$OSTYPE" == "darwin"* ]]; then
    python3 -c "import tkinter" 2>/dev/null || {
        echo "❌ tkinter가 설치되지 않았습니다."
        echo "💡 다음 명령어로 설치하세요:"
        echo "   brew install python-tk"
        echo "   또는"
        echo "   brew install tkinter"
        read -p "설치 후 엔터를 눌러 계속..."
    }
fi

# .env 파일 확인
if [ ! -f ".env" ]; then
    echo "⚠️  .env 파일이 없습니다."
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "📝 .env.example을 복사했습니다."
        echo "🔑 .env 파일을 열어서 OPENAI_API_KEY를 설정하세요."
        
        # 기본 에디터로 .env 열기 시도
        if command -v code &> /dev/null; then
            echo "📝 VS Code로 .env 파일을 엽니다..."
            code .env
        elif command -v nano &> /dev/null; then
            echo "📝 nano 에디터로 .env 파일을 엽니다..."
            nano .env
        else
            echo "📝 수동으로 .env 파일을 편집하세요."
        fi
        
        read -p "API 키 설정 후 엔터를 눌러 계속..."
    else
        echo "❌ .env.example 파일도 없습니다."
        read -p "엔터를 눌러 종료..."
        exit 1
    fi
fi

# API 키 확인
if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null; then
    echo "⚠️  OpenAI API 키가 설정되지 않았을 수 있습니다."
    echo "🔑 .env 파일에서 OPENAI_API_KEY=your_key_here 형태로 설정하세요."
fi

echo ""
echo "🎯 실행할 인터페이스를 선택하세요:"
echo "1. 🌐 웹 인터페이스 (추천)"
echo "2. 🖥️  GUI 인터페이스"  
echo "3. 💻 커맨드라인 인터페이스"
echo "4. 🧪 간단 테스트"
echo "5. ❌ 종료"
echo ""

while true; do
    read -p "선택 (1-5): " choice
    case $choice in
        1)
        echo ""
        echo "🌐 웹 인터페이스를 시작합니다..."
        echo "📍 브라우저에서 http://localhost:4000 으로 접속하세요"
        echo "⏹️  종료하려면 Ctrl+C를 누르세요"
        echo ""
        python run_web.py
        break
        ;;
        2)
        echo ""
        echo "🖥️  GUI 인터페이스를 시작합니다..."
        python run_gui.py
        break
        ;;
        3)
        echo ""
        echo "💻 커맨드라인 인터페이스를 시작합니다..."
        python run_cli.py
        break
        ;;
        4)
            echo ""
            echo "🧪 간단 테스트를 실행합니다..."
            python -c "
import sys, os
sys.path.append('.')
from src.core.vehicle_data_extractor import VehicleDataExtractor
import json

try:
    extractor = VehicleDataExtractor()
    result = extractor.analyze_vehicle_from_text('2022년식 현대 소나타')
    print('✅ 테스트 성공!')
    print(json.dumps(result, ensure_ascii=False, indent=2))
except Exception as e:
    print(f'❌ 테스트 실패: {e}')
"
            read -p "엔터를 눌러 메뉴로 돌아가기..."
            echo ""
            ;;
        5)
            echo "👋 프로그램을 종료합니다."
            exit 0
            ;;
        *)
            echo "❌ 잘못된 선택입니다. 1-5 중에서 선택하세요."
            ;;
    esac
done

echo ""
echo "🎉 실행 완료!"
