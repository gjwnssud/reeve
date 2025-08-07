@echo off
setlocal EnableDelayedExpansion

REM =============================================================================
REM 차량 데이터셋 생성기 - Windows 실행 스크립트  
REM =============================================================================

title 차량 데이터셋 생성기
color 0A

echo.
echo 🚗 차량 데이터셋 생성기 시작
echo ==========================
echo.

REM 현재 디렉토리로 이동
cd /d "%~dp0"

REM Python 설치 확인
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python이 설치되지 않았거나 PATH에 없습니다.
    echo 🔗 https://www.python.org/downloads/ 에서 Python 3.8+ 설치
    echo 💡 설치 시 "Add Python to PATH" 옵션을 체크하세요
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYTHON_VERSION=%%i
echo ✅ Python 확인됨: %PYTHON_VERSION%

REM 가상환경 확인 및 생성
if not exist ".venv" (
    echo 📦 가상환경을 생성합니다...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ 가상환경 생성 실패
        pause
        exit /b 1
    )
)

REM 가상환경 활성화
echo 🔧 가상환경 활성화 중...
call .venv\Scripts\activate.bat

REM 의존성 설치/업데이트  
echo 📚 필수 패키지 설치 중...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

if errorlevel 1 (
    echo ❌ 패키지 설치 실패
    echo 💡 수동 설치 명령어: pip install -r requirements.txt
    pause
    exit /b 1
)

REM .env 파일 확인
if not exist ".env" (
    echo ⚠️  .env 파일이 없습니다.
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo 📝 .env.example을 복사했습니다.
        echo 🔑 .env 파일을 열어서 OPENAI_API_KEY를 설정하세요.
        
        REM 기본 에디터로 .env 열기
        if exist "C:\Program Files\Microsoft VS Code\Code.exe" (
            echo 📝 VS Code로 .env 파일을 엽니다...
            "C:\Program Files\Microsoft VS Code\Code.exe" .env
        ) else (
            echo 📝 메모장으로 .env 파일을 엽니다...
            notepad .env
        )
        
        pause
    ) else (
        echo ❌ .env.example 파일도 없습니다.
        pause
        exit /b 1
    )
)

REM API 키 확인
findstr /C:"OPENAI_API_KEY=sk-" .env >nul 2>&1
if errorlevel 1 (
    echo ⚠️  OpenAI API 키가 설정되지 않았을 수 있습니다.
    echo 🔑 .env 파일에서 OPENAI_API_KEY=your_key_here 형태로 설정하세요.
)

:MENU
echo.
echo 🎯 실행할 인터페이스를 선택하세요:
echo 1. 🌐 웹 인터페이스 (추천)
echo 2. 🖥️  GUI 인터페이스
echo 3. 💻 커맨드라인 인터페이스  
echo 4. 🧪 간단 테스트
echo 5. ❌ 종료
echo.

set /p choice="선택 (1-5): "

if "%choice%"=="1" (
    echo.
    echo 🌐 웹 인터페이스를 시작합니다...
    echo 📍 브라우저에서 http://localhost:4000 으로 접속하세요
    echo ⏹️  종료하려면 Ctrl+C를 누르세요
    echo.
    python run_web.py
    goto END
) else if "%choice%"=="2" (
    echo.
    echo 🖥️  GUI 인터페이스를 시작합니다...
    python run_gui.py
    goto END
) else if "%choice%"=="3" (
    echo.
    echo 💻 커맨드라인 인터페이스를 시작합니다...
    python run_cli.py
    goto END
) else if "%choice%"=="4" (
    echo.
    echo 🧪 간단 테스트를 실행합니다...
    python -c "import sys, os; sys.path.append('.'); from src.core.vehicle_data_extractor import VehicleDataExtractor; import json; extractor = VehicleDataExtractor(); result = extractor.analyze_vehicle_from_text('2022년식 현대 소나타'); print('✅ 테스트 성공!'); print(json.dumps(result, ensure_ascii=False, indent=2))" 2>nul
    if errorlevel 1 (
        echo ❌ 테스트 실패 - API 키나 네트워크 연결을 확인하세요
    )
    pause
    goto MENU
) else if "%choice%"=="5" (
    echo 👋 프로그램을 종료합니다.
    goto END
) else (
    echo ❌ 잘못된 선택입니다. 1-5 중에서 선택하세요.
    goto MENU
)

:END
echo.
echo 🎉 실행 완료!
pause
