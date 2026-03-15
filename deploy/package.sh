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

    rm -rf "$dest"
    mkdir -p "$dest"

    # docker 파일 복사 (경로 패치 적용)
    patch_compose "$DOCKER_DIR/docker-compose.yml"     > "$dest/docker-compose.yml"
    patch_compose "$DOCKER_DIR/docker-compose.dev.yml" > "$dest/docker-compose.dev.yml"
    cp "$DOCKER_DIR/Dockerfile"            "$dest/"
    cp "$DOCKER_DIR/Dockerfile.identifier" "$dest/"
    cp "$DOCKER_DIR/.env.example"          "$dest/"

    # 소스 코드 복사
    info "소스 코드 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/studio/"     "$dest/studio/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/identifier/" "$dest/identifier/"
    rsync -a "$ROOT/sql/"                               "$dest/sql/"
    cp "$ROOT/requirements.txt"            "$dest/"
    cp "$ROOT/requirements-identifier.txt" "$dest/"

    # 빈 디렉토리 생성 (Docker 볼륨 마운트 대상)
    mkdir -p "$dest/data/mysql" "$dest/data/qdrant" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/hf-cache" "$dest/data/shared" \
             "$dest/data/finetune" "$dest/logs/studio" "$dest/logs/identifier" \
             "$dest/output"

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

echo "[Reeve Studio] Linux 초기 설정 (GPU)"
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
    echo "   - OPENAI_API_KEY"
    echo "   - MYSQL_ROOT_PASSWORD"
    echo "   - MYSQL_PASSWORD"
    echo ""
    echo "   .env 파일을 편집한 후 start.sh를 실행하세요."
    exit 0
else
    echo "      .env 파일 존재 확인"
fi

echo "[4/4] Docker 이미지 준비 중..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f docker-compose.dev.yml build

echo ""
echo "======================================"
echo "초기 설정 완료. ./start.sh 로 서비스를 시작하세요."
echo "======================================"
EOF

    cat > "$dest/start.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve Studio] Linux 서비스 시작 (GPU)"
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Studio        : http://localhost:8000"
echo "  Identifier    : http://localhost:8001"
echo "  LLaMA-Factory : http://localhost:7860"
echo "  Qdrant        : http://localhost:6333/dashboard"
echo "  Ollama        : http://localhost:11434  (NVIDIA GPU)"
EOF

    cat > "$dest/stop.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

echo "[Reeve Studio] 서비스 중지 중..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml down

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
        echo    - OPENAI_API_KEY
        echo    - MYSQL_ROOT_PASSWORD
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
docker compose -f docker-compose.yml -f docker-compose.dev.yml pull --ignore-buildable
docker compose -f docker-compose.yml -f docker-compose.dev.yml build

echo.
echo ======================================
echo 초기 설정 완료. start.bat으로 서비스를 시작하세요.
echo ======================================
pause
EOF

    cat > "$dest/start.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Studio] Windows 서비스 시작 (GPU)...
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

if errorlevel 1 (
    echo [오류] 서비스 시작 실패. 로그를 확인하세요:
    echo        docker compose -f docker-compose.yml -f docker-compose.dev.yml logs
    pause
    exit /b 1
)

echo.
echo 서비스가 시작되었습니다:
echo   Studio        : http://localhost:8000
echo   Identifier    : http://localhost:8001
echo   LLaMA-Factory : http://localhost:7860
echo   Qdrant        : http://localhost:6333/dashboard
EOF

    cat > "$dest/stop.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Studio] 서비스 중지 중...
