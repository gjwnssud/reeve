@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

:: ============================================================
:: Reeve Deployment Package Builder (Windows)
::
:: Usage:
::   package.bat [target]
::
:: Targets:
::   dev-linux     개발사 납품 - Linux dev environment (GPU)
::   dev-windows   개발사 납품 - Windows dev environment (GPU)
::   prod-linux    고객사 납품 - Linux production environment
::   prod-windows  고객사 납품 - Windows production environment
::   all           Build all packages
:: ============================================================

set SCRIPT_DIR=%~dp0
set ROOT=%SCRIPT_DIR%..
set DOCKER_DIR=%ROOT%\docker

set TARGET=%~1

if /i "%TARGET%"=="dev-linux"    goto :RUN_DEV_LINUX
if /i "%TARGET%"=="dev-windows"  goto :RUN_DEV_WINDOWS
if /i "%TARGET%"=="prod-linux"   goto :RUN_PROD_LINUX
if /i "%TARGET%"=="prod-windows" goto :RUN_PROD_WINDOWS
if /i "%TARGET%"=="all"          goto :RUN_ALL

echo Usage: package.bat [target]
echo.
echo   dev-linux     Dev package for Linux environment (GPU)
echo   dev-windows   Dev package for Windows environment (GPU)
echo   prod-linux    Prod package for Linux environment
echo   prod-windows  Prod package for Windows environment
echo   all           Build all packages
exit /b 0

:RUN_DEV_LINUX
call :PACKAGE_DEV linux
goto :DONE

:RUN_DEV_WINDOWS
call :PACKAGE_DEV windows
goto :DONE

:RUN_PROD_LINUX
call :PACKAGE_PROD linux
goto :DONE

:RUN_PROD_WINDOWS
call :PACKAGE_PROD windows
goto :DONE

:RUN_ALL
call :PACKAGE_DEV linux
call :PACKAGE_DEV windows
call :PACKAGE_PROD linux
call :PACKAGE_PROD windows
goto :DONE

:DONE
echo.
echo [DONE] Check each package under deploy\
exit /b 0


:: ============================================================
:PACKAGE_DEV
set OS=%~1
set DEST=%SCRIPT_DIR%dev\%OS%
echo.
echo ===== Building Dev %OS% package =====

if exist "%DEST%" rd /s /q "%DEST%"
mkdir "%DEST%"

