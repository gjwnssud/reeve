@echo off
cd /d "%~dp0"
:: Running from: docker/identifier/windows/

echo [Reeve Identifier] Stopping services...
docker compose down

echo Done.
