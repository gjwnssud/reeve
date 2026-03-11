#!/bin/bash
set -e
cd "$(dirname "$0")/../.."
# 실행 위치: docker/

echo "[Reeve Studio] Mac 초기 설정"
echo "======================================"

# ── 1. Docker Desktop 확인 ──────────────────
echo "[1/4] Docker Desktop 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker Desktop이 실행되지 않았습니다."
    echo "       Docker Desktop을 시작한 후 다시 실행하세요."
    exit 1
fi
echo "      OK"

# ── 2. 안내 ─────────────────────────────────
echo "[2/4] Mac 환경 확인..."
echo "      ollama: Docker CPU 모드로 실행 (Apple GPU 미지원)"
echo "      llamafactory: Docker CPU 모드로 실행"

# ── 3. .env 파일 생성 ───────────────────────
echo "[3/4] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp ".env.example" ".env"
        echo "      .env 파일이 생성되었습니다."
        echo ""
        echo " ★ 필수 수정 항목:"
        echo "   - OPENAI_API_KEY"
        echo "   - MYSQL_ROOT_PASSWORD"
        echo "   - MYSQL_PASSWORD"
        echo ""
        echo "   docker/.env 파일을 편집한 후 start.sh를 실행하세요."
        open ".env" 2>/dev/null || echo "   (텍스트 편집기로 docker/.env를 열어 수정하세요.)"
        exit 0
    else
        echo "[오류] .env.example 파일을 찾을 수 없습니다."
        exit 1
    fi
else
    echo "      .env 파일 존재 확인"
fi

# ── 4. 이미지 빌드 / Pull ───────────────────
echo "[4/4] Docker 이미지 준비 중..."
docker compose -f docker-compose.yml -f dev/mac/docker-compose.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f dev/mac/docker-compose.yml build

echo ""
echo "======================================"
echo "초기 설정 완료. ./dev/mac/start.sh 로 서비스를 시작하세요."
echo "======================================"
