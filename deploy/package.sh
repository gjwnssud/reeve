#!/bin/bash
# ══════════════════════════════════════════════════════════
# Reeve 배포 패키지 생성 스크립트 (Mac/Linux)
#
# 사용법:
#   ./package.sh [target]
#
# target:
#   dev-linux     개발사 납품 — Linux 개발 환경 (GPU)
#   dev-windows   개발사 납품 — Windows 개발 환경 (GPU)
#   dev-mac       개발사 납품 — Mac 개발 환경 (Apple Silicon, 네이티브 Trainer)
#   prod-linux    고객사 납품 — Linux 운영 환경
#   prod-windows  고객사 납품 — Windows 운영 환경
#   all           전체 패키지 생성
# ══════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"  # deploy/
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"          # 프로젝트 루트
DOCKER_DIR="$ROOT/docker"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── rsync 제외 패턴 ─────────────────────────────────────
RSYNC_EXCLUDES=(
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='*.pyo'
    --exclude='.DS_Store'
    --exclude='*.egg-info/'
    --exclude='.pytest_cache/'
)

RSYNC_FRONTEND_EXCLUDES=(
    --exclude='node_modules/'
    --exclude='.pnpm-store/'
    --exclude='dist/'
    --exclude='*.tsbuildinfo'
)

# ── compose 파일 경로 패치 (docker/ 기준 → 배포 패키지 루트 기준) ──
# context: .. → context: .
# dockerfile: docker/XXX → dockerfile: XXX
# - ../ (볼륨 마운트) → - ./
patch_compose() {
    sed \
        -e 's|context: \.\.|context: .|g' \
        -e 's|dockerfile: docker/|dockerfile: |g' \
        -e 's|- \.\./|- ./|g' \
        "$1"
}

# ══════════════════════════════════════════════════════════
# Dev 패키지
# ══════════════════════════════════════════════════════════
package_dev() {
    local os="$1"   # linux | windows
    local dest="$SCRIPT_DIR/dev/$os"

    info "===== Dev $os 패키지 생성 시작 ====="

    # data/, logs/ 는 운영 데이터이므로 보존 — 소스 파일만 교체
    if [ -d "$dest" ]; then
        find "$dest" -maxdepth 1 -mindepth 1 \
            ! -name 'data' ! -name 'logs' \
            -exec rm -rf {} +
    fi
    mkdir -p "$dest"

    # docker 파일 복사 (경로 패치 적용)
    patch_compose "$DOCKER_DIR/docker-compose.yml"     > "$dest/docker-compose.yml"
    patch_compose "$DOCKER_DIR/docker-compose.dev.yml" > "$dest/docker-compose.dev.yml"
    cp "$DOCKER_DIR/docker-compose.gpu.yml" "$dest/docker-compose.gpu.yml"
    cp "$DOCKER_DIR/docker-compose.ssl.yml" "$dest/docker-compose.ssl.yml"
    cp "$DOCKER_DIR/Dockerfile"            "$dest/"
    cp "$DOCKER_DIR/Dockerfile.studio"     "$dest/"
    cp "$DOCKER_DIR/Dockerfile.identifier" "$dest/"
    cp "$DOCKER_DIR/Dockerfile.trainer"    "$dest/"
    cp "$DOCKER_DIR/.env.example"          "$dest/"
    cp "$ROOT/.dockerignore"               "$dest/"
    install -m 755 "$DOCKER_DIR/gen-cert.sh" "$dest/gen-cert.sh"

    # 소스 코드 복사
    info "소스 코드 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/studio/"     "$dest/studio/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/identifier/" "$dest/identifier/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/trainer/"    "$dest/trainer/"
    rsync -a "$ROOT/sql/"                               "$dest/sql/"
    cp "$ROOT/requirements.txt"            "$dest/"
    cp "$ROOT/requirements-identifier.txt" "$dest/"

    # 프론트엔드 소스 복사 (Docker 멀티스테이지 빌드에서 사용)
    info "프론트엔드 소스 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "${RSYNC_FRONTEND_EXCLUDES[@]}" "$ROOT/frontend/" "$dest/frontend/"

    # 빈 디렉토리 생성 (Docker 볼륨 마운트 대상)
    mkdir -p "$dest/data/mysql" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/hf-cache" "$dest/data/shared" \
             "$dest/data/finetune" \
             "$dest/data/models/efficientnet" "$dest/data/models/vlm" \
             "$dest/data/checkpoints/vlm" \
             "$dest/logs/studio" "$dest/logs/identifier"

    # Ollama Modelfile — VLM GGUF export 결과와 같은 위치에 배치
    cp "$DOCKER_DIR/ollama/Modelfile" "$dest/data/models/vlm/Modelfile"

    if [ "$os" = "linux" ]; then
        _write_dev_linux_scripts "$dest"
    else
        _write_dev_windows_scripts "$dest"
    fi

    info "Dev $os 패키지 완료: $dest"
    echo ""
}

