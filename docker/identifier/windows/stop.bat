@echo off
chcp 65001 > nul
cd /d "%~dp0"
:: 실행 위치: docker/identifier/windows/

echo [Reeve Identifier] 서비스 중지 중...
docker compose down

echo 완료.