docker compose -f docker-compose.yml -f docker-compose.dev.yml down

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
    mkdir -p "$dest/snapshots" "$dest/models" \
             "$dest/data/qdrant" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/shared" \
             "$dest/logs"

    # Dockerfile.identifier → Dockerfile (standalone 빌드용)
    cp "$DOCKER_DIR/Dockerfile.identifier" "$dest/Dockerfile"

    # prod docker-compose.yml 생성 (standalone, pre-built image 기반)
    _write_prod_compose "$dest"

    # .env.example (Identifier 전용)
    _write_prod_env_example "$dest"

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

    # Qdrant 스냅샷
    set +e
    if curl -s http://localhost:6333/healthz > /dev/null 2>&1; then
        info "Qdrant 스냅샷 생성 중..."
        local snapshot_resp
        snapshot_resp=$(curl -s -X POST \
            "http://localhost:6333/collections/training_images/snapshots" 2>/dev/null)
        local snapshot_name
        snapshot_name=$(echo "$snapshot_resp" | python3 -c \
            "import sys,json; d=json.load(sys.stdin); print(d['result']['name'])" 2>/dev/null)
        if [ -n "$snapshot_name" ]; then
            curl -s -o "$dest/snapshots/training_images.snapshot" \
                "http://localhost:6333/collections/training_images/snapshots/$snapshot_name"
            if [ $? -eq 0 ] && [ -s "$dest/snapshots/training_images.snapshot" ]; then
                info "스냅샷 저장 완료: snapshots/training_images.snapshot"
            else
                rm -f "$dest/snapshots/training_images.snapshot"
                warn "스냅샷 다운로드 실패. snapshots/ 폴더에 직접 넣으세요."
            fi
        else
            warn "Qdrant 스냅샷 생성 실패."
            warn "  Studio에서 데이터 동기화 후 다시 실행하거나 snapshots/ 에 직접 넣으세요."
            [ -n "$snapshot_resp" ] && warn "  Qdrant 응답: $snapshot_resp"
        fi
    else
        warn "Qdrant가 실행되지 않아 스냅샷을 건너뜁니다."
        warn "서비스 실행 후 다시 packaging하거나 snapshots/ 에 직접 넣으세요."
    fi
    set -e

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
# 포함 서비스: qdrant + redis + identifier + celery-worker + ollama
# 이미지 빌드: docker build -t reeve-identifier:latest -f Dockerfile .
# ──────────────────────────────────────────

services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: reeve-qdrant
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - ./data/qdrant:/qdrant/storage
    environment:
      - QDRANT__SERVICE__GRPC_PORT=6334
      - QDRANT__STORAGE__ON_DISK_PAYLOAD=true
    networks:
      - reeve-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
        reservations:
          cpus: '0.25'
          memory: 256M

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
    environment:
      - QDRANT_HOST=qdrant
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
      - EMBEDDING_DEVICE=cuda
    depends_on:
      qdrant:
        condition: service_started
      redis:
        condition: service_started
    networks:
      - reeve-network
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 1G

  celery-worker:
    image: reeve-identifier:latest
    container_name: reeve-celery-worker
    env_file:
      - .env
    command: /app/identifier/start_worker.sh
    volumes:
      - ./logs:/app/logs
      - ./data/shared:/app/shared
    environment:
      - QDRANT_HOST=qdrant
      - REDIS_HOST=redis
      - OLLAMA_BASE_URL=http://ollama:11434
      - EMBEDDING_DEVICE=cuda
    depends_on:
      redis:
        condition: service_started
      qdrant:
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
          cpus: '2.0'
          memory: 2G

  ollama:
    image: ollama/ollama:latest
    container_name: reeve-ollama
    ports:
      - "11434:11434"
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

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Embedding
EMBEDDING_DEVICE=cuda

# 판별 모드: clip_only | visual_rag | vlm_only
IDENTIFIER_MODE=visual_rag

# VLM (Ollama)
OLLAMA_BASE_URL=http://ollama:11434
VLM_MODEL_NAME=vehicle-vlm-v1
VLM_TIMEOUT=30
VLM_MAX_CANDIDATES=5
VLM_FALLBACK_TO_CLIP=true
VLM_BATCH_CONCURRENCY=2

# 판별 파라미터
IDENTIFIER_PORT=8001
IDENTIFIER_TOP_K=10
IDENTIFIER_CONFIDENCE_THRESHOLD=0.80
IDENTIFIER_MIN_SIMILARITY=0.70
IDENTIFIER_VOTE_THRESHOLD=3
IDENTIFIER_VOTE_CONCENTRATION_THRESHOLD=0.3
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

echo "[1/5] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker가 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

echo "[2/5] NVIDIA GPU 확인 중..."
if ! nvidia-smi > /dev/null 2>&1; then
    echo "[오류] NVIDIA GPU를 감지하지 못했습니다."
    echo "       nvidia-container-toolkit이 설치되어 있는지 확인하세요."
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | while read line; do
    echo "      GPU: $line"