_write_dev_linux_scripts() {
    local dest="$1"

    cat > "$dest/setup.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve] Linux 초기 설정 (GPU)"
echo "======================================"

echo "[1/4] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker가 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

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

echo "[3/4] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "      .env 파일이 생성되었습니다."
    echo ""
    echo " ★ 필수 수정 항목:"
    echo "   - OPENAI_API_KEY        (OpenAI Vision API 키)"
    echo "   - GEMINI_API_KEY        (Google Gemini API 키, 교차검증용)"
    echo "   - MYSQL_PASSWORD"
    echo ""
    echo "   .env 파일을 편집한 후 start.sh를 실행하세요."
    exit 0
else
    echo "      .env 파일 존재 확인"
fi

echo "[4/4] Docker 이미지 준비 중..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml build

echo ""
echo "======================================"
echo "초기 설정 완료. ./start.sh 로 서비스를 시작하세요."
echo "======================================"
EOF

    cat > "$dest/start.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

# .env 로드 (포트, 백엔드 설정 등)
if [ -f ".env" ]; then
    set -o allexport; source .env; set +o allexport
fi

_STUDIO_PORT="${STUDIO_PORT:-8000}"
_IDENTIFIER_PORT="${IDENTIFIER_PORT:-8001}"
_TRAINER_PORT="${TRAINER_PORT:-8002}"
_OLLAMA_PORT="${OLLAMA_PORT:-11434}"
_TRAINER_BACKEND="${TRAINER_BACKEND:-efficientnet}"

SSL_COMPOSE=""
if [ -f "certs/cert.pem" ] && [ -f "certs/key.pem" ]; then
    SSL_COMPOSE="-f docker-compose.ssl.yml"
fi

PROTO="http"
[ -n "$SSL_COMPOSE" ] && PROTO="https"

echo "[Reeve] Linux 서비스 시작 (GPU)"
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml $SSL_COMPOSE down 2>/dev/null || true
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml $SSL_COMPOSE up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Studio        : ${PROTO}://localhost:${_STUDIO_PORT}"
echo "  Identifier    : ${PROTO}://localhost:${_IDENTIFIER_PORT}"
echo "  Trainer       : http://localhost:${_TRAINER_PORT}  (${_TRAINER_BACKEND}, NVIDIA GPU)"
echo "  Ollama        : http://localhost:${_OLLAMA_PORT}  (NVIDIA GPU)"
EOF

    cat > "$dest/stop.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

echo "[Reeve] 서비스 중지 중..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml down

echo "완료."
EOF

    chmod +x "$dest/setup.sh" "$dest/start.sh" "$dest/stop.sh"
}

_write_dev_windows_scripts() {
    local dest="$1"

    cat > "$dest/setup.bat" << 'EOF'
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo [Reeve Studio] Windows 초기 설정 (GPU)
echo ======================================

echo [1/4] Docker Desktop 확인 중...
docker info > nul 2>&1
if errorlevel 1 (
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo        Docker Desktop을 시작한 후 다시 실행하세요.
    pause
    exit /b 1
)
echo       OK

echo [2/4] NVIDIA GPU 확인 중...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [경고] NVIDIA GPU를 감지하지 못했습니다.
    echo        ollama, llamafactory가 CPU로 실행됩니다.
    set /p CONTINUE="계속 진행하시겠습니까? (y/N): "
    if /i "!CONTINUE!" neq "y" exit /b 1
) else (
    for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name --format=csv^,noheader 2^>nul') do (
        echo       GPU 감지: %%g
    )
)

echo [3/4] 환경변수 파일 확인 중...
if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" > nul
        echo       .env 파일이 생성되었습니다.
        echo.
        echo  * 필수 수정 항목:
        echo    - OPENAI_API_KEY        (OpenAI Vision API 키)
        echo    - GEMINI_API_KEY        (Google Gemini API 키, 교차검증용)
        echo    - MYSQL_PASSWORD
        echo.
        echo    .env 파일을 편집한 후 start.bat을 실행하세요.
        start notepad ".env"
        pause
        exit /b 0
    ) else (
        echo [오류] .env.example 파일을 찾을 수 없습니다.
        pause
        exit /b 1
    )
) else (
    echo       .env 파일 존재 확인
)

echo [4/4] Docker 이미지 준비 중...
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml build

echo.
echo ======================================
echo 초기 설정 완료. start.bat으로 서비스를 시작하세요.
echo ======================================
pause
EOF

    cat > "$dest/start.bat" << 'EOF'
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set _STUDIO_PORT=8000
set _IDENTIFIER_PORT=8001
set _TRAINER_PORT=8002
set _OLLAMA_PORT=11434
set _TRAINER_BACKEND=efficientnet

if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if "%%a"=="STUDIO_PORT"      set _STUDIO_PORT=%%b
        if "%%a"=="IDENTIFIER_PORT"  set _IDENTIFIER_PORT=%%b
        if "%%a"=="TRAINER_PORT"     set _TRAINER_PORT=%%b
        if "%%a"=="OLLAMA_PORT"      set _OLLAMA_PORT=%%b
        if "%%a"=="TRAINER_BACKEND"  set _TRAINER_BACKEND=%%b
    )
)

set SSL_COMPOSE=
if exist "certs\cert.pem" if exist "certs\key.pem" set SSL_COMPOSE=-f docker-compose.ssl.yml

set PROTO=http
if defined SSL_COMPOSE set PROTO=https

