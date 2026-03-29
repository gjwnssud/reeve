# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
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

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# EfficientNet-B3 모델 사전 다운로드 (빌드 시 캐싱)
RUN python -c "import timm; timm.create_model('efficientnet_b3', pretrained=True, num_classes=0)"

# YOLO26n 모델 사전 다운로드 (빌드 시 캐싱)
RUN python -c "from ultralytics import YOLO; YOLO('yolo26m.pt')"

# Copy application code
COPY studio/ ./studio/
COPY data/ ./data/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "studio.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
