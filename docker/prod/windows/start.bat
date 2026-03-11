@echo off
cd /d "%~dp0"
:: Running from: docker/identifier/windows/

echo [Reeve Identifier] Starting services (GPU)...
docker compose up -d

if errorlevel 1 (
    echo [ERROR] Failed to start services. Check the logs:
    echo        docker compose logs
    pause
    exit /b 1
)

echo.
echo Services started:
echo   Identifier API : http://localhost:8001
echo   Identifier Docs: http://localhost:8001/docs
echo   Qdrant Dashboard: http://localhost:6333/dashboard
