@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Reeve Deployment Package Builder (Windows)
::
:: Usage:
::   package.bat [target]
::
:: Targets:
::   studio-mac          Studio package for Mac dev environment
::   studio-linux        Studio package for Linux dev environment
::   studio-windows      Studio package for Windows dev environment
::   identifier-linux    Identifier package for Linux production
::   identifier-windows  Identifier package for Windows production
::   all                 Build all packages
:: ============================================================

set SCRIPT_DIR=%~dp0
set ROOT=%SCRIPT_DIR%..
set DOCKER_DIR=%ROOT%\docker

set TARGET=%~1
if "%TARGET%"=="" (
    echo Usage: package.bat [target]
    echo.
    echo   studio-mac          Studio package for Mac dev environment
    echo   studio-linux        Studio package for Linux dev environment
    echo   studio-windows      Studio package for Windows dev environment
    echo   identifier-linux    Identifier package for Linux production
    echo   identifier-windows  Identifier package for Windows production
    echo   all                 Build all packages
    exit /b 0
)

if "%TARGET%"=="studio-mac"          call :PACKAGE_STUDIO mac
if "%TARGET%"=="studio-linux"        call :PACKAGE_STUDIO linux
if "%TARGET%"=="studio-windows"      call :PACKAGE_STUDIO windows
if "%TARGET%"=="identifier-linux"    call :PACKAGE_IDENTIFIER linux
if "%TARGET%"=="identifier-windows"  call :PACKAGE_IDENTIFIER windows
if "%TARGET%"=="all" (
    call :PACKAGE_STUDIO mac
    call :PACKAGE_STUDIO linux
    call :PACKAGE_STUDIO windows
    call :PACKAGE_IDENTIFIER linux
    call :PACKAGE_IDENTIFIER windows
)

echo.
echo [DONE] Check each package under deploy\
exit /b 0


:: --------------------------------------------
:PACKAGE_STUDIO
set OS=%~1
set DEST=%SCRIPT_DIR%studio-%OS%
echo.
echo ===== Building Studio %OS% package =====

if exist "%DEST%" rd /s /q "%DEST%"
mkdir "%DEST%\docker\dev\%OS%"

:: Copy docker files
copy "%DOCKER_DIR%\docker-compose.yml"      "%DEST%\docker\" > nul
copy "%DOCKER_DIR%\Dockerfile"              "%DEST%\docker\" > nul
copy "%DOCKER_DIR%\Dockerfile.identifier"   "%DEST%\docker\" > nul

:: Copy OS-specific overrides and scripts
xcopy /e /i /q "%DOCKER_DIR%\dev\%OS%\*" "%DEST%\docker\dev\%OS%\" > nul

:: Copy source (robocopy exit code 0=ok, 1=files copied, both are success)
robocopy "%ROOT%\studio"     "%DEST%\studio"     /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [WARN] robocopy error: %ROOT%\studio
robocopy "%ROOT%\identifier" "%DEST%\identifier" /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [WARN] robocopy error: %ROOT%\identifier
robocopy "%ROOT%\sql"        "%DEST%\sql"        /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [WARN] robocopy error: %ROOT%\sql

copy "%ROOT%\requirements.txt"             "%DEST%\" > nul
copy "%ROOT%\requirements-identifier.txt"  "%DEST%\" > nul
copy "%DOCKER_DIR%\.env.example"           "%DEST%\docker\" > nul

:: Create empty dirs for Docker volume mounts
for %%d in (
    data\mysql data\qdrant data\redis data\ollama
    data\hf-cache data\shared data\finetune
    logs\studio logs\identifier output
) do mkdir "%DEST%\%%d" 2>nul

echo [INFO] Studio %OS% package done: %DEST%
exit /b 0


:: --------------------------------------------
:PACKAGE_IDENTIFIER
set OS=%~1
set DEST=%SCRIPT_DIR%identifier-%OS%
echo.
echo ===== Building Identifier %OS% package =====

if exist "%DEST%" rd /s /q "%DEST%"
for %%d in (snapshots models data\qdrant data\redis data\ollama data\shared logs) do (
    mkdir "%DEST%\%%d" 2>nul
)

:: Copy docker files and scripts
copy "%DOCKER_DIR%\prod\%OS%\docker-compose.yml" "%DEST%\" > nul
copy "%DOCKER_DIR%\prod\%OS%\.env.example"       "%DEST%\" > nul

if "%OS%"=="windows" (
    copy "%DOCKER_DIR%\prod\%OS%\setup.bat" "%DEST%\" > nul
    copy "%DOCKER_DIR%\prod\%OS%\start.bat" "%DEST%\" > nul
    copy "%DOCKER_DIR%\prod\%OS%\stop.bat"  "%DEST%\" > nul
) else (
    copy "%DOCKER_DIR%\prod\%OS%\setup.sh"  "%DEST%\" > nul
    copy "%DOCKER_DIR%\prod\%OS%\start.sh"  "%DEST%\" > nul
    copy "%DOCKER_DIR%\prod\%OS%\stop.sh"   "%DEST%\" > nul
)

:: -- Build and save Identifier Docker image --
echo [INFO] Building Identifier Docker image...
cd /d "%ROOT%"
docker build -t reeve-identifier:latest -f docker\Dockerfile.identifier .
if errorlevel 1 (
    echo [ERROR] Docker image build failed
    exit /b 1
)

:: Docker Desktop requires WSL2 so wsl gzip is always available
echo [INFO] Saving image (this may take a while)...
docker save reeve-identifier:latest | wsl gzip > "%DEST%\reeve-identifier-latest.tar.gz"
if errorlevel 1 (
    echo [ERROR] Docker image save failed
    exit /b 1
)
echo [INFO] Image saved: reeve-identifier-latest.tar.gz

:: -- Export Qdrant snapshot --
curl -s http://localhost:6333/healthz > nul 2>&1
if not errorlevel 1 (
    echo [INFO] Creating Qdrant snapshot...

    :: Save response to temp file to avoid pipe quoting issues
    set SNAP_JSON=%TEMP%\reeve_snap.json
    curl -s -X POST "http://localhost:6333/collections/training_images/snapshots" -o "!SNAP_JSON!" 2>nul

    :: Write Python parser to temp file (no quoting issues with echo)
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
        echo        The training_images collection may not exist or have no data.
        echo        Run data sync in Studio first, or place the snapshot in snapshots\ manually.
    )
) else (
    echo [WARN] Qdrant is not running - skipping snapshot.
    echo        Start the service first, or place the snapshot in snapshots\ manually.
)

:: -- Copy Ollama models --
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

echo [INFO] Identifier %OS% package done: %DEST%
exit /b 0


