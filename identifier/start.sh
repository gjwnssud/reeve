#!/bin/bash
# Identifier 서비스 시작 스크립트
# CPU 코어 수를 감지하여 uvicorn workers 자동 계산

set -e

# 환경변수에서 torch_threads 읽기 (기본값: 8)
TORCH_THREADS=${IDENTIFIER_TORCH_THREADS:-8}

# CPU 코어 수 감지
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# workers 계산 (최소 1)
WORKERS=$((CPU_CORES / TORCH_THREADS))
if [ "$WORKERS" -lt 1 ]; then
    WORKERS=1
fi

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
