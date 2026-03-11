#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
# 실행 위치: docker/

echo "[Reeve Studio] Mac 서비스 시작 (CPU)"
docker compose -f docker-compose.yml -f dev/mac/docker-compose.yml up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Studio        : http://localhost:8000"
echo "  Identifier    : http://localhost:8001"
echo "  LLaMA-Factory : http://localhost:7860"
echo "  Qdrant        : http://localhost:6333/dashboard"
echo "  Ollama        : http://localhost:11434  (CPU 모드)"