done

echo "[3/5] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "      .env 파일이 생성되었습니다. 필요시 내용을 수정하세요."
else
    echo "      .env 파일 존재 확인"
fi

echo "[4/5] Identifier 이미지 확인 중..."
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

echo "[5/5] 서비스 시작 중..."
docker compose up -d

echo ""
echo "Qdrant 준비 대기 중..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then
        echo "Qdrant 준비 완료"
        break
    fi
    sleep 2
done

set +e
SNAPSHOT_FILE=$(ls snapshots/training_images*.snapshot 2>/dev/null | head -1)
if [ -n "$SNAPSHOT_FILE" ]; then
    echo ""
    echo "Qdrant 스냅샷 복원 중: $SNAPSHOT_FILE"
    if ! curl -sf http://localhost:6333/collections/training_images > /dev/null 2>&1; then
        curl -s -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" \
            -H "Content-Type:multipart/form-data" \
            -F "snapshot=@$SNAPSHOT_FILE"
        [ $? -eq 0 ] && echo "스냅샷 복원 완료" || echo "[경고] 스냅샷 복원 실패. setup.sh를 다시 실행하세요."
    else
        echo "training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다."
    fi
else
    echo ""
    echo "[정보] snapshots/ 폴더에 스냅샷 파일이 없습니다."
    echo "       Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.sh를 다시 실행하세요."
fi
set -e

echo ""
echo "Ollama 준비 대기 중..."
for i in $(seq 1 30); do
    if docker exec reeve-ollama ollama list > /dev/null 2>&1; then
        break
    fi
    sleep 2
done

MODEL_NAME=$(grep VLM_MODEL_NAME .env | cut -d= -f2 | tr -d ' ')
MODEL_NAME="${MODEL_NAME:-vehicle-vlm-v1}"

if docker exec reeve-ollama ollama list | grep -q "$MODEL_NAME"; then
    echo "Ollama 모델 '$MODEL_NAME' 이미 존재합니다."
