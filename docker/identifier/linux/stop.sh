#!/bin/bash
cd "$(dirname "$0")"
# 실행 위치: docker/identifier/linux/

echo "[Reeve Identifier] 서비스 중지 중..."
docker compose down

echo "완료."
