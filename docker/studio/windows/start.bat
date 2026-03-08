@echo off
chcp 65001 > nul
cd /d "%~dp0..\.."
:: 실행 위치: docker/

echo [Reeve Studio] Windows 서비스 시작 (GPU)
docker compose -f docker-compose.yml -f studio\windows\docker-compose.windows.yml up -d

if errorlevel 1 (
    echo [오류] 서비스 시작에 실패했습니다. 로그를 확인하세요:
    echo        docker compose -f docker-compose.yml -f studio\windows\docker-compose.windows.yml logs
    pause
    exit /b 1
)

echo.
echo 서비스가 시작되었습니다:
echo   Studio   : http://localhost:8000
echo   Identifier: http://localhost:8001
echo   LLaMA-Factory: http://localhost:7860
echo   Qdrant   : http://localhost:6333/dashboard
