@echo off
chcp 65001 > nul
cd /d "%~dp0..\.."
:: 실행 위치: docker/

echo [Reeve Studio] 서비스 중지 중...
docker compose -f docker-compose.yml -f studio\windows\docker-compose.windows.yml down

echo 완료.