:: Copy and patch docker-compose files (fix paths for package root context)
:: context: .. -> context: .  |  dockerfile: docker/ -> dockerfile:  |  - ../ -> - ./
set "_PJS=%TEMP%\reeve_patch_%RANDOM%.js"
echo function r(p){var s=new ActiveXObject("ADODB.Stream");s.Open();s.Type=2;s.Charset="utf-8";s.LoadFromFile(p);var t=s.ReadText();s.Close();return t;} > "%_PJS%"
echo function w(p,t){var s=new ActiveXObject("ADODB.Stream");s.Open();s.Type=2;s.Charset="utf-8";s.WriteText(t);s.SaveToFile(p,2);s.Close();} >> "%_PJS%"
echo function patch(s,d){var t=r(s);t=t.replace(/context: \.\./g,"context: .");t=t.replace(/dockerfile: docker\//g,"dockerfile: ");t=t.replace(/- \.\.\//g,"- ./");w(d,t);} >> "%_PJS%"
echo patch(WScript.Arguments(0),WScript.Arguments(1)); >> "%_PJS%"
cscript //nologo "%_PJS%" "%DOCKER_DIR%\docker-compose.yml" "%DEST%\docker-compose.yml"
cscript //nologo "%_PJS%" "%DOCKER_DIR%\docker-compose.dev.yml" "%DEST%\docker-compose.dev.yml"
del "%_PJS%" 2>nul

copy "%DOCKER_DIR%\Dockerfile"            "%DEST%\" > nul
copy "%DOCKER_DIR%\Dockerfile.identifier" "%DEST%\" > nul
copy "%DOCKER_DIR%\.env.example"          "%DEST%\" > nul

:: Copy source code
robocopy "%ROOT%\studio"     "%DEST%\studio"     /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [WARN] robocopy error: studio
robocopy "%ROOT%\identifier" "%DEST%\identifier" /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [WARN] robocopy error: identifier
robocopy "%ROOT%\sql"        "%DEST%\sql"        /e > nul
if errorlevel 2 echo [WARN] robocopy error: sql
copy "%ROOT%\requirements.txt"            "%DEST%\" > nul
copy "%ROOT%\requirements-identifier.txt" "%DEST%\" > nul

:: Convert .sh files to LF line endings (CRLF causes "no such file or directory" in Linux containers)
set "_LJS=%TEMP%\reeve_lf_%RANDOM%.js"
echo function r(p){var s=new ActiveXObject("ADODB.Stream");s.Open();s.Type=2;s.Charset="utf-8";s.LoadFromFile(p);var t=s.ReadText();s.Close();return t;} > "%_LJS%"
echo function w(p,t){var s=new ActiveXObject("ADODB.Stream");s.Open();s.Type=2;s.Charset="utf-8";s.WriteText(t);s.Position=0;s.Type=1;s.Read(3);var b=new ActiveXObject("ADODB.Stream");b.Open();b.Type=1;s.CopyTo(b);s.Close();b.SaveToFile(p,2);b.Close();} >> "%_LJS%"
echo function walk(fso,folder){var fi=new Enumerator(folder.Files);while(fi.atEnd()==false){var f=fi.item();if(/\.sh$/i.test(f.Name)){w(f.Path,r(f.Path).replace(/\r\n/g,"\n"));}fi.moveNext();}var si=new Enumerator(folder.SubFolders);while(si.atEnd()==false){walk(fso,si.item());si.moveNext();}} >> "%_LJS%"
echo var fso=new ActiveXObject("Scripting.FileSystemObject");walk(fso,fso.GetFolder(WScript.Arguments(0))); >> "%_LJS%"
cscript //nologo "%_LJS%" "%DEST%"
del "%_LJS%" 2>nul

:: Create empty dirs for Docker volume mounts
for %%d in (
    data\mysql data\qdrant data\redis data\ollama
    data\hf-cache data\shared data\finetune
    logs\studio logs\identifier output
) do mkdir "%DEST%\%%d" 2>nul

:: Write OS-specific scripts
if "%OS%"=="linux" (
    call :WRITE_DEV_LINUX_SCRIPTS "%DEST%"
) else (
    call :WRITE_DEV_WINDOWS_SCRIPTS "%DEST%"
)

echo [INFO] Dev %OS% package done: %DEST%
exit /b 0


:: ============================================================
:PACKAGE_PROD
set OS=%~1
set DEST=%SCRIPT_DIR%prod\%OS%
echo.
echo ===== Building Prod %OS% package =====

if exist "%DEST%" rd /s /q "%DEST%"
for %%d in (snapshots models data\qdrant data\redis data\ollama data\shared logs) do (
    mkdir "%DEST%\%%d" 2>nul
)

:: Dockerfile.identifier -> Dockerfile (standalone build)
copy "%DOCKER_DIR%\Dockerfile.identifier" "%DEST%\Dockerfile" > nul

:: Write prod docker-compose.yml and .env.example
call :WRITE_PROD_COMPOSE "%DEST%"
call :WRITE_PROD_ENV_EXAMPLE "%DEST%"

:: Write OS-specific scripts
if "%OS%"=="linux" (
    call :WRITE_PROD_LINUX_SCRIPTS "%DEST%"
) else (
    call :WRITE_PROD_WINDOWS_SCRIPTS "%DEST%"
)

:: Build and save Identifier Docker image (temp tag to preserve existing reeve-identifier:latest)
for /f "tokens=2 delims==" %%t in ('wmic os get LocalDateTime /value 2^>nul') do set DT=%%t
set TMP_TAG=reeve-identifier:pkg-%DT:~0,14%
echo [INFO] Building Identifier Docker image... (tag: %TMP_TAG%)
cd /d "%ROOT%"
docker build -t "%TMP_TAG%" -f docker\Dockerfile.identifier .
if errorlevel 1 (
    echo [ERROR] Docker image build failed
    exit /b 1
)

echo [INFO] Saving image (this may take a while)...
docker save "%TMP_TAG%" | wsl gzip > "%DEST%\reeve-identifier-latest.tar.gz"
if errorlevel 1 (
    echo [ERROR] Docker image save failed
    exit /b 1
)
echo [INFO] Image saved: reeve-identifier-latest.tar.gz

echo [INFO] Removing temp image: %TMP_TAG%
docker rmi "%TMP_TAG%" > nul 2>&1

:: Export Qdrant snapshot
curl -s http://localhost:6333/healthz > nul 2>&1
if not errorlevel 1 (
    echo [INFO] Creating Qdrant snapshot...
    set SNAP_JSON=%TEMP%\reeve_snap.json
    curl -s -X POST "http://localhost:6333/collections/training_images/snapshots" -o "!SNAP_JSON!" 2>nul

    (
        echo import json, sys
        echo with open(sys.argv[1]) as f: d = json.load(f)
        echo r = d.get('result', {})
        echo print(r.get('name', '') if isinstance(r, dict) else '')
    ) > "%TEMP%\reeve_parse.py"

    set SNAP_NAME=
    for /f "delims=" %%s in ('python "%TEMP%\reeve_parse.py" "!SNAP_JSON!" 2^>nul') do set SNAP_NAME=%%s
    del "%TEMP%\reeve_parse.py" "!SNAP_JSON!" 2>nul

    if defined SNAP_NAME (
        curl -s -o "%DEST%\snapshots\training_images.snapshot" ^
            "http://localhost:6333/collections/training_images/snapshots/!SNAP_NAME!"
        echo [INFO] Snapshot saved: snapshots\training_images.snapshot
    ) else (
        echo [WARN] Qdrant snapshot creation failed.
        echo        Run data sync in Studio first, or place snapshot in snapshots\ manually.
    )
) else (
    echo [WARN] Qdrant is not running - skipping snapshot.
    echo        Start the service first, or place snapshot in snapshots\ manually.
)

:: Copy Ollama models
set OLLAMA_HAS_FILES=0
if exist "%ROOT%\data\ollama\" (
    for /r "%ROOT%\data\ollama" %%f in (*) do set OLLAMA_HAS_FILES=1
)
if "!OLLAMA_HAS_FILES!"=="1" (
    echo [INFO] Copying Ollama models...
    xcopy /e /i /q "%ROOT%\data\ollama\*" "%DEST%\data\ollama\" > nul
    echo [INFO] Ollama models copied
) else (
    echo [WARN] data\ollama is empty.
    echo        Run finetuning first, or place GGUF + Modelfile in models\ manually.
)

echo [INFO] Prod %OS% package done: %DEST%
exit /b 0


:: ============================================================
:WRITE_DEV_LINUX_SCRIPTS
set DEST=%~1

:: Write setup.sh (LF line endings via PowerShell)
powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'set -e'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Studio] Linux 초기 설정 (GPU)\"'," ^
  "'echo \"======================================\"'," ^
  "''," ^
  "'echo \"[1/4] Docker 확인 중...\"'," ^
  "'if ! docker info > /dev/null 2>&1; then'," ^
  "'    echo \"[오류] Docker가 실행되지 않았습니다.\"'," ^
  "'    exit 1'," ^
  "'fi'," ^
  "'echo \"      OK\"'," ^
  "''," ^
  "'echo \"[2/4] NVIDIA GPU 확인 중...\"'," ^
  "'if ! nvidia-smi > /dev/null 2>&1; then'," ^
  "'    echo \"[경고] NVIDIA GPU를 감지하지 못했습니다.\"'," ^
  "'    echo \"       nvidia-container-toolkit이 설치되어 있는지 확인하세요.\"'," ^
  "'    read -p \"계속 진행하시겠습니까? (y/N): \" CONTINUE'," ^
  "'    [[ \"\$CONTINUE\" =~ ^[Yy]\$ ]] ^|^| exit 1'," ^
  "'else'," ^
  "'    nvidia-smi --query-gpu=name --format=csv,noheader ^| while read name; do'," ^
  "'        echo \"      GPU: \$name\"'," ^
  "'    done'," ^
  "'fi'," ^
  "''," ^
  "'echo \"[3/4] 환경변수 파일 확인 중...\"'," ^
  "'if [ ! -f \".env\" ]; then'," ^
  "'    cp \".env.example\" \".env\"'," ^
  "'    echo \"      .env 파일이 생성되었습니다.\"'," ^
  "'    echo \"\"'," ^
  "'    echo \" ★ 필수 수정 항목:\"'," ^
  "'    echo \"   - OPENAI_API_KEY\"'," ^
  "'    echo \"   - MYSQL_ROOT_PASSWORD\"'," ^
  "'    echo \"   - MYSQL_PASSWORD\"'," ^
  "'    echo \"\"'," ^
  "'    echo \"   .env 파일을 편집한 후 start.sh를 실행하세요.\"'," ^
  "'    exit 0'," ^
  "'else'," ^
  "'    echo \"      .env 파일 존재 확인\"'," ^
  "'fi'," ^
  "''," ^
  "'echo \"[4/4] Docker 이미지 준비 중...\"'," ^
  "'docker compose -f docker-compose.yml -f docker-compose.dev.yml pull --ignore-buildable'," ^
  "'docker compose -f docker-compose.yml -f docker-compose.dev.yml build'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"======================================\"'," ^
  "'echo \"초기 설정 완료. ./start.sh 로 서비스를 시작하세요.\"'," ^
  "'echo \"======================================\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\setup.sh', ($c -join [char]10) + [char]10)"

