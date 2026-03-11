@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0..\.."
:: Running from: docker/

echo [Reeve Studio] Windows Setup
echo ======================================

:: -- 1. Check Docker Desktop --
echo [1/4] Checking Docker Desktop...
docker info > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running.
    echo        Start Docker Desktop and try again.
    pause
    exit /b 1
)
echo       OK

:: -- 2. Check NVIDIA GPU --
echo [2/4] Checking NVIDIA GPU...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [WARN] No NVIDIA GPU detected.
    echo        ollama and llamafactory will run on CPU.
    set /p CONTINUE="Continue anyway? (y/N): "
    if /i "!CONTINUE!" neq "y" exit /b 1
) else (
    for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name --format=csv^,noheader 2^>nul') do (
        echo       GPU detected: %%g
    )
)

:: -- 3. Create .env file --
echo [3/4] Checking environment file...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" > nul
        echo       .env file created.
        echo.
        echo  * Required settings to update:
        echo    - OPENAI_API_KEY
        echo    - MYSQL_ROOT_PASSWORD
        echo    - MYSQL_PASSWORD
        echo.
        echo    Edit docker\.env and then run start.bat.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo [ERROR] .env.example not found.
        pause
        exit /b 1
    )
) else (
    echo       .env file found
)

:: -- 4. Pull / Build images --
echo [4/4] Preparing Docker images...
docker compose -f docker-compose.yml -f dev\windows\docker-compose.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f dev\windows\docker-compose.yml build

echo.
echo ======================================
echo Setup complete. Run start.bat to start the services.
echo ======================================
pause
