# 🚗 Vehicle Dataset Generator

OpenAI GPT를 활용한 AI 기반 차량 정보 추출 및 데이터셋 생성 시스템

## 📋 개요

차량 이미지와 텍스트 설명을 분석하여 제조사, 모델 정보를 자동으로 추출하고 구조화된 JSON 데이터셋을 생성하는 Python 애플리케이션입니다.

## ✨ 주요 기능

- 🖼️ **이미지 분석**: 차량 사진에서 브랜드/모델 자동 인식
- 📝 **텍스트 분석**: 차량 설명 텍스트에서 정보 추출
- 🌐 **웹 인터페이스**: 브라우저 기반 직관적 UI (포트 4000)
- 📊 **실시간 통계**: 데이터셋 현황 및 분석 결과 확인

## 🏗️ 프로젝트 구조

```
vehicle-dataset-generator/
├── 🚀 run_macos.sh          # macOS/Linux 실행 스크립트
├── 🚀 run_windows.bat       # Windows 실행 스크립트
├── 📖 QUICK_START.md        # 상세 시작 가이드
├── ⚙️ config.py             # 설정 관리
├── 🎯 run.py                # 메인 실행 파일
├── 📦 requirements.txt      # Python 패키지 의존성
├── 🔐 .env.example          # 환경변수 템플릿
├── 📁 app/                  # 웹 애플리케이션
├── 📁 src/                  # 핵심 로직
├── 📁 uploads/              # 업로드된 파일 임시 저장
└── 🤖 yolov8n.pt           # YOLO 모델 파일
```

## ⚡ 빠른 시작

### 🚀 자동 설치 & 실행

**macOS/Linux:**
```bash
chmod +x start.sh
./start.sh
```

**Windows:**
```cmd
start.bat
```

스크립트 실행 후 자동으로 웹 브라우저에서 `http://localhost:4000`이 열립니다.

### 📋 사전 요구사항

1. **Python 3.8+** 설치
2. **OpenAI API 키** 발급 ([platform.openai.com](https://platform.openai.com))
3. **인터넷 연결** (API 호출용)

## 🎯 사용법

### 🌐 웹 인터페이스

```bash
# 실행 후 브라우저에서 접속
http://localhost:4000
```

**주요 기능:**
- 드래그 앤 드롭 이미지 업로드
- 실시간 분석 결과 표시
- 텍스트 분석 모드
- 데이터셋 관리 및 통계

## 📊 출력 형식

### JSON 데이터셋 구조
```json
{
  "id": "20250130_123456_001",
  "timestamp": "2025-01-30T12:34:56",
  "source_type": "image",
  "input": "car_photo.jpg",
  "output": {
    "brand_kr": "현대",
    "brand_en": "Hyundai",
    "model_kr": "소나타", 
    "model_en": "Sonata",
    "confidence": 85
  },
  "metadata": {
    "has_error": false,
    "processing_time": 2.3
  }
}
```

### 저장 위치
```
../../dataset/
├── vehicle_dataset_001.json
├── vehicle_dataset_002.json
└── ...
```

## ⚙️ 설정

### 환경변수 (.env)
```bash
# OpenAI 설정
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_MODEL=gpt-4o-mini

# 경로 설정
IMAGE_DIR=../../images_daytime
DATASET_DIR=../../dataset

# 웹서버 설정 (선택)
WEB_PORT=4000
DEBUG_MODE=false
```

## 🛠️ 기술 스택

| 구분 | 기술 |
|------|------|
| **AI/ML** | OpenAI GPT-4o-mini |
| **웹** | Flask, HTML/CSS/JS |
| **이미지 처리** | Pillow (PIL) |
| **HTTP** | Requests |
| **데이터** | JSON, Python-dotenv |

## 🔧 개발 환경 설정

### 수동 설치
```bash
# 1. 가상환경 생성
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env 파일에서 API 키 설정

# 4. 실행
python run.py
```

## 📈 성능 최적화

- **배치 처리**: 웹 인터페이스에서 다중 이미지 업로드 지원
- **캐싱**: 처리 결과 자동 저장 및 중복 방지
- **비동기 처리**: Flask 기반 비동기 이미지 분석

## 🧪 테스트

```bash
# 웹 서버 시작 테스트
python run.py

# API 연결 테스트  
python -c "from src.analysis_engine import test_connection; test_connection()"
```

## 🚨 문제 해결

### 자주 발생하는 오류

**1. API 키 오류**
```bash
# .env 파일 확인
cat .env | grep OPENAI_API_KEY
# sk-로 시작하는지 확인
```

**2. 패키지 설치 실패**
```bash
# pip 업그레이드
python -m pip install --upgrade pip
# 개별 설치
pip install openai python-dotenv pillow flask
```

**3. 포트 충돌 (웹 모드)**
```bash
# 포트 사용 확인
lsof -i :4000  # macOS/Linux
netstat -an | findstr :4000  # Windows
```

## 📚 관련 문서

- [상세 시작 가이드](./QUICK_START.md)
- [메인 프로젝트 문서](../README.md)
- [OpenAI API 문서](https://platform.openai.com/docs)

## 🔄 업데이트

```bash
git pull origin main
pip install -r requirements.txt --upgrade
```

## 💡 사용 팁

### 이미지 분석 최적화
- **고해상도** 이미지 사용
- **정면/측면** 각도에서 촬영
- **헤드램프와 그릴** 영역이 명확한 사진
- **밝은 조명** 환경에서 촬영

### 텍스트 분석 팁
- **브랜드명과 모델명** 정확히 기재
- **LED 헤드램프, 그릴 디자인** 등 세부 특징 포함

## ⚠️ 주의사항

- 💰 OpenAI API 사용료 발생
- 🌐 인터넷 연결 필수
- 🔒 API 키 보안 유지 (.env 파일 공유 금지)
- 📊 신뢰도 낮은 결과는 수동 검증 권장

---

**효율적인 차량 데이터셋 생성을 시작하세요! 🚀**