:: Write start.sh
powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'set -e'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Studio] Linux 서비스 시작 (GPU)\"'," ^
  "'docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"서비스가 시작되었습니다:\"'," ^
  "'echo \"  Studio        : http://localhost:8000\"'," ^
  "'echo \"  Identifier    : http://localhost:8001\"'," ^
  "'echo \"  LLaMA-Factory : http://localhost:7860\"'," ^
  "'echo \"  Qdrant        : http://localhost:6333/dashboard\"'," ^
  "'echo \"  Ollama        : http://localhost:11434  (NVIDIA GPU)\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\start.sh', ($c -join [char]10) + [char]10)"

:: Write stop.sh
powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Studio] 서비스 중지 중...\"'," ^
  "'docker compose -f docker-compose.yml -f docker-compose.dev.yml down'," ^
  "''," ^
  "'echo \"완료.\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\stop.sh', ($c -join [char]10) + [char]10)"

exit /b 0


:: ============================================================
:WRITE_DEV_WINDOWS_SCRIPTS
set DEST=%~1

(
echo @echo off
echo chcp 65001 ^> nul
echo setlocal EnableDelayedExpansion
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Studio] Windows 초기 설정 ^(GPU^)
echo echo ======================================
echo.
echo echo [1/4] Docker Desktop 확인 중...
echo docker info ^> nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [오류] Docker Desktop이 실행되지 않았습니다.
echo     echo        Docker Desktop을 시작한 후 다시 실행하세요.
echo     pause
echo     exit /b 1
echo ^)
echo echo       OK
echo.
echo echo [2/4] NVIDIA GPU 확인 중...
echo nvidia-smi ^> nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [경고] NVIDIA GPU를 감지하지 못했습니다.
echo     echo        ollama, llamafactory가 CPU로 실행됩니다.
echo     set /p CONTINUE="계속 진행하시겠습니까? ^(y/N^): "
echo     if /i "%%CONTINUE%%" neq "y" exit /b 1
echo ^) else ^(
echo     for /f "tokens=*" %%%%g in ^('nvidia-smi -L'^) do ^(
echo         echo       GPU 감지: %%%%g
echo     ^)
echo ^)
echo.
echo echo [3/4] 환경변수 파일 확인 중...
echo if not exist ".env" ^(
echo     if exist ".env.example" ^(
echo         copy ".env.example" ".env" ^> nul
echo         echo       .env 파일이 생성되었습니다.
echo         echo.
echo         echo  * 필수 수정 항목:
echo         echo    - OPENAI_API_KEY
echo         echo    - MYSQL_ROOT_PASSWORD
echo         echo    - MYSQL_PASSWORD
echo         echo.
echo         echo    .env 파일을 편집한 후 start.bat을 실행하세요.
echo         start notepad ".env"
echo         pause
echo         exit /b 0
echo     ^) else ^(
echo         echo [오류] .env.example 파일을 찾을 수 없습니다.
echo         pause
echo         exit /b 1
echo     ^)
echo ^) else ^(
echo     echo       .env 파일 존재 확인
echo ^)
echo.
echo echo [4/4] Docker 이미지 준비 중...
echo docker compose -f docker-compose.yml -f docker-compose.dev.yml pull --ignore-buildable
echo docker compose -f docker-compose.yml -f docker-compose.dev.yml build
echo.
echo echo.
echo echo ======================================
echo echo 초기 설정 완료. start.bat으로 서비스를 시작하세요.
echo echo ======================================
echo pause
) > "%DEST%\setup.bat"

