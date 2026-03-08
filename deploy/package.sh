#!/bin/bash
# ══════════════════════════════════════════════════════════
# Reeve 배포 패키지 생성 스크립트 (Mac/Linux)
#
# 사용법:
#   ./package.sh [target]
#
# target:
#   studio-mac        개발사 납품 — Mac 개발 환경
#   studio-linux      개발사 납품 — Linux 개발 환경
#   studio-windows    개발사 납품 — Windows 개발 환경 (파일 생성만, 실행은 Windows에서)
#   identifier-linux  고객사 납품 — Linux 운영 환경
#   identifier-windows 고객사 납품 — Windows 운영 환경 (파일 생성만, 실행은 Windows에서)
#   all               전체 패키지 생성
# ══════════════════════════════════════════════════════════
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"  # deploy/
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"          # 프로젝트 루트
DOCKER_DIR="$ROOT/docker"

# ── 컬러 출력 ───────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── 소스 복사 (공통) ─────────────────────────
# rsync 제외 패턴: 캐시, 런타임 파일, 이미 gitignore 된 항목
RSYNC_EXCLUDES=(
    --exclude='__pycache__/'
    --exclude='*.pyc'
    --exclude='*.pyo'
    --exclude='.DS_Store'
    --exclude='*.egg-info/'
    --exclude='.pytest_cache/'
)

copy_source() {
    local dest="$1"
    info "소스 코드 복사 중..."
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/studio/"     "$dest/studio/"
    rsync -a "${RSYNC_EXCLUDES[@]}" "$ROOT/identifier/" "$dest/identifier/"
    rsync -a "$ROOT/sql/"                               "$dest/sql/"
    cp "$ROOT/requirements.txt"            "$dest/"
    cp "$ROOT/requirements-identifier.txt" "$dest/"
    cp "$ROOT/.env.example"                "$dest/"
}

# ── Studio 패키지 생성 ───────────────────────
package_studio() {
    local os="$1"   # mac | linux | windows
    local dest="$SCRIPT_DIR/studio-$os"

    info "===== Studio $os 패키지 생성 시작 ====="

    rm -rf "$dest"
    mkdir -p "$dest/docker/studio/$os"

    # docker 파일 복사
    cp "$DOCKER_DIR/docker-compose.yml"           "$dest/docker/"
    cp "$DOCKER_DIR/Dockerfile"                   "$dest/docker/"
    cp "$DOCKER_DIR/Dockerfile.identifier"        "$dest/docker/"

    # OS별 override + 스크립트 복사
    cp "$DOCKER_DIR/studio/$os/"* "$dest/docker/studio/$os/"

    # 소스 복사
    copy_source "$dest"

    # 빈 디렉토리 생성 (Docker 볼륨 마운트 대상)
    mkdir -p "$dest/data/mysql" "$dest/data/qdrant" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/hf-cache" "$dest/data/shared" \
             "$dest/data/finetune" "$dest/logs/studio" "$dest/logs/identifier" \
             "$dest/output"

    info "Studio $os 패키지 완료: $dest"
    echo ""
}

