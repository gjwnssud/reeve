@echo off
setlocal EnableDelayedExpansion
chcp 65001 > nul
cd /d "%~dp0"
:: 실행 위치: docker/identifier/windows/

echo [Reeve Identifier] Windows 초기 설정
echo ======================================

:: ── 1. Docker Desktop 확인 ──────────────────
echo [1/5] Docker Desktop 확인 중...
docker info > nul 2>&1
if errorlevel 1 (
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo        Docker Desktop을 시작한 후 다시 실행하세요.
    pause
    exit /b 1
)
echo       OK

:: ── 2. NVIDIA GPU 확인 ──────────────────────
echo [2/5] NVIDIA GPU 확인 중...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [오류] NVIDIA GPU를 감지하지 못했습니다.
    echo        Docker Desktop + WSL2 + NVIDIA Container Toolkit이 설치되어 있는지 확인하세요.
    pause
    exit /b 1
)
for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name,memory.total --format=csv^,noheader 2^>nul') do (
    echo       GPU: %%g
)

:: ── 3. .env 파일 생성 ───────────────────────
echo [3/5] 환경변수 파일 확인 중...
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo       .env 파일이 생성되었습니다. 필요시 내용을 수정하세요.
) else (
    echo       .env 파일 존재 확인
)

:: ── 4. Identifier 이미지 로드 ────────────────
echo [4/5] Identifier 이미지 확인 중...
docker image inspect reeve-identifier:latest > nul 2>&1
if errorlevel 1 (
    set IMAGE_TAR=
    for %%f in (reeve-identifier-*.tar.gz) do set IMAGE_TAR=%%f
    if defined IMAGE_TAR (
        echo       이미지 로드 중: !IMAGE_TAR!
        docker load < "!IMAGE_TAR!"
    ) else (
        echo [오류] reeve-identifier:latest 이미지를 찾을 수 없습니다.
        echo        reeve-identifier-*.tar.gz 파일을 이 디렉토리에 넣거나
        echo        docker pull 명령으로 이미지를 받으세요.
        pause
        exit /b 1
    )
) else (
    echo       reeve-identifier:latest 확인
)

:: ── 5. 서비스 시작 ───────────────────────────
echo [5/5] 서비스 시작 중...
docker compose up -d
if errorlevel 1 (
    echo [오류] 서비스 시작에 실패했습니다.
    pause
    exit /b 1
)

:: ── Qdrant 준비 대기 ─────────────────────────
echo.
echo Qdrant 준비 대기 중...
:QDRANT_WAIT
timeout /t 2 /nobreak > nul
curl -sf http://localhost:6333/healthz > nul 2>&1
if errorlevel 1 goto QDRANT_WAIT
echo Qdrant 준비 완료

:: ── Qdrant 스냅샷 복원 ───────────────────────
set SNAPSHOT_FILE=
for %%f in (snapshots\training_images*.snapshot) do set SNAPSHOT_FILE=%%f

if defined SNAPSHOT_FILE (
    echo.
    echo Qdrant 스냅샷 복원 중: %SNAPSHOT_FILE%
    curl -sf http://localhost:6333/collections/training_images > nul 2>&1
    if errorlevel 1 (
        curl -sf -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" ^
            -H "Content-Type:multipart/form-data" ^
            -F "snapshot=@%SNAPSHOT_FILE%"
        echo 스냅샷 복원 완료
    ) else (
        echo training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다.
    )
) else (
    echo.
    echo [정보] snapshots\ 폴더에 스냅샷 파일이 없습니다.
    echo        Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.bat을 다시 실행하세요.
)

:: ── Ollama 모델 로드 ─────────────────────────
echo.
echo Ollama 준비 대기 중...
:OLLAMA_WAIT
timeout /t 2 /nobreak > nul
docker exec reeve-ollama ollama list > nul 2>&1
if errorlevel 1 goto OLLAMA_WAIT

:: .env에서 VLM_MODEL_NAME 읽기
set MODEL_NAME=vehicle-vlm-v1
for /f "tokens=2 delims==" %%a in ('findstr /i "VLM_MODEL_NAME" .env 2^>nul') do set MODEL_NAME=%%a

docker exec reeve-ollama ollama list | findstr /i "%MODEL_NAME%" > nul 2>&1
if not errorlevel 1 (
    echo Ollama 모델 '%MODEL_NAME%' 이미 존재합니다.
) else (
    set GGUF_FILE=
    for %%f in (models\*.gguf) do set GGUF_FILE=%%f

    if defined GGUF_FILE (
        if exist "models\Modelfile" (
            echo Ollama 모델 등록 중: %MODEL_NAME%
            for %%f in (!GGUF_FILE!) do docker cp "%%f" reeve-ollama:/root/%%~nxf
            docker cp "models\Modelfile" reeve-ollama:/root/Modelfile
            docker exec reeve-ollama ollama create %MODEL_NAME% -f /root/Modelfile
            echo 모델 등록 완료: %MODEL_NAME%
        ) else (
            echo [정보] models\Modelfile 파일이 없습니다.
        )
    ) else (
        echo [정보] models\ 폴더에 .gguf 파일이 없습니다.
        echo        파인튜닝된 모델 파일을 models\ 폴더에 넣고 setup.bat을 다시 실행하세요.
        echo        (models\vehicle-vlm-v1.gguf + models\Modelfile^)
    )
)

echo.
echo ======================================
echo 설정 완료.
echo   Identifier API : http://localhost:8001
echo   Identifier Docs: http://localhost:8001/docs
echo   Qdrant Dashboard: http://localhost:6333/dashboard
echo ======================================
pause
