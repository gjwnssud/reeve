# ─── Stage 1: Frontend Build ───────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

RUN npm install -g pnpm@9.15.0 --quiet

WORKDIR /workspace

# Install dependencies (separate layer for caching — invalidated only on lockfile change)
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./frontend/
COPY frontend/packages/config/package.json   ./frontend/packages/config/
COPY frontend/packages/shared/package.json   ./frontend/packages/shared/
COPY frontend/packages/ui/package.json       ./frontend/packages/ui/
COPY frontend/apps/studio/package.json       ./frontend/apps/studio/

RUN cd frontend && pnpm install --frozen-lockfile

# Build — output goes to /workspace/studio/static/ (vite outDir: ../../../studio/static)
COPY frontend/ ./frontend/
RUN cd frontend/apps/studio && pnpm build

# ─── Stage 2: Python Runtime ───────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    cmake \
    libopenblas-dev \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# EfficientNetV2-M 모델 사전 다운로드 (빌드 시 캐싱)
RUN python -c "import timm; timm.create_model('tf_efficientnetv2_m.in21k_ft_in1k', pretrained=True, num_classes=0)"

# YOLO26m 모델 사전 다운로드 (빌드 시 캐싱)
RUN python -c "from ultralytics import YOLO; YOLO('yolo26m.pt')"

COPY studio/ ./studio/
COPY --from=frontend-builder /workspace/static/ ./static/

RUN sed -i 's/\r$//' /app/studio/start.sh && chmod +x /app/studio/start.sh

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["/app/studio/start.sh"]
