#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
# 실행 위치: docker/

echo "[Reeve Studio] Linux 초기 설정 (GPU)"
echo "======================================"

# ── 1. Docker 확인 ───────────────────────────
echo "[1/4] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker가 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

# ── 2. NVIDIA GPU 확인 ───────────────────────
echo "[2/4] NVIDIA GPU 확인 중..."
if ! nvidia-smi > /dev/null 2>&1; then
    echo "[경고] NVIDIA GPU를 감지하지 못했습니다."
    echo "       nvidia-container-toolkit이 설치되어 있는지 확인하세요."
    read -p "계속 진행하시겠습니까? (y/N): " CONTINUE
    [[ "$CONTINUE" =~ ^[Yy]$ ]] || exit 1
else
    nvidia-smi --query-gpu=name --format=csv,noheader | while read name; do
        echo "      GPU: $name"
    done
fi

# ── 3. .env 파일 생성 ────────────────────────
echo "[3/4] 환경변수 파일 확인 중..."
if [ ! -f "../.env" ]; then
    cp "../.env.example" "../.env"
    echo "      .env 파일이 생성되었습니다."
    echo ""
    echo " ★ 필수 수정 항목:"
    echo "   - OPENAI_API_KEY"
    echo "   - MYSQL_ROOT_PASSWORD"
    echo "   - MYSQL_PASSWORD"
    echo ""
    echo "   ../.env 파일을 편집한 후 start.sh를 실행하세요."
    exit 0
else
    echo "      .env 파일 존재 확인"
fi

# ── 4. 이미지 빌드 / Pull ───────────────────
echo "[4/4] Docker 이미지 준비 중..."
docker compose -f docker-compose.yml -f studio/linux/docker-compose.linux.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f studio/linux/docker-compose.linux.yml build

echo ""
echo "======================================"
echo "초기 설정 완료. ./studio/linux/start.sh 로 서비스를 시작하세요."
echo "======================================"