echo [Reeve] Windows 서비스 시작 (GPU)...
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml !SSL_COMPOSE! down 2>nul
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml !SSL_COMPOSE! up -d

if errorlevel 1 (
    echo [오류] 서비스 시작 실패. 로그를 확인하세요:
    echo        docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml logs
    pause
    exit /b 1
)

echo.
echo 서비스가 시작되었습니다:
echo   Studio        : !PROTO!://localhost:!_STUDIO_PORT!
echo   Identifier    : !PROTO!://localhost:!_IDENTIFIER_PORT!
echo   Trainer       : http://localhost:!_TRAINER_PORT!  (!_TRAINER_BACKEND!, NVIDIA GPU)
echo   Ollama        : http://localhost:!_OLLAMA_PORT!  (NVIDIA GPU)
EOF

    cat > "$dest/stop.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Studio] 서비스 중지 중...
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.gpu.yml down

echo 완료.
EOF
}

# ══════════════════════════════════════════════════════════
# Prod 패키지
# ══════════════════════════════════════════════════════════
package_prod() {
    local os="$1"   # linux | windows
    local dest="$SCRIPT_DIR/prod/$os"

    info "===== Prod $os 패키지 생성 시작 ====="

    rm -rf "$dest"
    mkdir -p "$dest/models" \
             "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/shared" \
             "$dest/logs"

    # Dockerfile.identifier → Dockerfile (standalone 빌드용)
    cp "$DOCKER_DIR/Dockerfile.identifier" "$dest/Dockerfile"

    # prod docker-compose.yml 생성 (standalone, pre-built image 기반)
    _write_prod_compose "$dest"

    # .env.example (Identifier 전용)
    _write_prod_env_example "$dest"

    # Ollama Modelfile (파인튜닝 GGUF 배포용)
    cp "$DOCKER_DIR/ollama/Modelfile" "$dest/models/Modelfile"

    # OS별 스크립트 생성
    if [ "$os" = "linux" ]; then
        _write_prod_linux_scripts "$dest"
    else
        _write_prod_windows_scripts "$dest"
    fi

    # Docker 이미지 빌드 + 저장 (임시 태그 사용 → 기존 reeve-identifier:latest 보존)
    local TMP_TAG="reeve-identifier:pkg-$(date +%s)"
    info "Identifier Docker 이미지 빌드 중... (tag: $TMP_TAG)"
    cd "$ROOT"
    docker build -t "$TMP_TAG" -f docker/Dockerfile.identifier . \
        || error "Docker 이미지 빌드 실패"

    info "이미지 저장 중 (시간이 걸릴 수 있습니다)..."
    docker save "$TMP_TAG" | gzip > "$dest/reeve-identifier-latest.tar.gz"
    local img_size
    img_size=$(du -sh "$dest/reeve-identifier-latest.tar.gz" | cut -f1)
    info "이미지 저장 완료: reeve-identifier-latest.tar.gz ($img_size)"

    info "임시 이미지 삭제 중: $TMP_TAG"
    docker rmi "$TMP_TAG" > /dev/null 2>&1 || true

    # EfficientNet 파인튜닝 모델 복사 (존재 시)
    local eff_src="$ROOT/data/models/efficientnet"
    if [ -d "$eff_src" ] && [ -n "$(ls -A "$eff_src" 2>/dev/null)" ]; then
        info "EfficientNet 모델 복사 중..."
        mkdir -p "$dest/models/efficientnet"
        cp -r "$eff_src/." "$dest/models/efficientnet/"
        info "EfficientNet 모델 복사 완료"
    else
        warn "data/models/efficientnet 가 비어있습니다."
        warn "Trainer 학습 완료 후 다시 packaging하거나 models/efficientnet/ 에 .pth를 직접 넣으세요."
    fi

    # Ollama 모델 복사
    local ollama_src="$ROOT/data/ollama"
    if [ -d "$ollama_src" ] && [ -n "$(ls -A "$ollama_src" 2>/dev/null)" ]; then
        info "Ollama 모델 복사 중..."
        cp -r "$ollama_src/." "$dest/data/ollama/"
        info "Ollama 모델 복사 완료"
    else
        warn "data/ollama 가 비어있습니다."
        warn "파인튜닝 완료 후 다시 packaging하거나 models/ 에 GGUF + Modelfile을 직접 넣으세요."
    fi

    info "Prod $os 패키지 완료: $dest"
    echo ""
}

