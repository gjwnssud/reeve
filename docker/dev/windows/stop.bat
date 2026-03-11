@echo off
cd /d "%~dp0..\.."
:: Running from: docker/

echo [Reeve Studio] Stopping services...
docker compose -f docker-compose.yml -f dev\windows\docker-compose.yml down

echo Done.
