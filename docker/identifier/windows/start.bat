@echo off
chcp 65001 > nul
cd /d "%~dp0"
:: 실행 위치: docker/identifier/windows/

echo [Reeve Identifier] 서비스 시작 (GPU)
docker compose up -d

if errorlevel 1 (
    echo [오류] 서비스 시작에 실패했습니다. 로그를 확인하세요:
    echo        docker compose logs
    pause
    exit /b 1
)

echo.
echo 서비스가 시작되었습니다:
echo   Identifier API : http://localhost:8001
echo   Identifier Docs: http://localhost:8001/docs
echo   Qdrant Dashboard: http://localhost:6333/dashboard
