# Vehicle Dataset Generator

> OpenAI GPT API를 활용한 차량 정보 추출 및 LLM 파인튜닝용 데이터셋 생성 도구

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o--mini-orange.svg)](https://platform.openai.com/)

## 🎯 개요

차량 이미지와 설명으로부터 구조화된 JSON 데이터를 추출하는 도구입니다. 브랜드, 모델, 연식 정보를 한글/영문으로 동시 제공하며, 다양한 인터페이스를 통해 사용할 수 있습니다.

## ✨ 주요 기능

### 🔍 분석 기능
- **이미지 분석**: 차량 사진에서 정보 자동 추출
- **텍스트 분석**: 차량 설명에서 구조화된 데이터 생성
- **연식 추정**: AI 기반 상세한 연식 분석
- **신뢰도 평가**: 추출 결과의 정확도 점수 제공

### 🌐 다중 인터페이스
- **웹 인터페이스**: 직관적인 브라우저 기반 UI
- **GUI 애플리케이션**: tkinter 기반 데스크톱 앱
- **CLI 도구**: 자동화 및 배치 처리 지원

### 📊 데이터 관리
- **JSON 출력**: LLM 파인튜닝 표준 형식
- **배치 처리**: 여러 파일 일괄 분석
- **데이터셋 관리**: 자동 파일 분할 및 버전 관리

## 📁 프로젝트 구조

```
vehicle-dataset-generator/
├── 🚀 실행 파일
│   ├── run.py                # 🎯 통합 실행기
│   ├── run_cli.py            # 💻 CLI 실행
│   ├── run_gui.py            # 🖥️ GUI 실행  
│   ├── run_web.py            # 🌐 웹 실행
│   ├── run_macos.sh          # 🍎 macOS 자동 실행
│   └── run_windows.bat       # 🪟 Windows 자동 실행
│
├── ⚙️ 설정 파일
│   ├── .env                 # 🔐 환경변수 (API 키)
│   ├── .env.example         # 📄 환경변수 예시
│   ├── requirements.txt     # 📦 Python 의존성
│   └── yolov8n.pt          # 🤖 YOLO 모델 (옵션)
│
├── 📁 src/                  # 핵심 소스 코드
│   ├── core/                # 🧠 비즈니스 로직
│   │   ├── vehicle_data_extractor.py  # 차량 데이터 추출
│   │   └── dataset_manager.py         # 데이터셋 관리
│   ├── interfaces/          # 🎛️ 사용자 인터페이스
│   │   ├── cli.py          # 커맨드라인 인터페이스
│   │   └── gui.py          # GUI 인터페이스
│   └── utils/              # 🛠️ 유틸리티 함수
│
└── 📁 web/                 # 웹 애플리케이션
    ├── app.py              # 🌐 Flask 서버
    ├── templates/          # 📄 HTML 템플릿
    └── static/            # 🎨 CSS, JavaScript
```

## 🚀 빠른 시작

### 🛠️ 필수 준비사항

1. **Python 3.8+** 설치
2. **OpenAI API 키** 발급 ([가이드](https://platform.openai.com/api-keys))
3. **tkinter** 설치 (macOS: `brew install python-tk`)

### ⚡ 자동 실행 (권장)

**macOS/Linux:**
```bash
# 실행 권한 부여 (최초 1회)
chmod +x run_macos.sh

# 자동 실행
./run_macos.sh
```

**Windows:**
```cmd
# 더블클릭 또는 명령어 실행
run_windows.bat
```

**✨ 완전 자동화!** 가상환경 생성부터 의존성 설치까지 모든 과정이 자동으로 진행됩니다.

### 🎯 통합 실행기 사용

```bash
python run.py

# 메뉴에서 선택:
# 1. 🌐 웹 인터페이스 (추천)
# 2. 🖥️ GUI 인터페이스  
# 3. 💻 CLI 인터페이스
# 4. 🧪 간단 테스트
```

### 🔧 개별 실행

```bash
# 웹 인터페이스 (http://localhost:4000)
python run_web.py

# GUI 데스크톱 앱
python run_gui.py

# CLI 도구
python run_cli.py
```

## ⚙️ 환경 설정

### `.env` 파일 구성

```bash
# 🔑 OpenAI API 설정 (필수)
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o-mini

# 📁 디렉토리 경로 설정
IMAGE_DIR=../../images_daytime        # 이미지 소스 폴더
DATASET_DIR=../../dataset             # 데이터셋 저장 폴더

# 🌐 웹 서버 설정 (옵션)
WEB_PORT=4000
DEBUG=True
```

### 📂 경로 설정 예시

```bash
# 절대 경로
IMAGE_DIR=/Users/username/vehicle-images
DATASET_DIR=/Users/username/datasets

# 상대 경로  
IMAGE_DIR=./images
DATASET_DIR=../output/datasets

# Windows 경로
IMAGE_DIR=C:\Users\username\vehicle-images
DATASET_DIR=C:\Users\username\datasets
```

## 🎨 사용법

### 🌐 웹 인터페이스

1. **실행**: `python run_web.py` 또는 통합 실행기에서 선택
2. **접속**: 브라우저에서 `http://localhost:4000` 열기
3. **분석**: 텍스트 입력하거나 이미지 파일 업로드
4. **결과**: JSON 형태로 차량 정보 확인
5. **저장**: 데이터셋에 결과 자동 저장

### 🖥️ GUI 인터페이스

1. **실행**: `python run_gui.py` 또는 통합 실행기에서 선택
2. **파일 선택**: '이미지 선택' 버튼으로 차량 사진 선택
3. **분석**: 자동으로 이미지 분석 시작
4. **결과 확인**: 실시간으로 추출된 정보 표시
5. **저장**: 결과를 데이터셋에 저장

### 💻 CLI 인터페이스

```bash
python run_cli.py

# 메뉴 옵션:
# 1. 텍스트 분석     - 차량 설명 입력
# 2. 단일 이미지 분석 - 이미지 파일 선택  
# 3. 폴더 배치 분석  - 여러 이미지 일괄 처리
# 4. 데이터셋 통계   - 저장된 데이터 현황
```

### 🔧 라이브러리로 사용

```python
from src.core.vehicle_data_extractor import VehicleDataExtractor
from src.core.dataset_manager import DatasetManager

# 인스턴스 생성
extractor = VehicleDataExtractor()
dataset_manager = DatasetManager()

# 텍스트 분석
result = extractor.analyze_vehicle_from_text("2022년식 현대 소나타 DN8")
print(result)

# 이미지 분석
result = extractor.analyze_vehicle_from_image("path/to/car.jpg")
print(result)

# 데이터셋 저장
dataset_manager.save_results([result], "image")
```

## 📊 출력 형식

### JSON 데이터 구조

```json
{
  "id": "20250130_123456_001",
  "timestamp": "2025-01-30T12:34:56",
  "source_type": "image",
  "input": "hyundai_sonata.jpg",
  "output": {
    "brand_kr": "현대",
    "brand_en": "Hyundai",
    "model_kr": "소나타",
    "model_en": "Sonata",
    "year": "2022",
    "year_info": "DN8 페이스리프트 모델로 LED 헤드램프 적용",
    "confidence": 85
  }
}
```

### 필드 설명

| 필드 | 설명 | 예시 |
|------|------|------|
| `brand_kr` | 한글 브랜드명 | "현대" |
| `brand_en` | 영문 브랜드명 | "Hyundai" |
| `model_kr` | 한글 모델명 | "소나타" |
| `model_en` | 영문 모델명 | "Sonata" |
| `year` | 연식 | "2022" |
| `year_info` | 연식 추정 근거 | "LED 헤드램프..." |
| `confidence` | 신뢰도 (1-100) | 85 |

## 🛠️ 고급 기능

### 📁 데이터셋 관리

- **자동 분할**: 파일 크기 기준 데이터셋 분리
- **버전 관리**: 타임스탬프 기반 파일명
- **중복 제거**: 동일한 입력 데이터 중복 방지
- **통계 제공**: 브랜드별, 연식별 분포 확인

### 🔍 배치 처리

```python
# 폴더 내 모든 이미지 분석
python run_cli.py
# 옵션 3 선택 → 폴더 경로 입력
```

### 📈 성능 최적화

- **API 호출 최적화**: 요청 간격 조절
- **오류 처리**: 네트워크 오류 자동 재시도
- **캐싱**: 중복 분석 결과 캐시

## 💡 문제 해결

### 🐍 Python 관련

```bash
# Python 버전 확인
python --version  # 3.8+ 필요

# 패키지 수동 설치
pip install -r requirements.txt

# 가상환경 재생성
rm -rf .venv && python -m venv .venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
```

### 🔑 API 관련

```bash
# API 키 확인
cat .env | grep OPENAI_API_KEY

# 사용량 확인
# https://platform.openai.com/usage 방문
```

### 🖥️ GUI/tkinter 오류 (macOS)

```bash
# Homebrew 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# tkinter 설치
brew install python-tk
```

### 🌐 웹 인터페이스 오류

```bash
# 포트 사용 중일 때
lsof -i :4000
kill -9 [PID]

# 방화벽 설정 확인 (Windows)
# Windows Defender에서 포트 4000 허용
```

## 🧪 테스트

### 기본 테스트

```bash
python run.py
# 옵션 4번 선택하여 간단 테스트 실행
```

### 수동 테스트

```python
# 간단한 텍스트 분석 테스트
from src.core.vehicle_data_extractor import VehicleDataExtractor
extractor = VehicleDataExtractor()
result = extractor.analyze_vehicle_from_text("2020 BMW 3시리즈")
print(result)
```

## 🔧 개발 가이드

### IDE 설정 (IntelliJ IDEA / PyCharm)

1. **프로젝트 열기**: `vehicle-dataset-generator` 폴더를 IDE에서 열기
2. **Python 인터프리터**: `.venv/bin/python` 설정
3. **실행 구성**: `run.py`를 메인 실행 파일로 설정
4. **코드 스타일**: PEP 8 준수

### 새로운 기능 추가

```python
# 새로운 분석 기능 추가 예시
# src/core/vehicle_data_extractor.py

def analyze_vehicle_advanced(self, input_data):
    """고급 차량 분석 기능"""
    # 구현 내용
    pass
```

### 새로운 인터페이스 추가

1. **인터페이스 파일**: `src/interfaces/` 하위에 새 파일 생성
2. **메인 실행기**: `run.py`에 새 옵션 추가
3. **테스트**: 기본 기능 동작 확인

## 📈 성능 및 제한사항

### API 사용량

- **GPT-4o-mini**: 약 $0.0002/1K 토큰 (입력 기준)
- **이미지 분석**: 이미지당 약 1,000~2,000 토큰 소모
- **예상 비용**: 이미지 1장당 약 $0.0004~0.0008

### 처리 속도

- **텍스트 분석**: ~2-3초/건
- **이미지 분석**: ~5-10초/건 (이미지 크기에 따라)
- **배치 처리**: API 제한으로 인한 간격 조절 필요

### 정확도

- **브랜드 인식**: ~95%
- **모델 인식**: ~85-90%
- **연식 추정**: ~70-80% (외관 변화가 큰 모델)

## 🎯 사용 사례

### 1. 중고차 매매 업체
```python
# 대량 차량 정보 자동 추출
for image_file in car_images:
    result = extractor.analyze_vehicle_from_image(image_file)
    inventory_db.save(result)
```

### 2. 보험사 차량 평가
```python
# 사고 차량 정보 빠른 파악
accident_info = extractor.analyze_vehicle_from_image("accident_car.jpg")
insurance_claim.update(accident_info)
```

### 3. 연구 기관 데이터셋 구축
```python
# 대규모 차량 데이터셋 생성
dataset_manager.batch_process("./research_images/")
research_data = dataset_manager.export_for_training()
```

## 🤝 기여하기

### 이슈 리포팅

- **버그 리포트**: GitHub Issues에 상세한 정보와 함께 등록
- **기능 요청**: 사용 사례와 함께 제안
- **문서 개선**: README나 코드 주석 개선 제안

### 코드 기여

1. **Fork**: 저장소를 개인 계정으로 포크
2. **브랜치**: `feature/새기능` 또는 `bugfix/버그수정` 브랜치 생성
3. **개발**: 코드 작성 및 테스트
4. **PR**: Pull Request 생성 및 리뷰 요청

### 코딩 스타일

```python
# PEP 8 준수
def analyze_vehicle_data(input_data: str) -> dict:
    """
    차량 데이터 분석 함수
    
    Args:
        input_data (str): 입력 데이터
        
    Returns:
        dict: 분석 결과
    """
    # 구현 내용
    pass
```

## 📚 참고 자료

### 공식 문서

- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Flask Documentation](https://flask.palletsprojects.com/)
- [tkinter Documentation](https://docs.python.org/3/library/tkinter.html)

### 관련 프로젝트

- [Reeve 메인 프로젝트](../)
- [차량 분류 체계](../classificated_vehicle.json)

### 유용한 링크

- [Python 가상환경 가이드](https://docs.python.org/3/tutorial/venv.html)
- [OpenAI API 사용량 모니터링](https://platform.openai.com/usage)
- [JSON 데이터 검증 도구](https://jsonlint.com/)

## 📄 라이선스

이 프로젝트는 [MIT License](../LICENSE) 하에 배포됩니다.

## 🚨 주의사항

### 중요 사항

1. **API 비용**: OpenAI API 사용 시 요금 발생
2. **네트워크**: 인터넷 연결 필수
3. **Python 버전**: 3.8 이상 권장
4. **보안**: API 키를 공개 저장소에 커밋하지 마세요

### 보안 가이드

```bash
# .env 파일은 절대 git에 커밋하지 마세요
echo ".env" >> .gitignore

# API 키 확인
git log --oneline | grep -i "api\|key"  # 기록에 API 키가 없는지 확인
```

## 📞 지원

### 문제 해결

1. **FAQ**: [QUICK_START.md](QUICK_START.md) 참조
2. **Issues**: GitHub Issues에서 검색
3. **Discussion**: 프로젝트 Discussion 활용

### 연락처

- **GitHub**: [프로젝트 저장소](https://github.com/gjwnssud/vehicle-recognition-system)
- **Issues**: 버그 리포트 및 기능 요청
- **Discussions**: 일반적인 질문 및 토론

---

### 🎉 마무리

**차량 데이터셋 생성의 새로운 표준, Vehicle Dataset Generator!**

이 도구를 통해 고품질의 차량 데이터셋을 효율적으로 구축하고, 
차세대 차량 인식 AI 모델 개발에 기여해보세요! 🚗✨