_write_prod_compose() {
    local dest="$1"
    cat > "$dest/docker-compose.yml" << 'EOF'
name: reeve-identifier

# ──────────────────────────────────────────
# Identifier 납품 패키지 (NVIDIA GPU)
# 포함 서비스: redis + identifier + celery-worker + ollama
# 이미지 빌드: docker build -t reeve-identifier:latest -f Dockerfile .
# ──────────────────────────────────────────

services:
  redis:
    image: redis:7.4-alpine
    container_name: reeve-redis
    ports:
      - "6379:6379"
    volumes:
      - ./data/redis:/data
    networks:
      - reeve-network
    restart: unless-stopped
    command: redis-server --appendonly yes
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M

  identifier:
    image: reeve-identifier:latest
    container_name: reeve-identifier
    env_file:
      - .env
    ports:
      - "8001:8001"
    volumes:
      - ./logs:/app/logs
      - ./data/shared:/app/shared
      - ./models/efficientnet:/app/data/models/efficientnet
    environment:
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
      - EMBEDDING_DEVICE=cuda
    depends_on:
      redis:
        condition: service_started
    networks:
      - reeve-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G

  celery-worker:
    image: reeve-identifier:latest
    container_name: reeve-celery-worker
    env_file:
      - .env
    command: /app/identifier/start_worker.sh
    volumes:
      - ./logs:/app/logs
      - ./data/shared:/app/shared
      - ./models/efficientnet:/app/data/models/efficientnet
    environment:
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
      - EMBEDDING_DEVICE=cuda
    depends_on:
      redis:
        condition: service_started
    networks:
      - reeve-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '6.0'
          memory: 4G
        reservations:
          cpus: '2.0'
          memory: 2G

  ollama:
    image: ollama/ollama:latest
    container_name: reeve-ollama
    ports:
      - "11434:11434"
    environment:
      - OLLAMA_NUM_CTX=${OLLAMA_NUM_CTX:-8192}
    volumes:
      - ./data/ollama:/root/.ollama
    networks:
      - reeve-network
    restart: unless-stopped
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
        limits:
          memory: 16G

networks:
  reeve-network:
    driver: bridge
EOF
}

_write_prod_env_example() {
    local dest="$1"
    cat > "$dest/.env.example" << 'EOF'
# ──────────────────────────────────────────
# Identifier 서비스 환경변수
# 이 파일을 .env로 복사 후 수정하세요
# ──────────────────────────────────────────

# Embedding
EMBEDDING_DEVICE=cuda

# 판별 모드: efficientnet | vlm_only
IDENTIFIER_MODE=efficientnet

# VLM (Ollama) — vlm_only 모드에서만 사용
# 기본 모델(파인튜닝 없음): qwen3-vl:8b
# 파인튜닝 GGUF 배포 시: reeve-vlm-v1
OLLAMA_BASE_URL=http://ollama:11434
VLM_MODEL_NAME=qwen3-vl:8b
# KV 캐시 크기 제한 — 기본 256K는 ~36 GB를 소모하므로 차량 분석 용도에 맞게 축소
# 8192: ~1.1 GB (권장), 4096: ~0.6 GB, 16384: ~2.2 GB
OLLAMA_NUM_CTX=8192
VLM_TIMEOUT=30
VLM_BATCH_CONCURRENCY=2

# 판별 파라미터
IDENTIFIER_PORT=8001
CLASSIFIER_CONFIDENCE_THRESHOLD=0.80
CLASSIFIER_LOW_CONFIDENCE_THRESHOLD=0.40
IDENTIFIER_VEHICLE_DETECTION=true
IDENTIFIER_YOLO_CONFIDENCE=0.25
IDENTIFIER_CROP_PADDING=10

# 성능
IDENTIFIER_TORCH_THREADS=4
IDENTIFIER_BATCH_SIZE=32
IDENTIFIER_MAX_BATCH_FILES=100
IDENTIFIER_MAX_BATCH_UPLOAD_SIZE=104857600
IDENTIFIER_ENABLE_TORCH_COMPILE=true

# Redis / Celery
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
CELERY_TASK_TIME_LIMIT=600
CELERY_TASK_SOFT_TIME_LIMIT=540
CELERY_MAX_RETRIES=3

# 파일 업로드
MAX_UPLOAD_SIZE=5242880
ALLOWED_EXTENSIONS=jpg,jpeg,png,webp

# 로그
LOG_LEVEL=INFO
IDENTIFIER_LOG_FILE=./logs/identifier/service.log
EOF
}

