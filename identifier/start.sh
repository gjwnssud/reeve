#!/bin/bash
# Identifier 서비스 시작 스크립트

set -e

# 환경변수에서 torch_threads 읽기 (기본값: 8)
TORCH_THREADS=${IDENTIFIER_TORCH_THREADS:-8}

# CPU 코어 수 감지
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# ML 서비스는 workers=1 고정 (모델 다중 로드 방지, 비동기는 Celery가 처리)
# IDENTIFIER_WORKERS 환경변수로 override 가능
WORKERS=${IDENTIFIER_WORKERS:-1}

echo "=========================================="
echo "Identifier Service Startup"
echo "=========================================="
echo "CPU cores: $CPU_CORES"
echo "PyTorch threads: $TORCH_THREADS"
echo "Uvicorn workers: $WORKERS"
echo "=========================================="

# uvicorn 실행
exec uvicorn identifier.main:app \
    --host 0.0.0.0 \
    --port ${IDENTIFIER_PORT:-8001} \
    --workers "$WORKERS" \
    --no-access-log