(
echo @echo off
echo chcp 65001 ^> nul
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Studio] Windows 서비스 시작 ^(GPU^)...
echo docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d
echo.
echo if errorlevel 1 ^(
echo     echo [오류] 서비스 시작 실패. 로그를 확인하세요:
echo     echo        docker compose -f docker-compose.yml -f docker-compose.dev.yml logs
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo.
echo echo 서비스가 시작되었습니다:
echo echo   Studio        : http://localhost:8000
echo echo   Identifier    : http://localhost:8001
echo echo   LLaMA-Factory : http://localhost:7860
echo echo   Qdrant        : http://localhost:6333/dashboard
) > "%DEST%\start.bat"

(
echo @echo off
echo chcp 65001 ^> nul
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Studio] 서비스 중지 중...
echo docker compose -f docker-compose.yml -f docker-compose.dev.yml down
echo.
echo echo 완료.
) > "%DEST%\stop.bat"

exit /b 0


:: ============================================================
:WRITE_PROD_COMPOSE
set DEST=%~1

(
echo name: reeve-identifier
echo.
echo # ──────────────────────────────────────────
echo # Identifier 납품 패키지 ^(NVIDIA GPU^)
echo # 포함 서비스: qdrant + redis + identifier + celery-worker + ollama
echo # 이미지 빌드: docker build -t reeve-identifier:latest -f Dockerfile .
echo # ──────────────────────────────────────────
echo.
echo services:
echo   qdrant:
echo     image: qdrant/qdrant:latest
echo     container_name: reeve-qdrant
echo     ports:
echo       - "6333:6333"
echo       - "6334:6334"
echo     volumes:
echo       - ./data/qdrant:/qdrant/storage
echo     environment:
echo       - QDRANT__SERVICE__GRPC_PORT=6334
echo       - QDRANT__STORAGE__ON_DISK_PAYLOAD=true
echo     networks:
echo       - reeve-network
echo     restart: unless-stopped
echo     deploy:
echo       resources:
echo         limits:
echo           cpus: '1.0'
echo           memory: 2G
echo         reservations:
echo           cpus: '0.25'
echo           memory: 256M
echo.
echo   redis:
echo     image: redis:7.4-alpine
echo     container_name: reeve-redis
echo     ports:
echo       - "6379:6379"
echo     volumes:
echo       - ./data/redis:/data
echo     networks:
echo       - reeve-network
echo     restart: unless-stopped
echo     command: redis-server --appendonly yes
echo     deploy:
echo       resources:
echo         limits:
echo           cpus: '0.5'
echo           memory: 512M
echo.
echo   identifier:
echo     image: reeve-identifier:latest
echo     container_name: reeve-identifier
echo     env_file:
echo       - .env
echo     ports:
echo       - "8001:8001"
echo     volumes:
echo       - ./logs:/app/logs
echo       - ./data/shared:/app/shared
echo     environment:
echo       - QDRANT_HOST=qdrant
echo       - REDIS_HOST=redis
echo       - OLLAMA_BASE_URL=http://ollama:11434
echo       - EMBEDDING_DEVICE=cuda
echo     depends_on:
echo       qdrant:
echo         condition: service_started
echo       redis:
echo         condition: service_started
echo     networks:
echo       - reeve-network
echo     restart: unless-stopped
echo     deploy:
echo       resources:
echo         limits:
echo           cpus: '2.0'
echo           memory: 2G
echo         reservations:
echo           cpus: '0.5'
echo           memory: 1G
echo.
echo   celery-worker:
echo     image: reeve-identifier:latest
echo     container_name: reeve-celery-worker
echo     env_file:
echo       - .env
echo     command: /app/identifier/start_worker.sh
echo     volumes:
echo       - ./logs:/app/logs
echo       - ./data/shared:/app/shared
echo     environment:
echo       - QDRANT_HOST=qdrant
echo       - REDIS_HOST=redis
echo       - OLLAMA_BASE_URL=http://ollama:11434
echo       - EMBEDDING_DEVICE=cuda
echo     depends_on:
echo       redis:
echo         condition: service_started
echo       qdrant:
echo         condition: service_started
echo     networks:
echo       - reeve-network
echo     restart: unless-stopped
echo     deploy:
echo       resources:
echo         limits:
echo           cpus: '4.0'
echo           memory: 4G
echo         reservations:
echo           cpus: '2.0'
echo           memory: 2G
echo.
echo   ollama:
echo     image: ollama/ollama:latest
echo     container_name: reeve-ollama
echo     ports:
echo       - "11434:11434"
echo     volumes:
echo       - ./data/ollama:/root/.ollama
echo     networks:
echo       - reeve-network
echo     restart: unless-stopped
echo     deploy:
echo       resources:
echo         reservations:
echo           devices:
echo             - driver: nvidia
echo               count: 1
echo               capabilities: [gpu]
echo         limits:
echo           memory: 16G
echo.
echo networks:
echo   reeve-network:
echo     driver: bridge
) > "%DEST%\docker-compose.yml"

