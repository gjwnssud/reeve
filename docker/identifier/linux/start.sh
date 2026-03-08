#!/bin/bash
set -e
cd "$(dirname "$0")"
# 실행 위치: docker/identifier/linux/

echo "[Reeve Identifier] 서비스 시작 (GPU)"
docker compose up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Identifier API : http://localhost:8001"
echo "  Identifier Docs: http://localhost:8001/docs"
echo "  Qdrant Dashboard: http://localhost:6333/dashboard"
