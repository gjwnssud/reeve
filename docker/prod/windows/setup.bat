@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
:: Running from: docker/identifier/windows/

echo [Reeve Identifier] Windows Setup
echo ======================================

:: -- 1. Check Docker Desktop --
echo [1/5] Checking Docker Desktop...
docker info > nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop is not running.
    echo        Start Docker Desktop and try again.
    pause
    exit /b 1
)
echo       OK

:: -- 2. Check NVIDIA GPU --
echo [2/5] Checking NVIDIA GPU...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [ERROR] No NVIDIA GPU detected.
    echo        Ensure Docker Desktop + WSL2 + NVIDIA Container Toolkit are installed.
    pause
    exit /b 1
)
for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name,memory.total --format=csv^,noheader 2^>nul') do (
    echo       GPU: %%g
)

:: -- 3. Create .env file --
echo [3/5] Checking environment file...
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo       .env file created. Edit if needed.
) else (
    echo       .env file found
)

:: -- 4. Load Identifier image --
echo [4/5] Checking Identifier image...
docker image inspect reeve-identifier:latest > nul 2>&1
if errorlevel 1 (
    set IMAGE_TAR=
    for %%f in (reeve-identifier-*.tar.gz) do set IMAGE_TAR=%%f
    if defined IMAGE_TAR (
        echo       Loading image: !IMAGE_TAR!
        docker load < "!IMAGE_TAR!"
        if errorlevel 1 (
            echo [ERROR] Failed to load Docker image.
            pause
            exit /b 1
        )
    ) else (
        echo [ERROR] reeve-identifier:latest image not found.
        echo        Place reeve-identifier-*.tar.gz in this directory, or
        echo        pull the image with docker pull.
        pause
        exit /b 1
    )
) else (
    echo       reeve-identifier:latest found
)

:: -- 5. Start services --
echo [5/5] Starting services...
docker compose up -d
if errorlevel 1 (
    echo [ERROR] Failed to start services.
    pause
    exit /b 1
)

:: -- Wait for Qdrant --
echo.
echo Waiting for Qdrant to be ready...
:QDRANT_WAIT
timeout /t 2 /nobreak > nul
curl -s http://localhost:6333/healthz > nul 2>&1
if errorlevel 1 goto QDRANT_WAIT
echo Qdrant ready

:: -- Restore Qdrant snapshot --
set SNAPSHOT_FILE=
for %%f in (snapshots\training_images*.snapshot) do set SNAPSHOT_FILE=%%f

if defined SNAPSHOT_FILE (
    echo.
    echo Restoring Qdrant snapshot: %SNAPSHOT_FILE%
    curl -s http://localhost:6333/collections/training_images > nul 2>&1
    if errorlevel 1 (
        curl -s -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" ^
            -H "Content-Type:multipart/form-data" ^
            -F "snapshot=@%SNAPSHOT_FILE%"
        if errorlevel 1 (
            echo [WARN] Snapshot restore failed. Run setup.bat again after checking Qdrant.
        ) else (
            echo Snapshot restored successfully
        )
    ) else (
        echo training_images collection already exists. Skipping restore.
    )
) else (
    echo.
    echo [INFO] No snapshot file found in snapshots\
    echo        Export a snapshot from Studio, place it here, and run setup.bat again.
)

:: -- Load Ollama model --
echo.
echo Waiting for Ollama to be ready...
:OLLAMA_WAIT
timeout /t 2 /nobreak > nul
docker exec reeve-ollama ollama list > nul 2>&1
if errorlevel 1 goto OLLAMA_WAIT

:: Read VLM_MODEL_NAME from .env (only non-commented lines)
set MODEL_NAME=vehicle-vlm-v1
for /f "tokens=2 delims==" %%a in ('findstr /i "^VLM_MODEL_NAME" .env 2^>nul') do set MODEL_NAME=%%a

docker exec reeve-ollama ollama list | findstr /i "%MODEL_NAME%" > nul 2>&1
if not errorlevel 1 (
    echo Ollama model '%MODEL_NAME%' already exists.
) else (
    set GGUF_FILE=
    for %%f in (models\*.gguf) do set GGUF_FILE=%%f

    if defined GGUF_FILE (
        if exist "models\Modelfile" (
            echo Registering Ollama model: %MODEL_NAME%
            for %%f in (!GGUF_FILE!) do docker cp "%%f" reeve-ollama:/root/%%~nxf
            docker cp "models\Modelfile" reeve-ollama:/root/Modelfile
            docker exec reeve-ollama ollama create %MODEL_NAME% -f /root/Modelfile
            if errorlevel 1 (
                echo [WARN] Failed to register Ollama model.
            ) else (
                echo Model registered: %MODEL_NAME%
            )
        ) else (
            echo [INFO] models\Modelfile not found.
        )
    ) else (
        echo [INFO] No .gguf file found in models\
        echo        Place the finetuned model files in models\ and run setup.bat again.
        echo        (models\vehicle-vlm-v1.gguf + models\Modelfile)
    )
)

echo.
echo ======================================
echo Setup complete.
echo   Identifier API : http://localhost:8001
echo   Identifier Docs: http://localhost:8001/docs
echo   Qdrant Dashboard: http://localhost:6333/dashboard
echo ======================================
pause
