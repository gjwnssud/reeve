@echo off
cd /d "%~dp0..\.."
:: Running from: docker/

echo [Reeve Studio] Starting services (GPU)...
docker compose -f docker-compose.yml -f dev\windows\docker-compose.yml up -d

if errorlevel 1 (
    echo [ERROR] Failed to start services. Check the logs:
    echo        docker compose -f docker-compose.yml -f dev\windows\docker-compose.yml logs
    pause
    exit /b 1
)

echo.
echo Services started:
echo   Studio        : http://localhost:8000
echo   Identifier    : http://localhost:8001
echo   LLaMA-Factory : http://localhost:7860
echo   Qdrant        : http://localhost:6333/dashboard
