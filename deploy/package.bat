@echo off
setlocal EnableDelayedExpansion
chcp 65001 > nul

:: ══════════════════════════════════════════════════════════
:: Reeve 배포 패키지 생성 스크립트 (Windows)
::
:: 사용법:
::   package.bat [target]
::
:: target:
::   studio-mac        개발사 납품 — Mac 개발 환경
::   studio-linux      개발사 납품 — Linux 개발 환경
::   studio-windows    개발사 납품 — Windows 개발 환경
::   identifier-linux  고객사 납품 — Linux 운영 환경
::   identifier-windows 고객사 납품 — Windows 운영 환경
::   all               전체 패키지 생성
:: ══════════════════════════════════════════════════════════

set SCRIPT_DIR=%~dp0
:: SCRIPT_DIR = deploy\
set ROOT=%SCRIPT_DIR%..
:: ROOT = 프로젝트 루트
set DOCKER_DIR=%ROOT%\docker

set TARGET=%~1
if "%TARGET%"=="" (
    echo 사용법: package.bat [target]
    echo.
    echo   studio-mac          개발사 납품 — Mac 개발 환경
    echo   studio-linux        개발사 납품 — Linux 개발 환경
    echo   studio-windows      개발사 납품 — Windows 개발 환경
    echo   identifier-linux    고객사 납품 — Linux 운영 환경
    echo   identifier-windows  고객사 납품 — Windows 운영 환경
    echo   all                 전체 패키지 생성
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
echo [완료] deploy\ 폴더에서 각 패키지를 확인하세요.
exit /b 0


:: ────────────────────────────────────────────
:PACKAGE_STUDIO
set OS=%~1
set DEST=%SCRIPT_DIR%studio-%OS%
echo.
echo ===== Studio %OS% 패키지 생성 시작 =====

if exist "%DEST%" rd /s /q "%DEST%"
mkdir "%DEST%\docker\studio\%OS%"

:: docker 파일 복사
copy "%DOCKER_DIR%\docker-compose.yml"      "%DEST%\docker\" > nul
copy "%DOCKER_DIR%\Dockerfile"              "%DEST%\docker\" > nul
copy "%DOCKER_DIR%\Dockerfile.identifier"   "%DEST%\docker\" > nul

:: OS별 override + 스크립트 복사
xcopy /e /i /q "%DOCKER_DIR%\studio\%OS%\*" "%DEST%\docker\studio\%OS%\" > nul

:: 소스 복사 (robocopy: 0=OK, 1=복사완료, 둘다 성공)
call :ROBOCOPY_SOURCE "%ROOT%\studio"     "%DEST%\studio"
call :ROBOCOPY_SOURCE "%ROOT%\identifier" "%DEST%\identifier"
call :ROBOCOPY_SOURCE "%ROOT%\sql"        "%DEST%\sql"

copy "%ROOT%\requirements.txt"             "%DEST%\" > nul
copy "%ROOT%\requirements-identifier.txt"  "%DEST%\" > nul
copy "%ROOT%\.env.example"                 "%DEST%\" > nul

:: 빈 디렉토리 생성 (Docker 볼륨 마운트 대상)
for %%d in (
    data\mysql data\qdrant data\redis data\ollama
    data\hf-cache data\shared data\finetune
    logs\studio logs\identifier output
) do mkdir "%DEST%\%%d" 2>nul

echo [INFO] Studio %OS% 패키지 완료: %DEST%
exit /b 0


:: ────────────────────────────────────────────
:PACKAGE_IDENTIFIER
set OS=%~1
set DEST=%SCRIPT_DIR%identifier-%OS%
echo.
echo ===== Identifier %OS% 패키지 생성 시작 =====

if exist "%DEST%" rd /s /q "%DEST%"
for %%d in (snapshots models data\qdrant data\redis data\ollama data\shared logs) do (
    mkdir "%DEST%\%%d" 2>nul
)

:: docker 파일 + 스크립트 복사
copy "%DOCKER_DIR%\identifier\%OS%\docker-compose.yml" "%DEST%\" > nul
copy "%DOCKER_DIR%\identifier\%OS%\.env.example"       "%DEST%\" > nul

if "%OS%"=="windows" (
    copy "%DOCKER_DIR%\identifier\%OS%\setup.bat" "%DEST%\" > nul
    copy "%DOCKER_DIR%\identifier\%OS%\start.bat" "%DEST%\" > nul
    copy "%DOCKER_DIR%\identifier\%OS%\stop.bat"  "%DEST%\" > nul
) else (
    copy "%DOCKER_DIR%\identifier\%OS%\setup.sh"  "%DEST%\" > nul
    copy "%DOCKER_DIR%\identifier\%OS%\start.sh"  "%DEST%\" > nul
    copy "%DOCKER_DIR%\identifier\%OS%\stop.sh"   "%DEST%\" > nul
)

:: ── Identifier Docker 이미지 빌드 + 저장 ──
echo [INFO] Identifier Docker 이미지 빌드 중...
cd /d "%ROOT%"
docker build -t reeve-identifier:latest -f docker\Dockerfile.identifier .
if errorlevel 1 (
    echo [오류] Docker 이미지 빌드 실패
    exit /b 1
)

echo [INFO] 이미지 저장 중 (시간이 걸릴 수 있습니다)...
docker save reeve-identifier:latest | gzip > "%DEST%\reeve-identifier-latest.tar.gz"
echo [INFO] 이미지 저장 완료: reeve-identifier-latest.tar.gz

:: ── Qdrant 스냅샷 내보내기 ────────────────
curl -sf http://localhost:6333/healthz > nul 2>&1
if not errorlevel 1 (
    echo [INFO] Qdrant 스냅샷 생성 중...
    for /f "delims=" %%s in ('curl -sf -X POST "http://localhost:6333/collections/training_images/snapshots" ^| python -c "import sys,json; print(json.load(sys.stdin)[\"result\"][\"name\"])" 2^>nul') do set SNAP_NAME=%%s
    if defined SNAP_NAME (
        curl -sf -o "%DEST%\snapshots\training_images.snapshot" ^
            "http://localhost:6333/collections/training_images/snapshots/!SNAP_NAME!"
        echo [INFO] 스냅샷 저장 완료: snapshots\training_images.snapshot
    ) else (
        echo [경고] Qdrant 스냅샷 생성 실패. snapshots\ 폴더에 직접 넣으세요.
    )
) else (
    echo [경고] Qdrant가 실행되지 않아 스냅샷을 건너뜁니다.
    echo        서비스 실행 후 다시 packaging하거나 snapshots\ 에 직접 넣으세요.
)

:: ── Ollama 모델 복사 ──────────────────────
if exist "%ROOT%\data\ollama\*" (
    echo [INFO] Ollama 모델 복사 중...
    xcopy /e /i /q "%ROOT%\data\ollama\*" "%DEST%\data\ollama\" > nul
    echo [INFO] Ollama 모델 복사 완료
) else (
    echo [경고] data\ollama 가 비어있습니다.
    echo        파인튜닝 완료 후 다시 packaging하거나 models\ 에 GGUF + Modelfile을 직접 넣으세요.
)

echo [INFO] Identifier %OS% 패키지 완료: %DEST%
exit /b 0


:: ────────────────────────────────────────────
:ROBOCOPY_SOURCE
:: robocopy 종료코드 0,1은 성공
robocopy "%~1" "%~2" /e /xd __pycache__ .pytest_cache *.egg-info /xf *.pyc *.pyo .DS_Store > nul
if errorlevel 2 echo [경고] robocopy 오류: %~1
exit /b 0
