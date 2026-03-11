#!/bin/bash
cd "$(dirname "$0")/../.."
# 실행 위치: docker/

echo "[Reeve Studio] 서비스 중지 중..."
docker compose -f docker-compose.yml -f dev/mac/docker-compose.yml down

echo "완료."
