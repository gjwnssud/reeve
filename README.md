# Reeve - Vehicle Recognition System

> 차량 이미지 분석을 위한 로컬 LLM 기반 AI 시스템

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![OpenAI](https://img.shields.io/badge/API-OpenAI_GPT--4o--mini-orange.svg)](https://platform.openai.com/)

## 🎯 프로젝트 개요

**Reeve**는 차량 사진을 분석하여 제조사, 모델, 연식 정보를 추출하는 AI 시스템입니다. OpenAI API를 활용한 데이터셋 생성부터 로컬 LLM 파인튜닝까지, 완전한 차량 인식 솔루션을 제공합니다.

### 🌟 주요 특징

- 🔍 **정확한 차량 분석**: GPT-4o-mini 기반 차량 정보 추출
- 🛠️ **다양한 인터페이스**: Web, GUI, CLI 지원
- 📊 **구조화된 데이터**: JSON 형식의 표준화된 출력
- 🎨 **사용자 친화적**: 직관적인 웹 인터페이스
- 🚀 **확장 가능**: 로컬 LLM 파인튜닝 준비

## 📁 프로젝트 구조

```
reeve/
├── 📁 vehicle-dataset-generator/    # 차량 데이터셋 생성 도구
│   ├── 🐍 Python 기반 분석 엔진
│   ├── 🌐 웹 인터페이스 (Flask)
│   ├── 🖥️ GUI 인터페이스 (tkinter)
│   └── 💻 CLI 인터페이스
├── 📁 dataset/                      # 생성된 JSON 데이터셋
├── 📁 images_daytime/              # 차량 이미지 저장소
└── 📄 분류 데이터 (classificated_vehicle.json)
```

### 🔧 vehicle-dataset-generator

LLM 파인튜닝을 위한 핵심 데이터셋 생성 도구입니다.

**주요 기능:**
- 차량 이미지/텍스트 분석
- 브랜드, 모델, 연식 추출
- 배치 처리 지원
- 다국어 출력 (한글/영문)
- 웹/GUI/CLI 멀티 인터페이스

**기술 스택:**
- Python 3.8+, Flask, tkinter
- OpenAI GPT-4o-mini API
- JSON 데이터 포맷

## 🚀 빠른 시작

### 1. 환경 준비
```bash
# 저장소 클론
git clone https://github.com/gjwnssud/vehicle-recognition-system.git
cd reeve

# 데이터셋 생성기로 이동
cd vehicle-dataset-generator
```

### 2. 자동 실행 (추천)

**macOS/Linux:**
```bash
chmod +x run_macos.sh
./run_macos.sh
```

**Windows:**
```cmd
run_windows.bat
```

### 3. OpenAI API 키 설정
```bash
# .env 파일 생성
cp .env.example .env

# API 키 입력
OPENAI_API_KEY=your_api_key_here
```

## 📋 개발 로드맵

### ✅ Phase 1: 데이터 수집 도구 (완료)
- [x] ChatGPT API 기반 차량 정보 추출
- [x] 웹/GUI/CLI 인터페이스 구현
- [x] 배치 처리 및 데이터셋 관리
- [x] 다중 이미지 분석 지원

### 🔄 Phase 2: 데이터셋 구축 (진행중)
- [ ] 대량 이미지 데이터 수집
- [ ] 데이터 품질 검증 및 정제
- [ ] 한국 차량 분류 체계 적용
- [ ] 훈련/검증 데이터셋 분리

### 📋 Phase 3: 로컬 LLM 파인튜닝 (예정)
- [ ] 오픈소스 LLM 모델 선택
- [ ] 파인튜닝 파이프라인 구축
- [ ] 성능 평가 및 최적화
- [ ] 모델 경량화

### 🎯 Phase 4: API 서비스화 (목표)
- [ ] FastAPI/NestJS 기반 API 서버
- [ ] 모델 서빙 인프라 구축
- [ ] 도커 컨테이너화
- [ ] 프로덕션 배포

## 🗂️ 차량 분류 체계

한국 자동차 시장에 최적화된 분류 시스템을 제공합니다.

**국산차 브랜드:**
- 현대, 기아, 제네시스, 쉐보레(GM대우), 쌍용, 르노삼성

**수입차 브랜드:**
- 독일: BMW, 벤츠, 아우디, 폭스바겐, 포르쉐
- 일본: 도요타, 혼다, 닛산, 마쯔다, 렉서스
- 미국: 포드, GM, 크라이슬러, 테슬라
- 기타 유럽: 볼보, 재규어, 랜드로버 등

## 🛠️ 기술 스택

### 현재 (Phase 1)
- **Backend**: Python 3.8+, Flask
- **Frontend**: Vanilla JavaScript, HTML/CSS
- **AI/ML**: OpenAI GPT-4o-mini API
- **Data**: JSON, 한국차량분류체계

### 향후 (Phase 3-4)
- **Backend**: Java/NestJS (API 서버)
- **AI/ML**: Transformers, PyTorch, Hugging Face
- **Infrastructure**: Docker, FastAPI
- **Database**: PostgreSQL/MongoDB

## 📊 출력 데이터 형식

```json
{
  "id": "20250130_123456_001",
  "timestamp": "2025-01-30T12:34:56",
  "source_type": "image",
  "input": "car_image.jpg",
  "output": {
    "brand_kr": "현대",
    "brand_en": "Hyundai",
    "model_kr": "소나타",
    "model_en": "Sonata",
    "year": "2022",
    "year_info": "LED 헤드램프와 카스케이딩 그릴 디자인으로 7세대 후기형 추정",
    "confidence": 85
  }
}
```

## 🤝 기여 방법

1. **Issue 등록**: 버그 리포트나 기능 요청
2. **Fork & PR**: 코드 개선사항 제출
3. **데이터 제공**: 차량 이미지나 분류 정보 기여
4. **문서화**: README나 가이드 개선

## 📄 라이선스

이 프로젝트는 [MIT License](LICENSE) 하에 배포됩니다.

## 🔗 관련 링크

- **GitHub**: [vehicle-recognition-system](https://github.com/gjwnssud/vehicle-recognition-system)
- **OpenAI API**: [Platform Documentation](https://platform.openai.com/docs)
- **차량 데이터셋 생성기**: [vehicle-dataset-generator](./vehicle-dataset-generator/)

---

### 💡 개발자 노트

이 프로젝트는 **IntelliJ IDEA**와 **PyCharm**에서 최적화되어 개발되었습니다. IDE별 설정 파일들이 포함되어 있어 즉시 개발을 시작할 수 있습니다.

**🚗 차량 인식의 새로운 기준, Reeve와 함께하세요!**
