#!/bin/bash
# Celery Worker 시작 스크립트

set -e

# 환경변수에서 torch_threads 읽기 (기본값: 8)
TORCH_THREADS=${IDENTIFIER_TORCH_THREADS:-8}

# CPU 코어 수 감지
CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 8)

# Celery concurrency 계산 (workers와 동일하게)
CONCURRENCY=$((CPU_CORES / TORCH_THREADS))
if [ "$CONCURRENCY" -lt 1 ]; then
    CONCURRENCY=1
fi

echo "=========================================="
echo "Celery Worker Startup"
echo "=========================================="
echo "CPU cores: $CPU_CORES"
echo "PyTorch threads: $TORCH_THREADS"
echo "Celery concurrency: $CONCURRENCY"
echo "=========================================="

# Celery worker 실행
exec celery -A identifier.celery_app worker \
    --loglevel=info \
    --concurrency="$CONCURRENCY" \
    --max-tasks-per-child=100