# ── Identifier 패키지 생성 ───────────────────
package_identifier() {
    local os="$1"   # linux | windows
    local dest="$SCRIPT_DIR/identifier-$os"

    info "===== Identifier $os 패키지 생성 시작 ====="

    rm -rf "$dest"
    mkdir -p "$dest/snapshots" "$dest/models" \
             "$dest/data/qdrant" "$dest/data/redis" \
             "$dest/data/ollama" "$dest/data/shared" \
             "$dest/logs"

    # docker 파일 + 스크립트 복사
    cp "$DOCKER_DIR/identifier/$os/docker-compose.yml" "$dest/"
    cp "$DOCKER_DIR/identifier/$os/.env.example"       "$dest/"
    if [ "$os" = "linux" ]; then
        cp "$DOCKER_DIR/identifier/$os/setup.sh"  "$dest/"
        cp "$DOCKER_DIR/identifier/$os/start.sh"  "$dest/"
        cp "$DOCKER_DIR/identifier/$os/stop.sh"   "$dest/"
        chmod +x "$dest/"*.sh
    else
        # windows: .bat 파일
        cp "$DOCKER_DIR/identifier/$os/setup.bat" "$dest/"
        cp "$DOCKER_DIR/identifier/$os/start.bat" "$dest/"
        cp "$DOCKER_DIR/identifier/$os/stop.bat"  "$dest/"
    fi

    # ── Identifier Docker 이미지 빌드 + 저장 ──
    info "Identifier Docker 이미지 빌드 중..."
    cd "$ROOT"
    docker build -t reeve-identifier:latest -f docker/Dockerfile.identifier . \
        || error "Docker 이미지 빌드 실패"

    info "이미지 저장 중 (시간이 걸릴 수 있습니다)..."
    docker save reeve-identifier:latest | gzip > "$dest/reeve-identifier-latest.tar.gz"
    local img_size
    img_size=$(du -sh "$dest/reeve-identifier-latest.tar.gz" | cut -f1)
    info "이미지 저장 완료: reeve-identifier-latest.tar.gz ($img_size)"

    # ── Qdrant 스냅샷 내보내기 ────────────────
    if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then
        info "Qdrant 스냅샷 생성 중..."
        local snapshot_resp
        snapshot_resp=$(curl -sf -X POST \
            "http://localhost:6333/collections/training_images/snapshots" 2>/dev/null)
        local snapshot_name
        snapshot_name=$(echo "$snapshot_resp" | python3 -c \
            "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null)
        if [ -n "$snapshot_name" ]; then
            curl -sf -o "$dest/snapshots/training_images.snapshot" \
                "http://localhost:6333/collections/training_images/snapshots/$snapshot_name"
            info "스냅샷 저장 완료: snapshots/training_images.snapshot"
        else
            warn "Qdrant 스냅샷 생성 실패 (training_images 컬렉션이 없을 수 있습니다)"
            warn "나중에 snapshots/ 폴더에 직접 넣으세요."
        fi
    else
        warn "Qdrant가 실행되지 않아 스냅샷을 건너뜁니다."
        warn "서비스 실행 후 다시 packaging하거나 snapshots/ 에 직접 넣으세요."
    fi

    # ── Ollama 모델 복사 ──────────────────────
    local ollama_src="$ROOT/data/ollama"
    if [ -d "$ollama_src" ] && [ -n "$(ls -A "$ollama_src" 2>/dev/null)" ]; then
        info "Ollama 모델 복사 중..."
        cp -r "$ollama_src/." "$dest/data/ollama/"
        info "Ollama 모델 복사 완료"
    else
        warn "data/ollama 가 비어있습니다."
        warn "파인튜닝 완료 후 다시 packaging하거나 models/ 에 GGUF + Modelfile을 직접 넣으세요."
    fi

    info "Identifier $os 패키지 완료: $dest"
    echo ""
}

# ── 메인 ─────────────────────────────────────
TARGET="${1:-}"

if [ -z "$TARGET" ]; then
    echo "사용법: $0 [target]"
    echo ""
    echo "  studio-mac          개발사 납품 — Mac 개발 환경"
    echo "  studio-linux        개발사 납품 — Linux 개발 환경"
    echo "  studio-windows      개발사 납품 — Windows 개발 환경"
    echo "  identifier-linux    고객사 납품 — Linux 운영 환경"
    echo "  identifier-windows  고객사 납품 — Windows 운영 환경"
    echo "  all                 전체 패키지 생성"
    exit 0
fi

case "$TARGET" in
    studio-mac)        package_studio mac ;;
    studio-linux)      package_studio linux ;;
    studio-windows)    package_studio windows ;;
    identifier-linux)  package_identifier linux ;;
    identifier-windows) package_identifier windows ;;
    all)
        package_studio mac
        package_studio linux
        package_studio windows
        package_identifier linux
        package_identifier windows
        ;;
    *) error "알 수 없는 target: $TARGET" ;;
esac

info "완료. deploy/ 폴더에서 각 패키지를 확인하세요."
