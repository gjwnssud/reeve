@echo off
setlocal EnableDelayedExpansion
chcp 65001 > nul
cd /d "%~dp0..\.."
:: 실행 위치: docker/

echo [Reeve Studio] Windows 초기 설정
echo ======================================

:: ── 1. Docker Desktop 확인 ──────────────────
echo [1/4] Docker Desktop 확인 중...
docker info > nul 2>&1
if errorlevel 1 (
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo        Docker Desktop을 시작한 후 다시 실행하세요.
    pause
    exit /b 1
)
echo       OK

:: ── 2. NVIDIA GPU 확인 ──────────────────────
echo [2/4] NVIDIA GPU 확인 중...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [경고] NVIDIA GPU를 감지하지 못했습니다.
    echo        GPU 없이 계속 진행하면 ollama/llamafactory가 CPU로 실행됩니다.
    set /p CONTINUE="계속 진행하시겠습니까? (y/N): "
    if /i "!CONTINUE!" neq "y" exit /b 1
) else (
    for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name --format=csv^,noheader 2^>nul') do (
        echo       감지된 GPU: %%g
    )
)

:: ── 3. .env 파일 생성 ───────────────────────
echo [3/4] 환경변수 파일 확인 중...
if not exist "..\\.env" (
    if exist "..\\.env.example" (
        copy "..\\.env.example" "..\\.env" > nul
        echo       .env 파일이 생성되었습니다.
        echo.
        echo  ★ 필수 수정 항목:
        echo    - OPENAI_API_KEY
        echo    - MYSQL_ROOT_PASSWORD
        echo    - MYSQL_PASSWORD
        echo.
        echo    ..\\.env 파일을 편집한 후 start.bat을 실행하세요.
        start notepad "..\\.env"
        pause
        exit /b 0
    ) else (
        echo [오류] .env.example 파일을 찾을 수 없습니다.
        pause
        exit /b 1
    )
) else (
    echo       .env 파일 존재 확인
)

:: ── 4. 이미지 빌드 / Pull ───────────────────
echo [4/4] Docker 이미지 준비 중...
docker compose -f docker-compose.yml -f studio\windows\docker-compose.windows.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f studio\windows\docker-compose.windows.yml build

echo.
echo ======================================
echo 초기 설정 완료. start.bat으로 서비스를 시작하세요.
echo ======================================
pause
