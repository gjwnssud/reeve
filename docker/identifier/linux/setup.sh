#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
# 실행 위치: docker/identifier/linux/

echo "[Reeve Identifier] Linux 초기 설정"
echo "======================================"

# ── 1. Docker 확인 ───────────────────────────
echo "[1/5] Docker 확인 중..."
if ! docker info > /dev/null 2>&1; then
    echo "[오류] Docker가 실행되지 않았습니다."
    exit 1
fi
echo "      OK"

# ── 2. NVIDIA GPU 확인 ───────────────────────
echo "[2/5] NVIDIA GPU 확인 중..."
if ! nvidia-smi > /dev/null 2>&1; then
    echo "[오류] NVIDIA GPU를 감지하지 못했습니다."
    echo "       nvidia-container-toolkit이 설치되어 있는지 확인하세요."
    exit 1
fi
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | while read line; do
    echo "      GPU: $line"
done

# ── 3. .env 파일 생성 ────────────────────────
echo "[3/5] 환경변수 파일 확인 중..."
if [ ! -f ".env" ]; then
    cp ".env.example" ".env"
    echo "      .env 파일이 생성되었습니다. 필요시 내용을 수정하세요."
else
    echo "      .env 파일 존재 확인"
fi

# ── 4. Identifier 이미지 로드 ────────────────
echo "[4/5] Identifier 이미지 확인 중..."
if ! docker image inspect reeve-identifier:latest > /dev/null 2>&1; then
    # tar.gz 파일이 있으면 로드
    IMAGE_TAR=$(ls reeve-identifier-*.tar.gz 2>/dev/null | head -1)
    if [ -n "$IMAGE_TAR" ]; then
        echo "      이미지 로드 중: $IMAGE_TAR"
        docker load < "$IMAGE_TAR"
    else
        echo "[오류] reeve-identifier:latest 이미지를 찾을 수 없습니다."
        echo "       reeve-identifier-*.tar.gz 파일을 이 디렉토리에 넣거나"
        echo "       docker pull 명령으로 이미지를 받으세요."
        exit 1
    fi
else
    echo "      reeve-identifier:latest 확인"
fi

# ── 5. 서비스 시작 ───────────────────────────
echo "[5/5] 서비스 시작 중..."
docker compose up -d

# ── Qdrant 준비 대기 ─────────────────────────
echo ""
echo "Qdrant 준비 대기 중..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:6333/healthz > /dev/null 2>&1; then
        echo "Qdrant 준비 완료"
        break
    fi
    sleep 2
done

# ── Qdrant 스냅샷 복원 ───────────────────────
SNAPSHOT_FILE=$(ls snapshots/training_images*.snapshot 2>/dev/null | head -1)
if [ -n "$SNAPSHOT_FILE" ]; then
    echo ""
    echo "Qdrant 스냅샷 복원 중: $SNAPSHOT_FILE"
    # 기존 컬렉션이 없을 경우에만 복원
    if ! curl -sf http://localhost:6333/collections/training_images > /dev/null 2>&1; then
        curl -sf -X POST "http://localhost:6333/collections/training_images/snapshots/upload?priority=snapshot" \
            -H "Content-Type:multipart/form-data" \
            -F "snapshot=@$SNAPSHOT_FILE"
        echo "스냅샷 복원 완료"
    else
        echo "training_images 컬렉션이 이미 존재합니다. 복원을 건너뜁니다."
    fi
else
    echo ""
    echo "[정보] snapshots/ 폴더에 스냅샷 파일이 없습니다."
    echo "       Studio에서 스냅샷을 내보낸 후 이 폴더에 넣고 setup.sh를 다시 실행하세요."
fi

# ── Ollama 모델 로드 ─────────────────────────
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
echo "  Identifier API : http://localhost:8001"
echo "  Identifier Docs: http://localhost:8001/docs"
echo "  Qdrant Dashboard: http://localhost:6333/dashboard"
echo "======================================"
