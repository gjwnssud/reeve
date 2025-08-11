#!/bin/bash

# Quick Start Script for Vehicle Dataset Generator
# 새로운 구조의 Flask 애플리케이션을 빠르게 실행

echo "🚗 Vehicle Dataset Generator - Quick Start"
echo "=========================================="

# Python 가상환경 활성화 확인
if [[ "$VIRTUAL_ENV" != "" ]]; then
    echo "✅ Virtual environment activated: $VIRTUAL_ENV"
else
    echo "⚠️ Virtual environment not detected. Activating..."
    source .venv/bin/activate 2>/dev/null || echo "❌ Please activate your virtual environment manually"
fi

# 환경 변수 설정
export FLASK_ENV=development
export PYTHONPATH=$PWD:$PYTHONPATH

echo "🔧 Environment: $FLASK_ENV"
echo "📂 Project Root: $PWD"

# Flask 애플리케이션 실행
echo "🚀 Starting Flask application..."
python run.py