_write_prod_linux_scripts() {
    local dest="$1"

    cat > "$dest/setup.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve Identifier] Linux 초기 설정"
echo "======================================"

echo "[1/6] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker가 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

echo "[2/6] NVIDIA GPU 확인 중..."
if ! nvidia-smi > /dev/null 2>&1; then
    echo "[오류] NVIDIA GPU를 감지하지 못했습니다."
    echo "       nvidia-container-toolkit이 설치되어 있는지 확인하세요."
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | while read line; do
    echo "      GPU: $line"
done

echo "[3/6] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "      .env 파일이 생성되었습니다. 필요시 내용을 수정하세요."
else
    echo "      .env 파일 존재 확인"
fi

echo "[4/6] EfficientNet 모델 확인 중..."
EFF_MODEL=$(ls models/efficientnet/*.pth 2>/dev/null | head -1)
if [ -n "$EFF_MODEL" ]; then
    echo "      OK: $EFF_MODEL"
else
    echo "[경고] models/efficientnet/ 에 .pth 파일이 없습니다."
    echo "       IDENTIFIER_MODE=efficientnet 모드에서는 파인튜닝된 모델이 필요합니다."
    echo "       Trainer에서 학습 후 생성된 .pth 파일을 넣으세요."
fi

echo "[5/6] Identifier 이미지 확인 중..."
if ! docker image inspect reeve-identifier:latest > /dev/null 2>&1; then
    IMAGE_TAR=$(ls reeve-identifier-*.tar.gz 2>/dev/null | head -1)
    if [ -n "$IMAGE_TAR" ]; then
        echo "      이미지 로드 중: $IMAGE_TAR"
        LOAD_OUT=$(docker load < "$IMAGE_TAR")
        echo "$LOAD_OUT"
        LOADED_TAG=$(echo "$LOAD_OUT" | grep "Loaded image:" | awk '{print $NF}')
        if [ -n "$LOADED_TAG" ] && [ "$LOADED_TAG" != "reeve-identifier:latest" ]; then
            docker tag "$LOADED_TAG" reeve-identifier:latest
            echo "      태그 설정: $LOADED_TAG → reeve-identifier:latest"
        fi
    else
        echo "[오류] reeve-identifier:latest 이미지를 찾을 수 없습니다."
        echo "       reeve-identifier-*.tar.gz 파일을 이 디렉토리에 넣거나"
        echo "       docker build -t reeve-identifier:latest -f Dockerfile . 로 빌드하세요."
        exit 1
    fi
else
    echo "      reeve-identifier:latest 확인"
fi

echo "[6/6] 서비스 시작 중..."
docker compose down 2>/dev/null || true
docker compose up -d

echo ""
echo "Ollama 준비 대기 중..."
for i in $(seq 1 30); do
    if docker exec reeve-ollama ollama list > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

MODEL_NAME=$(grep VLM_MODEL_NAME .env | cut -d= -f2 | tr -d ' ')
MODEL_NAME="${MODEL_NAME:-qwen3-vl:8b}"

if docker exec reeve-ollama ollama list | grep -q "$MODEL_NAME"; then
    echo "Ollama 모델 '$MODEL_NAME' 이미 존재합니다."
else
    GGUF_FILE=$(ls models/*.gguf 2>/dev/null | head -1)
    MODELFILE="models/Modelfile"
    if [ -n "$GGUF_FILE" ] && [ -f "$MODELFILE" ]; then
        # 파인튜닝된 GGUF → reeve-vlm-v1 등록
        echo "Ollama 모델 등록 중 (GGUF): $MODEL_NAME"
        docker cp "$GGUF_FILE" reeve-ollama:/root/$(basename "$GGUF_FILE")
        docker cp "$MODELFILE" reeve-ollama:/root/Modelfile
        docker exec reeve-ollama ollama create "$MODEL_NAME" -f /root/Modelfile
        echo "모델 등록 완료: $MODEL_NAME"
    else
        # 기본 모델 — Ollama 레지스트리에서 직접 pull
        echo "Ollama 기본 모델 다운로드 중: $MODEL_NAME"
        echo "(qwen3-vl:8b 기준 약 5GB, 네트워크 환경에 따라 시간이 걸립니다)"
        docker exec reeve-ollama ollama pull "$MODEL_NAME"
        echo "모델 다운로드 완료: $MODEL_NAME"
    fi
fi

echo ""
echo "======================================"
echo "설정 완료."
echo "  Identifier API  : http://localhost:8001"
echo "  Identifier Docs : http://localhost:8001/docs"
echo "======================================"
EOF

    cat > "$dest/start.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve Identifier] 서비스 시작 (GPU)"
docker compose down 2>/dev/null || true
docker compose up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Identifier API  : http://localhost:8001"
echo "  Identifier Docs : http://localhost:8001/docs"
EOF

    cat > "$dest/stop.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

echo "[Reeve Identifier] 서비스 중지 중..."
docker compose down

echo "완료."
EOF

    chmod +x "$dest/setup.sh" "$dest/start.sh" "$dest/stop.sh"
}

_write_prod_windows_scripts() {
    local dest="$1"

    cat > "$dest/setup.bat" << 'EOF'
@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

echo [Reeve Identifier] Windows 초기 설정
echo ======================================

echo [1/6] Docker Desktop 확인 중...
docker info > nul 2>&1
if errorlevel 1 (
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo        Docker Desktop을 시작한 후 다시 실행하세요.
    pause
    exit /b 1
)
echo       OK

echo [2/6] NVIDIA GPU 확인 중...
nvidia-smi > nul 2>&1
if errorlevel 1 (
    echo [오류] NVIDIA GPU를 감지하지 못했습니다.
    echo        Docker Desktop + WSL2 + NVIDIA Container Toolkit이 필요합니다.
    pause
    exit /b 1
)
for /f "tokens=*" %%g in ('nvidia-smi --query-gpu=name,memory.total --format=csv^,noheader 2^>nul') do (
    echo       GPU: %%g
)

echo [3/6] 환경변수 파일 확인 중...
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo       .env 파일이 생성되었습니다. 필요시 내용을 수정하세요.
) else (
    echo       .env 파일 존재 확인
)

echo [4/6] EfficientNet 모델 확인 중...
set EFF_MODEL=
for %%f in (models\efficientnet\*.pth) do set EFF_MODEL=%%f
if defined EFF_MODEL (
    echo       OK: %EFF_MODEL%
) else (
    echo [경고] models\efficientnet\ 에 .pth 파일이 없습니다.
    echo        IDENTIFIER_MODE=efficientnet 모드에서는 파인튜닝된 모델이 필요합니다.
    echo        Trainer에서 학습 후 생성된 .pth 파일을 넣으세요.
)

echo [5/6] Identifier 이미지 확인 중...
docker image inspect reeve-identifier:latest > nul 2>&1
if errorlevel 1 (
    set IMAGE_TAR=
    for %%f in (reeve-identifier-*.tar.gz) do set IMAGE_TAR=%%f
    if defined IMAGE_TAR (
        echo       이미지 로드 중: !IMAGE_TAR!
        docker load < "!IMAGE_TAR!" > "%TEMP%\reeve_load.txt"
        if errorlevel 1 (
            echo [오류] Docker 이미지 로드 실패.
            del "%TEMP%\reeve_load.txt" 2>nul
            pause
            exit /b 1
        )
        set LOADED_TAG=
        for /f "tokens=3" %%t in ('findstr /i "Loaded image:" "%TEMP%\reeve_load.txt"') do set LOADED_TAG=%%t
        del "%TEMP%\reeve_load.txt" 2>nul
        if defined LOADED_TAG (
            if "!LOADED_TAG!" neq "reeve-identifier:latest" (
                docker tag "!LOADED_TAG!" reeve-identifier:latest
                echo       태그 설정: !LOADED_TAG! -^> reeve-identifier:latest
            )
        )
    ) else (
        echo [오류] reeve-identifier:latest 이미지를 찾을 수 없습니다.
        echo        reeve-identifier-*.tar.gz 를 이 폴더에 넣거나
        echo        docker build -t reeve-identifier:latest -f Dockerfile . 로 빌드하세요.
        pause
        exit /b 1
    )
) else (
    echo       reeve-identifier:latest 확인
)

echo [6/6] 서비스 시작 중...
docker compose down 2>nul
docker compose up -d
if errorlevel 1 (
    echo [오류] 서비스 시작 실패.
    pause
    exit /b 1
)

echo.
echo Ollama 준비 대기 중...
:OLLAMA_WAIT
timeout /t 2 /nobreak > nul
docker exec reeve-ollama ollama list > nul 2>&1
if errorlevel 1 goto OLLAMA_WAIT

set MODEL_NAME=qwen3-vl:8b
for /f "tokens=2 delims==" %%a in ('findstr /i "^VLM_MODEL_NAME" .env 2^>nul') do set MODEL_NAME=%%a

docker exec reeve-ollama ollama list | findstr /i "%MODEL_NAME%" > nul 2>&1
if not errorlevel 1 (
    echo Ollama 모델 '%MODEL_NAME%' 이미 존재합니다.
) else (
    set GGUF_FILE=
    for %%f in (models\*.gguf) do set GGUF_FILE=%%f
    if defined GGUF_FILE (
        if exist "models\Modelfile" (
            echo Ollama 모델 등록 중 (GGUF): %MODEL_NAME%
            for %%f in (!GGUF_FILE!) do docker cp "%%f" reeve-ollama:/root/%%~nxf
            docker cp "models\Modelfile" reeve-ollama:/root/Modelfile
            docker exec reeve-ollama ollama create %MODEL_NAME% -f /root/Modelfile
            if errorlevel 1 (
                echo [경고] Ollama 모델 등록 실패.
            ) else (
                echo 모델 등록 완료: %MODEL_NAME%
            )
        ) else (
            echo [정보] models\Modelfile이 없습니다.
        )
    ) else (
        echo Ollama 기본 모델 다운로드 중: %MODEL_NAME%
        echo (qwen3-vl:8b 기준 약 5GB, 네트워크 환경에 따라 시간이 걸립니다)
        docker exec reeve-ollama ollama pull %MODEL_NAME%
        if errorlevel 1 (
            echo [경고] 모델 다운로드 실패. 네트워크를 확인하거나 수동으로 실행하세요:
            echo        docker exec reeve-ollama ollama pull %MODEL_NAME%
        ) else (
            echo 모델 다운로드 완료: %MODEL_NAME%
        )
    )
)

echo.
echo ======================================
echo 설정 완료.
echo   Identifier API  : http://localhost:8001
echo   Identifier Docs : http://localhost:8001/docs
echo ======================================
pause
EOF

    cat > "$dest/start.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Identifier] 서비스 시작 (GPU)...
docker compose down 2>nul
docker compose up -d

if errorlevel 1 (
    echo [오류] 서비스 시작 실패. 로그를 확인하세요:
    echo        docker compose logs
    pause
    exit /b 1
)

echo.
echo 서비스가 시작되었습니다:
echo   Identifier API  : http://localhost:8001
echo   Identifier Docs : http://localhost:8001/docs
EOF

    cat > "$dest/stop.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Identifier] 서비스 중지 중...
docker compose down

echo 완료.
EOF
}

# ══════════════════════════════════════════════════════════
# Dev Mac 패키지 (Apple Silicon, 네이티브 Trainer)
# ══════════════════════════════════════════════════════════
package_dev_mac() {
    local dest="$SCRIPT_DIR/dev/mac"

    info "===== Dev mac 패키지 생성 시작 ====="

    # data/, logs/ 는 운영 데이터이므로 보존 — 소스 파일만 교체
    if [ -d "$dest" ]; then
        find "$dest" -maxdepth 1 -mindepth 1 \
            ! -name 'data' ! -name 'logs' \
            -exec rm -rf {} +
    fi
    mkdir -p "$dest"

    # docker 파일 복사 (base + dev + mac 오버라이드, 경로 패치 적용)
    patch_compose "$DOCKER_DIR/docker-compose.yml"     > "$dest/docker-compose.yml"
    patch_compose "$DOCKER_DIR/docker-compose.dev.yml" > "$dest/docker-compose.dev.yml"
    cp "$DOCKER_DIR/docker-compose.mac.yml"  "$dest/docker-compose.mac.yml"
    cp "$DOCKER_DIR/docker-compose.ssl.yml" "$dest/docker-compose.ssl.yml"
    cp "$DOCKER_DIR/Dockerfile"                  "$dest/"
    cp "$DOCKER_DIR/Dockerfile.identifier.mac"   "$dest/Dockerfile.identifier.mac"
    # Dockerfile.trainer은 Mac에서 네이티브 실행이므로 미포함
    cp "$DOCKER_DIR/.env.example"          "$dest/"
    cp "$ROOT/.dockerignore"               "$dest/"
    install -m 755 "$DOCKER_DIR/gen-cert.sh" "$dest/gen-cert.sh"

    # 소스 코드 복사 (trainer 포함 — 네이티브 실행용)
    info "소스 코드 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/studio/"     "$dest/studio/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/identifier/" "$dest/identifier/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/trainer/"    "$dest/trainer/"
    rsync -a "$ROOT/sql/"                               "$dest/sql/"
    cp "$ROOT/requirements.txt"            "$dest/"
    cp "$ROOT/requirements-identifier.txt" "$dest/"

    # 프론트엔드 소스 복사 (Docker 멀티스테이지 빌드에서 사용)
    info "프론트엔드 소스 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "${RSYNC_FRONTEND_EXCLUDES[@]}" "$ROOT/frontend/" "$dest/frontend/"

    # 빈 디렉토리 생성
    mkdir -p "$dest/data/mysql" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/hf-cache" "$dest/data/shared" \
             "$dest/data/finetune" \
             "$dest/data/models/efficientnet" "$dest/data/models/vlm" \
             "$dest/data/checkpoints/vlm" \
             "$dest/logs/studio" "$dest/logs/identifier"

    # Ollama Modelfile — VLM GGUF export 결과와 같은 위치에 배치
    cp "$DOCKER_DIR/ollama/Modelfile" "$dest/data/models/vlm/Modelfile"

    _write_dev_mac_scripts "$dest"

    info "Dev mac 패키지 완료: $dest"
    echo ""
}

_write_dev_mac_scripts() {
    local dest="$1"

    cat > "$dest/setup.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve] Mac 초기 설정 (Apple Silicon)"
echo "======================================"

echo "[1/5] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker Desktop이 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

echo "[2/5] Homebrew / Python 확인 중..."
if ! command -v python3 > /dev/null 2>&1; then
    echo "[오류] Python3이 설치되지 않았습니다. brew install python을 실행하세요."
    exit 1
fi
echo "      Python: $(python3 --version)"

echo "[3/5] 가상환경 및 Trainer 의존성 확인 중..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "      .venv 가상환경 생성 완료"
    .venv/bin/pip install --upgrade pip
    # MLX (vlm_only 모드) + EfficientNet (efficientnet 모드) 양쪽 의존성 설치
    .venv/bin/pip install mlx-lm mlx-vlm fastapi "uvicorn[standard]" pydantic-settings pyyaml psutil httpx
    .venv/bin/pip install torch==2.6.0 torchvision==0.21.0 timm Pillow
    echo "      의존성 설치 완료"
else
    echo "      .venv 존재 — 설치 건너뜀 (재설치: .venv 삭제 후 재실행)"
fi

echo "[4/5] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "      .env 파일이 생성되었습니다."
    echo ""
    echo " ★ 필수 수정 항목:"
    echo "   - OPENAI_API_KEY        (OpenAI Vision API 키)"
    echo "   - GEMINI_API_KEY        (Google Gemini API 키, 교차검증용)"
    echo "   - MYSQL_PASSWORD"
    echo ""
    echo "   .env 파일을 편집한 후 start.sh를 실행하세요."
    exit 0
else
    echo "      .env 파일 존재 확인"
fi

echo "[5/5] Docker 이미지 준비 중..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml build

echo ""
echo "======================================"
echo "초기 설정 완료. ./start.sh 로 서비스를 시작하세요."
echo "======================================"
EOF

    cat > "$dest/start.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve] Mac 서비스 시작 (Apple Silicon)"
echo ""

# 1. .env 로드 (TRAINER_BACKEND 등)
if [ -f ".env" ]; then
    set -o allexport; source .env; set +o allexport
fi

# 2. Ollama 네이티브 시작 (실행 중이면 종료 후 재시작)
if pgrep -x "ollama" > /dev/null 2>&1; then
    echo "[1/3] Ollama 종료 중..."
    pkill -x ollama
    sleep 1
fi
echo "[1/3] Ollama 시작 중..."
OLLAMA_NUM_CTX="${OLLAMA_NUM_CTX:-8192}" ollama serve > logs/ollama.log 2>&1 &
OLLAMA_PID=$!
echo "      PID: $OLLAMA_PID (logs/ollama.log)"
sleep 2

# Ollama 준비 대기 후 VLM 모델 pull (없을 경우)
_MODEL="${VLM_MODEL_NAME:-qwen3-vl:8b}"
for _i in $(seq 1 15); do
    ollama list > /dev/null 2>&1 && break
    sleep 1
done
if ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qF "$_MODEL"; then
    echo "      VLM 모델 존재: $_MODEL"
else
    echo "      VLM 모델 없음 — pull 시작: $_MODEL"
    ollama pull "$_MODEL"
fi

# 3. Trainer 네이티브 시작 — IDENTIFIER_MODE에 따라 백엔드 자동 결정
#    efficientnet → TRAINER_BACKEND=efficientnet (Mac/Linux/Windows 공통)
#    vlm_only → Mac: mlx
if [ "${IDENTIFIER_MODE}" = "efficientnet" ]; then
    _TRAINER_BACKEND=efficientnet
    _TRAINER_LABEL="EfficientNet"
else
    _TRAINER_BACKEND=mlx
    _TRAINER_LABEL="MLX (Qwen3-VL)"
fi

if pgrep -f "trainer.main:app" > /dev/null 2>&1; then
    echo "[2/3] Trainer 종료 중..."
    pkill -f "trainer.main:app"
    sleep 1
fi
echo "[2/3] Trainer (${_TRAINER_LABEL}) 시작 중..."
TRAINER_BACKEND=${_TRAINER_BACKEND} TRAINER_DATA_DIR=./data/finetune TRAINER_OUTPUT_DIR=./data/checkpoints/vlm \
    VLM_MODEL_DIR=./data/models/vlm EFFICIENTNET_MODEL_DIR=./data/models/efficientnet TRAINER_LOG_DIR=./logs/trainer \
    STUDIO_URL=http://localhost:8000 IDENTIFIER_URL=http://localhost:8001 \
    .venv/bin/uvicorn trainer.main:app --host 0.0.0.0 --port 8002 \
    > logs/trainer.log 2>&1 &
TRAINER_PID=$!
echo "      PID: $TRAINER_PID (logs/trainer.log)"
sleep 2

# 4. Docker 서비스 시작 (studio, identifier, celery, mysql, redis)
echo "[3/3] Docker 서비스 시작 중..."
SSL_COMPOSE=""
if [ -f "certs/cert.pem" ] && [ -f "certs/key.pem" ]; then
    SSL_COMPOSE="-f docker-compose.ssl.yml"
fi
PROTO="http"
[ -n "$SSL_COMPOSE" ] && PROTO="https"

docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml $SSL_COMPOSE down 2>/dev/null || true
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml $SSL_COMPOSE up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Studio        : ${PROTO}://localhost:8000"
echo "  Identifier    : ${PROTO}://localhost:8001"
echo "  Trainer (${_TRAINER_LABEL}) : http://localhost:8002  (네이티브 Apple Silicon)"
echo "  Ollama        : http://localhost:11434  (네이티브 Apple Silicon)"
echo ""
echo "로그 확인:"
echo "  Ollama  : tail -f logs/ollama.log"
echo "  Trainer : tail -f logs/trainer.log"
EOF

    cat > "$dest/stop.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

echo "[Reeve] Mac 서비스 중지 중..."

echo "[1/3] Docker 서비스 중지..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.mac.yml down

echo "[2/3] Trainer 중지..."
pkill -f "trainer.main:app" 2>/dev/null && echo "      Trainer 중지됨" || echo "      Trainer 실행 중 아님"

echo "[3/3] Ollama 중지..."
pkill -x "ollama" 2>/dev/null && echo "      Ollama 중지됨" || echo "      Ollama 실행 중 아님"

echo "완료."
EOF

    chmod +x "$dest/setup.sh" "$dest/start.sh" "$dest/stop.sh"
    mkdir -p "$dest/logs"
}

# ══════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════
TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    echo "사용법: $0 [target]"
    echo ""
    echo "  dev-linux     개발사 납품 — Linux 개발 환경 (GPU)"
    echo "  dev-windows   개발사 납품 — Windows 개발 환경 (GPU)"
    echo "  dev-mac       개발사 납품 — Mac 개발 환경 (Apple Silicon, 네이티브 Trainer)"
    echo "  prod-linux    고객사 납품 — Linux 운영 환경"
    echo "  prod-windows  고객사 납품 — Windows 운영 환경"
    echo "  all           전체 패키지 생성"
    exit 0
fi

case "$TARGET" in
    dev-linux)    package_dev linux ;;
    dev-windows)  package_dev windows ;;
    dev-mac)      package_dev_mac ;;
    prod-linux)   package_prod linux ;;
    prod-windows) package_prod windows ;;
    all)
        package_dev linux
        package_dev windows
        package_dev_mac
        package_prod linux
        package_prod windows
        ;;
    *) error "알 수 없는 target: $TARGET" ;;
esac

info "완료. deploy/ 폴더에서 각 패키지를 확인하세요."