exit /b 0


:: ============================================================
:WRITE_PROD_ENV_EXAMPLE
set DEST=%~1

(
echo # ──────────────────────────────────────────
echo # Identifier 서비스 환경변수
echo # 이 파일을 .env로 복사 후 수정하세요
echo # ──────────────────────────────────────────
echo.
echo # Qdrant
echo QDRANT_HOST=qdrant
echo QDRANT_PORT=6333
echo.
echo # Embedding
echo EMBEDDING_DEVICE=cuda
echo.
echo # 판별 모드: clip_only ^| visual_rag ^| vlm_only
echo IDENTIFIER_MODE=visual_rag
echo.
echo # VLM ^(Ollama^)
echo OLLAMA_BASE_URL=http://ollama:11434
echo VLM_MODEL_NAME=vehicle-vlm-v1
echo VLM_TIMEOUT=30
echo VLM_MAX_CANDIDATES=5
echo VLM_FALLBACK_TO_CLIP=true
echo VLM_BATCH_CONCURRENCY=2
echo.
echo # 판별 파라미터
echo IDENTIFIER_PORT=8001
echo IDENTIFIER_TOP_K=10
echo IDENTIFIER_CONFIDENCE_THRESHOLD=0.80
echo IDENTIFIER_MIN_SIMILARITY=0.70
echo IDENTIFIER_VOTE_THRESHOLD=3
echo IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD=0.3
echo IDENTIFIER_VEHICLE_DETECTION=true
echo IDENTIFIER_YOLO_CONFIDENCE=0.25
echo IDENTIFIER_CROP_PADDING=10
echo.
echo # 성능
echo IDENTIFIER_TORCH_THREADS=4
echo IDENTIFIER_BATCH_SIZE=32
echo IDENTIFIER_MAX_BATCH_FILES=100
echo IDENTIFIER_MAX_BATCH_UPLOAD_SIZE=104857600
echo IDENTIFIER_ENABLE_TORCH_COMPILE=true
echo.
echo # Redis / Celery
echo REDIS_HOST=redis
echo REDIS_PORT=6379
echo REDIS_DB=0
echo CELERY_TASK_TIME_LIMIT=600
echo CELERY_TASK_SOFT_TIME_LIMIT=540
echo CELERY_MAX_RETRIES=3
echo.
echo # 파일 업로드
echo MAX_UPLOAD_SIZE=5242880
echo ALLOWED_EXTENSIONS=jpg,jpeg,png,webp
echo.
echo # 로그
echo LOG_LEVEL=INFO
echo IDENTIFIER_LOG_FILE=./logs/identifier/service.log
) > "%DEST%\.env.example"

exit /b 0


:: ============================================================
:WRITE_PROD_LINUX_SCRIPTS
set DEST=%~1

powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'set -e'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Identifier] Linux 초기 설정\"'," ^
  "'echo \"======================================\"'," ^
  "''," ^
  "'echo \"[1/5] Docker 확인 중...\"'," ^
  "'if ! docker info > /dev/null 2>&1; then'," ^
  "'    echo \"[오류] Docker가 실행되지 않았습니다.\"'," ^
  "'    exit 1'," ^
  "'fi'," ^
  "'echo \"      OK\"'," ^
  "''," ^
  "'echo \"[2/5] NVIDIA GPU 확인 중...\"'," ^
  "'if ! nvidia-smi > /dev/null 2>&1; then'," ^
  "'    echo \"[오류] NVIDIA GPU를 감지하지 못했습니다.\"'," ^
  "'    echo \"       nvidia-container-toolkit이 설치되어 있는지 확인하세요.\"'," ^
  "'    exit 1'," ^
  "'fi'," ^
  "'nvidia-smi --query-gpu=name,memory.total --format=csv,noheader ^| while read line; do'," ^
  "'    echo \"      GPU: \$line\"'," ^
  "'done'," ^
  "''," ^
  "'echo \"[3/5] 환경변수 파일 확인 중...\"'," ^
  "'if [ ! -f \".env\" ]; then'," ^
  "'    cp \".env.example\" \".env\"'," ^
  "'    echo \"      .env 파일이 생성되었습니다. 필요시 내용을 수정하세요.\"'," ^
  "'else'," ^
  "'    echo \"      .env 파일 존재 확인\"'," ^
  "'fi'," ^
  "''," ^
  "'echo \"[4/5] Identifier 이미지 확인 중...\"'," ^
  "'if ! docker image inspect reeve-identifier:latest > /dev/null 2>&1; then'," ^
  "'    IMAGE_TAR=\$(ls reeve-identifier-*.tar.gz 2>/dev/null ^| head -1)'," ^
  "'    if [ -n \"\$IMAGE_TAR\" ]; then'," ^
  "'        echo \"      이미지 로드 중: \$IMAGE_TAR\"'," ^
  "'        LOAD_OUT=\$(docker load < \"\$IMAGE_TAR\")'," ^
  "'        echo \"\$LOAD_OUT\"'," ^
  "'        LOADED_TAG=\$(echo \"\$LOAD_OUT\" ^| grep \"Loaded image:\" ^| awk ''{print \$NF}'')'," ^
  "'        if [ -n \"\$LOADED_TAG\" ] && [ \"\$LOADED_TAG\" != \"reeve-identifier:latest\" ]; then'," ^
  "'            docker tag \"\$LOADED_TAG\" reeve-identifier:latest'," ^
  "'            echo \"      태그 설정: \$LOADED_TAG → reeve-identifier:latest\"'," ^
  "'        fi'," ^
  "'    else'," ^
  "'        echo \"[오류] reeve-identifier:latest 이미지를 찾을 수 없습니다.\"'," ^
  "'        echo \"       reeve-identifier-*.tar.gz 파일을 이 디렉토리에 넣거나\"'," ^
  "'        echo \"       docker build -t reeve-identifier:latest -f Dockerfile . 로 빌드하세요.\"'," ^
  "'        exit 1'," ^
  "'    fi'," ^
  "'else'," ^
  "'    echo \"      reeve-identifier:latest 확인\"'," ^
  "'fi'," ^
  "''," ^
  "'echo \"[5/5] 서비스 시작 중...\"'," ^
  "'docker compose up -d'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"Qdrant 준비 대기 중...\"'," ^
  "'for i in \$(seq 1 30); do'," ^
  "'    if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then'," ^
  "'        echo \"Qdrant 준비 완료\"'," ^
  "'        break'," ^
  "'    fi'," ^
  "'    sleep 2'," ^
  "'done'," ^
  "''," ^
  "'set +e'," ^
  "'SNAPSHOT_FILE=\$(ls snapshots/training_images*.snapshot 2>/dev/null ^| head -1)'," ^
  "'if [ -n \"\$SNAPSHOT_FILE\" ]; then'," ^
  "'    echo \"\"'," ^
  "'    echo \"Qdrant 스냅샷 복원 중: \$SNAPSHOT_FILE\"'," ^
  "'    if ! curl -sf http://localhost:6333/collections/training_images > /dev/null 2>&1; then'," ^
  "'        curl -s -X POST \"http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot\" \'," ^
  "'            -H \"Content-Type:multipart/form-data\" \'," ^
  "'            -F \"snapshot=@\$SNAPSHOT_FILE\"'," ^
  "'        [ \$? -eq 0 ] && echo \"스냅샷 복원 완료\" ^|^| echo \"[경고] 스냅샷 복원 실패.\"'," ^
  "'    else'," ^
  "'        echo \"training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다.\"'," ^
  "'    fi'," ^
  "'else'," ^
  "'    echo \"\"'," ^
  "'    echo \"[정보] snapshots/ 폴더에 스냅샷 파일이 없습니다.\"'," ^
  "'    echo \"       Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.sh를 다시 실행하세요.\"'," ^
  "'fi'," ^
  "'set -e'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"Ollama 준비 대기 중...\"'," ^
  "'for i in \$(seq 1 30); do'," ^
  "'    if docker exec reeve-ollama ollama list > /dev/null 2>&1; then'," ^
  "'        break'," ^
  "'    fi'," ^
  "'    sleep 2'," ^
  "'done'," ^
  "''," ^
  "'MODEL_NAME=\$(grep VLM_MODEL_NAME .env ^| cut -d= -f2 ^| tr -d '' '')'," ^
  "'MODEL_NAME=\"\${MODEL_NAME:-vehicle-vlm-v1}\"'," ^
  "''," ^
  "'if docker exec reeve-ollama ollama list ^| grep -q \"\$MODEL_NAME\"; then'," ^
  "'    echo \"Ollama 모델 '\''\$MODEL_NAME'\'' 이미 존재합니다.\"'," ^
  "'else'," ^
  "'    GGUF_FILE=\$(ls models/*.gguf 2>/dev/null ^| head -1)'," ^
  "'    MODELFILE=\"models/Modelfile\"'," ^
  "'    if [ -n \"\$GGUF_FILE\" ] && [ -f \"\$MODELFILE\" ]; then'," ^
  "'        echo \"Ollama 모델 등록 중: \$MODEL_NAME\"'," ^
  "'        docker cp \"\$GGUF_FILE\" reeve-ollama:/root/\$(basename \"\$GGUF_FILE\")'," ^
  "'        docker cp \"\$MODELFILE\" reeve-ollama:/root/Modelfile'," ^
  "'        docker exec reeve-ollama ollama create \"\$MODEL_NAME\" -f /root/Modelfile'," ^
  "'        echo \"모델 등록 완료: \$MODEL_NAME\"'," ^
  "'    else'," ^
  "'        echo \"[정보] models/ 폴더에 .gguf 파일 또는 Modelfile이 없습니다.\"'," ^
  "'        echo \"       (models/vehicle-vlm-v1.gguf + models/Modelfile)\"'," ^
  "'    fi'," ^
  "'fi'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"======================================\"'," ^
  "'echo \"설정 완료.\"'," ^
  "'echo \"  Identifier API  : http://localhost:8001\"'," ^
  "'echo \"  Identifier Docs : http://localhost:8001/docs\"'," ^
  "'echo \"  Qdrant Dashboard: http://localhost:6333/dashboard\"'," ^
  "'echo \"======================================\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\setup.sh', ($c -join [char]10) + [char]10)"

powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'set -e'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Identifier] 서비스 시작 (GPU)\"'," ^
  "'docker compose up -d'," ^
  "''," ^
  "'echo \"\"'," ^
  "'echo \"서비스가 시작되었습니다:\"'," ^
  "'echo \"  Identifier API  : http://localhost:8001\"'," ^
  "'echo \"  Identifier Docs : http://localhost:8001/docs\"'," ^
  "'echo \"  Qdrant Dashboard: http://localhost:6333/dashboard\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\start.sh', ($c -join [char]10) + [char]10)"

powershell -NoProfile -Command ^
  "$c = @(" ^
  "'#!/bin/bash'," ^
  "'cd \"\$(dirname \"\$0\")\"'," ^
  "''," ^
  "'echo \"[Reeve Identifier] 서비스 중지 중...\"'," ^
  "'docker compose down'," ^
  "''," ^
  "'echo \"완료.\"'" ^
  "); [IO.File]::WriteAllText('%DEST%\stop.sh', ($c -join [char]10) + [char]10)"

exit /b 0


:: ============================================================
:WRITE_PROD_WINDOWS_SCRIPTS
set DEST=%~1

(
echo @echo off
echo chcp 65001 ^> nul
echo setlocal EnableDelayedExpansion
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Identifier] Windows 초기 설정
echo echo ======================================
echo.
echo echo [1/5] Docker Desktop 확인 중...
echo docker info ^> nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [오류] Docker Desktop이 실행되지 않았습니다.
echo     echo        Docker Desktop을 시작한 후 다시 실행하세요.
echo     pause
echo     exit /b 1
echo ^)
echo echo       OK
echo.
echo echo [2/5] NVIDIA GPU 확인 중...
echo nvidia-smi ^> nul 2^>^&1
echo if errorlevel 1 ^(
echo     echo [오류] NVIDIA GPU를 감지하지 못했습니다.
echo     echo        Docker Desktop + WSL2 + NVIDIA Container Toolkit이 필요합니다.
echo     pause
echo     exit /b 1
echo ^)
echo for /f "tokens=*" %%%%g in ^('nvidia-smi -L'^) do ^(
echo     echo       GPU: %%%%g
echo ^)
echo.
echo echo [3/5] 환경변수 파일 확인 중...
echo if not exist ".env" ^(
echo     copy ".env.example" ".env" ^> nul
echo     echo       .env 파일이 생성되었습니다. 필요시 내용을 수정하세요.
echo ^) else ^(
echo     echo       .env 파일 존재 확인
echo ^)
echo.
echo echo [4/5] Identifier 이미지 확인 중...
echo docker image inspect reeve-identifier:latest ^> nul 2^>^&1
echo if errorlevel 1 ^(
echo     set IMAGE_TAR=
echo     for %%%%f in ^(reeve-identifier-*.tar.gz^) do set IMAGE_TAR=%%%%f
echo     if defined IMAGE_TAR ^(
echo         echo       이미지 로드 중: ^^!IMAGE_TAR^^!
echo         docker load ^< ^^!IMAGE_TAR^^! ^> "%%TEMP%%\reeve_load.txt"
echo         if errorlevel 1 ^(
echo             echo [오류] Docker 이미지 로드 실패.
echo             del "%%TEMP%%\reeve_load.txt" 2^>nul
echo             pause
echo             exit /b 1
echo         ^)
echo         set LOADED_TAG=
echo         for /f "tokens=3" %%%%t in ^('findstr /i "Loaded image:" "%%TEMP%%\reeve_load.txt"'^) do set LOADED_TAG=%%%%t
echo         del "%%TEMP%%\reeve_load.txt" 2^>nul
echo         if defined LOADED_TAG ^(
echo             if ^^!LOADED_TAG^^! neq "reeve-identifier:latest" ^(
echo                 docker tag ^^!LOADED_TAG^^! reeve-identifier:latest
echo                 echo       태그 설정: ^^!LOADED_TAG^^! -^> reeve-identifier:latest
echo             ^)
echo         ^)
echo     ^) else ^(
echo         echo [오류] reeve-identifier:latest 이미지를 찾을 수 없습니다.
echo         echo        reeve-identifier-*.tar.gz 를 이 폴더에 넣거나
echo         echo        docker build -t reeve-identifier:latest -f Dockerfile . 로 빌드하세요.
echo         pause
echo         exit /b 1
echo     ^)
echo ^) else ^(
echo     echo       reeve-identifier:latest 확인
echo ^)
echo.
echo echo [5/5] 서비스 시작 중...
echo docker compose up -d
echo if errorlevel 1 ^(
echo     echo [오류] 서비스 시작 실패.
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo.
echo echo Qdrant 준비 대기 중...
echo :QDRANT_WAIT
echo timeout /t 2 /nobreak ^> nul
echo curl -s http://localhost:6333/healthz ^> nul 2^>^&1
echo if errorlevel 1 goto QDRANT_WAIT
echo echo Qdrant 준비 완료
echo.
echo set SNAPSHOT_FILE=
echo for %%%%f in ^(snapshots\training_images*.snapshot^) do set SNAPSHOT_FILE=%%%%f
echo.
echo if defined SNAPSHOT_FILE ^(
echo     echo.
echo     echo Qdrant 스냅샷 복원 중: %%SNAPSHOT_FILE%%
echo     curl -s http://localhost:6333/collections/training_images ^> nul 2^>^&1
echo     if errorlevel 1 ^(
echo         curl -s -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" ^^
echo             -H "Content-Type:multipart/form-data" ^^
echo             -F "snapshot=@%%SNAPSHOT_FILE%%"
echo         if errorlevel 1 ^(
echo             echo [경고] 스냅샷 복원 실패. setup.bat을 다시 실행하세요.
echo         ^) else ^(
echo             echo 스냅샷 복원 완료
echo         ^)
echo     ^) else ^(
echo         echo training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다.
echo     ^)
echo ^) else ^(
echo     echo.
echo     echo [정보] snapshots\ 폴더에 스냅샷 파일이 없습니다.
echo     echo        Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.bat을 다시 실행하세요.
echo ^)
echo.
echo echo.
echo echo Ollama 준비 대기 중...
echo :OLLAMA_WAIT
echo timeout /t 2 /nobreak ^> nul
echo docker exec reeve-ollama ollama list ^> nul 2^>^&1
echo if errorlevel 1 goto OLLAMA_WAIT
echo.
echo set MODEL_NAME=vehicle-vlm-v1
echo for /f "tokens=2 delims==" %%%%a in ^('findstr /i "^VLM_MODEL_NAME=" .env 2^>nul'^) do set MODEL_NAME=%%%%a
echo.
echo docker exec reeve-ollama ollama list ^| findstr /i "%%MODEL_NAME%%" ^> nul 2^>^&1
echo if not errorlevel 1 ^(
echo     echo Ollama 모델 '%%MODEL_NAME%%' 이미 존재합니다.
echo ^) else ^(
echo     set GGUF_FILE=
echo     for %%%%f in ^(models\*.gguf^) do set GGUF_FILE=%%%%f
echo     if defined GGUF_FILE ^(
echo         if exist "models\Modelfile" ^(
echo             echo Ollama 모델 등록 중: %%MODEL_NAME%%
echo             for %%%%f in ^(^^!GGUF_FILE^^!^) do docker cp "%%%%f" reeve-ollama:/root/%%%%~nxf
echo             docker cp "models\Modelfile" reeve-ollama:/root/Modelfile
echo             docker exec reeve-ollama ollama create %%MODEL_NAME%% -f /root/Modelfile
echo             if errorlevel 1 ^(
echo                 echo [경고] Ollama 모델 등록 실패.
echo             ^) else ^(
echo                 echo 모델 등록 완료: %%MODEL_NAME%%
echo             ^)
echo         ^) else ^(
echo             echo [정보] models\Modelfile이 없습니다.
echo         ^)
echo     ^) else ^(
echo         echo [정보] models\ 폴더에 .gguf 파일이 없습니다.
echo         echo        ^(models\vehicle-vlm-v1.gguf + models\Modelfile^)
echo     ^)
echo ^)
echo.
echo echo.
echo echo ======================================
echo echo 설정 완료.
echo echo   Identifier API  : http://localhost:8001
echo echo   Identifier Docs : http://localhost:8001/docs
echo echo   Qdrant Dashboard: http://localhost:6333/dashboard
echo echo ======================================
echo pause
) > "%DEST%\setup.bat"

(
echo @echo off
echo chcp 65001 ^> nul
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Identifier] 서비스 시작 ^(GPU^)...
echo docker compose up -d
echo.
echo if errorlevel 1 ^(
echo     echo [오류] 서비스 시작 실패. 로그를 확인하세요:
echo     echo        docker compose logs
echo     pause
echo     exit /b 1
echo ^)
echo.
echo echo.
echo echo 서비스가 시작되었습니다:
echo echo   Identifier API  : http://localhost:8001
echo echo   Identifier Docs : http://localhost:8001/docs
echo echo   Qdrant Dashboard: http://localhost:6333/dashboard
) > "%DEST%\start.bat"

(
echo @echo off
echo chcp 65001 ^> nul
echo cd /d "%%~dp0"
echo.
echo echo [Reeve Identifier] 서비스 중지 중...
echo docker compose down
echo.
echo echo 완료.
) > "%DEST%\stop.bat"

exit /b 0
