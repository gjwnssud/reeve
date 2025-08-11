# 🚗 Reeve - Vehicle Recognition System

AI 기반 차량 인식 및 데이터셋 생성 시스템

## 📋 프로젝트 개요

Reeve는 차량 이미지와 텍스트 정보를 분석하여 차량의 제조사, 모델을 자동으로 인식하고 구조화된 데이터셋을 생성하는 시스템입니다.

## 🏗️ 프로젝트 구조

```
reeve/
├── 📁 vehicle-dataset-generator/   # Python 기반 차량 데이터셋 생성기
├── 📁 vehicle-category-generator/  # Java 기반 차량 분류 데이터 처리기
├── 📁 dataset/                     # 생성된 차량 데이터셋 저장소
├── 📁 images_daytime/             # 차량 이미지 데이터 (용량으로 인해 .gitignore)
└── 📁 temp/                       # 임시 파일 저장소
```

## 🛠️ 서브 프로젝트

### 1. [Vehicle Dataset Generator](./vehicle-dataset-generator/)
- **언어**: Python 3.8+
- **주요 기능**: 
  - OpenAI GPT를 활용한 차량 이미지/텍스트 분석
  - 웹 인터페이스 제공
  - 실시간 데이터셋 생성 및 관리
- **실행**: `./vehicle-dataset-generator/run_macos.sh` (macOS/Linux)

### 2. [Vehicle Category Generator](./vehicle-category-generator/)
- **언어**: Java 17+
- **주요 기능**:
  - 차량 분류 데이터 처리
  - SQL DDL/DML 쿼리 자동 생성
  - 제조사/모델 매핑 관리
- **실행**: `./gradlew run` (Gradle)

## ⚡ 빠른 시작

### 1. Vehicle Dataset Generator 실행
```bash
cd vehicle-dataset-generator
./run_macos.sh  # macOS/Linux
# 또는
run_windows.bat  # Windows
```

### 2. Vehicle Category Generator 실행
```bash
cd vehicle-category-generator
./gradlew build
./gradlew run
```

## 📊 데이터 구조

### 데이터셋 형식 (JSON)
```json
{
  "id": "20250130_123456_001",
  "timestamp": "2025-01-30T12:34:56",
  "source_type": "image",
  "output": {
    "brand_kr": "현대",
    "brand_en": "Hyundai", 
    "model_kr": "소나타",
    "model_en": "Sonata",
    "confidence": 85
  }
}
```

### 데이터베이스 스키마
- `manufacturers`: 제조사 정보 (국산/수입 분류)
- `vehicle_models`: 차량 모델 정보 (제조사 연결)

## 🔧 기술 스택

| 컴포넌트 | 기술 |
|---------|------|
| **Backend** | Python 3.8+, Java 17+ |
| **AI/ML** | OpenAI GPT-4o-mini |
| **웹 인터페이스** | Flask |
| **데이터 처리** | Jackson (Java), JSON (Python) |
| **빌드 도구** | Gradle, pip |

## 📁 데이터 위치

- **생성된 데이터셋**: `./dataset/vehicle_dataset_*.json`
- **차량 이미지**: `./images_daytime/` (대용량으로 git 제외)
- **SQL 스크립트**: `./vehicle-category-generator/src/main/resources/`

## 🚀 시스템 요구사항

### Python 프로젝트
- Python 3.8 이상
- OpenAI API 키
- 인터넷 연결

### Java 프로젝트  
- Java 17 이상
- Gradle 8.x

## 🔑 설정

1. **OpenAI API 키 설정**
   ```bash
   # vehicle-dataset-generator/.env
   OPENAI_API_KEY=sk-your-api-key-here
   ```

2. **이미지 경로 설정**
   ```bash
   IMAGE_DIR=../images_daytime
   DATASET_DIR=../dataset
   ```

## 📈 사용 플로우

1. **이미지 준비** → `images_daytime/` 폴더에 차량 이미지 저장
2. **데이터셋 생성** → `vehicle-dataset-generator` 실행
3. **분류 처리** → `vehicle-category-generator` 실행  
4. **데이터베이스 구축** → 생성된 SQL로 DB 설정

## 🧪 테스트

### Dataset Generator 테스트
```bash
cd vehicle-dataset-generator
python -m pytest tests/
```

### Category Generator 테스트
```bash
cd vehicle-category-generator
./gradlew test
```

## 📚 문서

- [Dataset Generator 상세 가이드](./vehicle-dataset-generator/QUICK_START.md)
- [Category Generator API 문서](./vehicle-category-generator/README.md)

## 🔄 업데이트

```bash
git pull origin main
cd vehicle-dataset-generator && pip install -r requirements.txt --upgrade
cd ../vehicle-category-generator && ./gradlew clean build
```

## ⚠️ 주의사항

- 💰 OpenAI API 사용료 발생
- 🌐 인터넷 연결 필수  
- 🔒 API 키 보안 유지
- 📁 대용량 이미지 파일은 별도 관리

## 📞 지원

- 이슈 등록: GitHub Issues
- 내부 개발팀 문의

---

**Reeve로 효율적인 차량 데이터 관리를 시작하세요! 🚀**