else
    GGUF_FILE=$(ls models/*.gguf 2>/dev/null | head -1)
    MODELFILE="models/Modelfile"
    if [ -n "$GGUF_FILE" ] && [ -f "$MODELFILE" ]; then
        echo "Ollama 모델 등록 중: $MODEL_NAME"
        docker cp "$GGUF_FILE" reeve-ollama:/root/$(basename "$GGUF_FILE")
        docker cp "$MODELFILE" reeve-ollama:/root/Modelfile
        docker exec reeve-ollama ollama create "$MODEL_NAME" -f /root/Modelfile
        echo "모델 등록 완료: $MODEL_NAME"
    else
        echo "[정보] models/ 폴더에 .gguf 파일 또는 Modelfile이 없습니다."
        echo "       파인튜닝된 모델 파일을 models/ 폴더에 넣고 setup.sh를 다시 실행하세요."
        echo "       (models/vehicle-vlm-v1.gguf + models/Modelfile)"
    fi
fi

echo ""
echo "======================================"
echo "설정 완료."
echo "  Identifier API  : http://localhost:8001"
echo "  Identifier Docs : http://localhost:8001/docs"
echo "  Qdrant Dashboard: http://localhost:6333/dashboard"
echo "======================================"
EOF

    cat > "$dest/start.sh" << 'EOF'
#!/bin/bash
set -e
cd "$(dirname "$0")"

echo "[Reeve Identifier] 서비스 시작 (GPU)"
docker compose up -d

echo ""
echo "서비스가 시작되었습니다:"
echo "  Identifier API  : http://localhost:8001"
echo "  Identifier Docs : http://localhost:8001/docs"
echo "  Qdrant Dashboard: http://localhost:6333/dashboard"
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

echo [1/5] Docker Desktop 확인 중...
docker info > nul 2>&1
if errorlevel 1 (
    echo [오류] Docker Desktop이 실행되지 않았습니다.
    echo        Docker Desktop을 시작한 후 다시 실행하세요.
    pause
    exit /b 1
)
echo       OK

echo [2/5] NVIDIA GPU 확인 중...
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

echo [3/5] 환경변수 파일 확인 중...
if not exist ".env" (
    copy ".env.example" ".env" > nul
    echo       .env 파일이 생성되었습니다. 필요시 내용을 수정하세요.
) else (
    echo       .env 파일 존재 확인
)

echo [4/5] Identifier 이미지 확인 중...
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

echo [5/5] 서비스 시작 중...
docker compose up -d
if errorlevel 1 (
    echo [오류] 서비스 시작 실패.
    pause
    exit /b 1
)

echo.
echo Qdrant 준비 대기 중...
:QDRANT_WAIT
timeout /t 2 /nobreak > nul
curl -s http://localhost:6333/healthz > nul 2>&1
if errorlevel 1 goto QDRANT_WAIT
echo Qdrant 준비 완료

set SNAPSHOT_FILE=
for %%f in (snapshots\training_images*.snapshot) do set SNAPSHOT_FILE=%%f

if defined SNAPSHOT_FILE (
    echo.
    echo Qdrant 스냅샷 복원 중: %SNAPSHOT_FILE%
    curl -s http://localhost:6333/collections/training_images > nul 2>&1
    if errorlevel 1 (
        curl -s -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" ^
            -H "Content-Type:multipart/form-data" ^
            -F "snapshot=@%SNAPSHOT_FILE%"
        if errorlevel 1 (
            echo [경고] 스냅샷 복원 실패. setup.bat을 다시 실행하세요.
        ) else (
            echo 스냅샷 복원 완료
        )
    ) else (
        echo training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다.
    )
) else (
    echo.
    echo [정보] snapshots\ 폴더에 스냅샷 파일이 없습니다.
    echo        Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.bat을 다시 실행하세요.
)

echo.
echo Ollama 준비 대기 중...
:OLLAMA_WAIT
timeout /t 2 /nobreak > nul
docker exec reeve-ollama ollama list > nul 2>&1
if errorlevel 1 goto OLLAMA_WAIT

set MODEL_NAME=vehicle-vlm-v1
for /f "tokens=2 delims==" %%a in ('findstr /i "^VLM_MODEL_NAME" .env 2^>nul') do set MODEL_NAME=%%a

docker exec reeve-ollama ollama list | findstr /i "%MODEL_NAME%" > nul 2>&1
if not errorlevel 1 (
    echo Ollama 모델 '%MODEL_NAME%' 이미 존재합니다.
) else (
    set GGUF_FILE=
    for %%f in (models\*.gguf) do set GGUF_FILE=%%f
    if defined GGUF_FILE (
        if exist "models\Modelfile" (
            echo Ollama 모델 등록 중: %MODEL_NAME%
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
        echo [정보] models\ 폴더에 .gguf 파일이 없습니다.
        echo        파인튜닝된 모델 파일을 models\ 폴더에 넣고 setup.bat을 다시 실행하세요.
        echo        (models\vehicle-vlm-v1.gguf + models\Modelfile)
    )
)

echo.
echo ======================================
echo 설정 완료.
echo   Identifier API  : http://localhost:8001
echo   Identifier Docs : http://localhost:8001/docs
echo   Qdrant Dashboard: http://localhost:6333/dashboard
echo ======================================
pause
EOF

    cat > "$dest/start.bat" << 'EOF'
@echo off
cd /d "%~dp0"

echo [Reeve Identifier] 서비스 시작 (GPU)...
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
echo   Qdrant Dashboard: http://localhost:6333/dashboard
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
# 메인
# ══════════════════════════════════════════════════════════
TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    echo "사용법: $0 [target]"
    echo ""
    echo "  dev-linux     개발사 납품 — Linux 개발 환경 (GPU)"
    echo "  dev-windows   개발사 납품 — Windows 개발 환경 (GPU)"
    echo "  prod-linux    고객사 납품 — Linux 운영 환경"
    echo "  prod-windows  고객사 납품 — Windows 운영 환경"
    echo "  all           전체 패키지 생성"
    exit 0
fi

case "$TARGET" in
    dev-linux)    package_dev linux ;;
    dev-windows)  package_dev windows ;;
    prod-linux)   package_prod linux ;;
    prod-windows) package_prod windows ;;
    all)
        package_dev linux
        package_dev windows
        package_prod linux
        package_prod windows
        ;;
    *) error "알 수 없는 target: $TARGET" ;;
esac

info "완료. deploy/ 폴더에서 각 패키지를 확인하세요."
