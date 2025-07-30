# Vehicle Dataset Generator

LLM 파인튜닝을 위한 차량 데이터셋 생성 도구입니다. OpenAI GPT API를 활용하여 차량 이미지와 설명으로부터 구조화된 JSON 데이터를 추출합니다.

## 📁 프로젝트 구조

```
vehicle-dataset-generator/
├── 📄 실행 파일
│   ├── run.py                # 통합 실행기
│   ├── run_cli.sh            # 커맨드라인 실행
│   ├── run_gui.sh            # 데스크탑 앱 실행
│   ├── run_web.sh            # 웹 실행
│   ├── run_macos.sh          # macOS/Linux 자동 실행
│   └── run_windows.bat       # Windows 자동 실행
│
├── 📄 설정 파일
│   ├── .env                 # 환경변수 (API 키 등)
│   ├── .env.example         # 환경변수 예시
│   └── requirements.txt     # Python 의존성
│
├── 📁 src/                  # 소스 코드
│   ├── core/                # 핵심 로직
│   │   ├── vehicle_data_extractor.py  # 차량 데이터 추출
│   │   └── dataset_manager.py         # 데이터셋 관리
│   ├── interfaces/          # 사용자 인터페이스
│   │   ├── cli.py          # 커맨드라인 인터페이스
│   │   └── gui.py          # GUI 인터페이스 (tkinter)
│   └── utils/              # 유틸리티 함수들
│
└── 📁 web/                 # 웹 인터페이스
    ├── app.py              # Flask 웹 애플리케이션
    ├── templates/          # HTML 템플릿
    └── static/            # CSS, JS 파일
```

## 🚀 주요 기능

- **텍스트 분석**: 차량 설명으로부터 브랜드, 차종, 연식 추출
- **이미지 분석**: 차량 이미지로부터 정보 추출  
- **웹 인터페이스**: 사용자 친화적인 웹 기반 UI
- **GUI 인터페이스**: 데스크톱 애플리케이션
- **CLI 인터페이스**: 커맨드라인 도구
- **연식 추정**: AI를 통한 상세한 연식 분석
- **다국어 지원**: 한글/영문 브랜드명 동시 제공
- **배치 처리**: 여러 입력 일괄 분석
- **JSON 출력**: LLM 파인튜닝용 표준화된 데이터 형식

## 🚀 빠른 시작

### 🍎 macOS/Linux 사용자
```bash
# 실행 권한 부여 (최초 1회만)
chmod +x run_macos.sh

# 실행
./run_macos.sh
```

### 🪟 Windows 사용자
```cmd
# 더블클릭하거나 명령어로 실행
run_windows.bat
```

**✨ 완전 자동화!** Python만 설치되어 있으면 모든 설정이 자동으로 진행됩니다.

## ⚙️ 필수 준비사항

### 1. Python 설치
- **Python 3.8 이상** 필요
- 다운로드: https://www.python.org/downloads/
- ⚠️ Windows: 설치 시 "Add Python to PATH" 옵션 필수 체크

### 2. OpenAI API 키
- OpenAI 계정 생성: https://platform.openai.com
- API 키 발급: https://platform.openai.com/api-keys
- 사용량 확인: https://platform.openai.com/usage

### 3. (macOS만) tkinter 설치
```bash
# Homebrew로 설치
brew install python-tk
```

## 🎯 사용법

### 1. 자동 실행 스크립트 (추천)
위의 "빠른 시작" 섹션 참조

### 2. 통합 실행기
```bash
python run.py
# 1-4 옵션 중 선택
```

### 3. 개별 인터페이스 실행
```bash
# 웹 인터페이스
python run_web.py

# GUI 인터페이스  
python run_gui.py

# CLI 인터페이스
python run_cli.py
```

### 4. 라이브러리로 사용
```python
from src.core.vehicle_data_extractor import VehicleDataExtractor
from src.core.dataset_manager import DatasetManager

# 인스턴스 생성
extractor = VehicleDataExtractor()
dataset_manager = DatasetManager()

# 텍스트 분석
result = extractor.analyze_vehicle_from_text("2022년식 현대 소나타")
print(result)

# 이미지 분석
result = extractor.analyze_vehicle_from_image("car_image.jpg")
print(result)

# 데이터셋에 저장
dataset_manager.save_results([result], "image")
```

## 🔑 환경변수 설정

`.env` 파일에서 다음 설정들을 변경할 수 있습니다:

```bash
# OpenAI API 키 (필수)
OPENAI_API_KEY=your_openai_api_key_here

# 사용할 OpenAI 모델
OPENAI_MODEL=gpt-4o-mini

# 이미지 파일들이 있는 디렉토리 경로
IMAGE_DIR=../../images_daytime

# 데이터셋 JSON 파일들이 저장될 디렉토리 경로
DATASET_DIR=../../dataset
```

**경로 설정 예시:**
- 절대 경로: `/Users/username/vehicle-images`
- 상대 경로: `./data/images` 또는 `../../images_daytime`
- Windows 경로: `C:\\Users\\username\\vehicle-images`

## 📄 출력 형식

```json
{
  "brand_kr": "현대",
  "brand_en": "Hyundai", 
  "model_kr": "소나타",
  "model_en": "Sonata",
  "year": "2022",
  "year_info": "LED 헤드램프와 카스케이딩 그릴 디자인으로 7세대 후기형 추정",
  "confidence": 85
}
```

## 🌐 웹 인터페이스

1. 스크립트 실행 후 웹 인터페이스 선택
2. 브라우저에서 `http://localhost:4000` 접속
3. 텍스트나 이미지로 차량 분석
4. 결과를 JSON 형태로 확인
5. 데이터셋에 저장 가능

## 🖥️ GUI 인터페이스

1. 스크립트 실행 후 GUI 인터페이스 선택
2. 데스크톱 창이 열림
3. 이미지 파일 선택하여 분석
4. 실시간 결과 확인
5. 데이터셋 저장 및 통계 확인

## 💻 CLI 인터페이스

1. 스크립트 실행 후 CLI 인터페이스 선택
2. 메뉴 선택으로 기능 실행
3. 텍스트/이미지/폴더 분석 지원
4. 배치 처리 기능
5. 데이터셋 통계 확인

## 💡 문제 해결

### Python 관련
```bash
# Python 버전 확인
python --version
# 또는
python3 --version

# pip 업그레이드
python -m pip install --upgrade pip
```

### 패키지 설치 오류
```bash
# 수동 설치
pip install -r requirements.txt

# 가상환경 재생성 (macOS/Linux)
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate

# 가상환경 재생성 (Windows)
rmdir /s .venv
python -m venv .venv
.venv\Scripts\activate
```

### tkinter 오류 (macOS)
```bash
# Homebrew 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# tkinter 설치
brew install python-tk
```

### API 키 오류
- `.env` 파일에서 API 키 확인
- OpenAI 계정의 사용량 한도 확인  
- 네트워크 연결 상태 확인

## 📁 데이터셋 관리

### 저장 위치
```
../../dataset/
├── vehicle_dataset_001.json
├── vehicle_dataset_002.json
└── ...
```

### 데이터셋 형식
각 JSON 파일은 분석 결과들의 배열을 포함합니다:

```json
[
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
      "confidence": 85
    }
  }
]
```

## 🔧 개발

### 새로운 기능 추가
- **핵심 로직**: `src/core/`에 추가
- **인터페이스**: `src/interfaces/`에 추가
- **유틸리티**: `src/utils/`에 추가
- **웹 기능**: `web/`에 추가

### 테스트
```bash
python run.py
# 옵션 4번 선택하여 간단 테스트
```

## 🤝 기여

1. Fork the project
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

MIT License - 자세한 내용은 `LICENSE` 파일을 참조하세요.

## 🚨 주의사항

1. **API 요금**: OpenAI API 사용 시 요금이 발생합니다
2. **인터넷 연결**: API 호출을 위해 인터넷 연결이 필요합니다
3. **Python 버전**: 3.8 이상 버전을 사용하세요
4. **방화벽**: 웹 인터페이스 사용 시 포트 4000 허용 필요

## 🎁 추가 문서

- [**📜 빠른 시작 가이드**](QUICK_START.md) - 자세한 사용법과 문제 해결
- [OpenAI API 문서](https://platform.openai.com/docs)
- [Flask 문서](https://flask.palletsprojects.com/)
- [tkinter 문서](https://docs.python.org/3/library/tkinter.html)

---

**즐거운 데이터셋 생성하세요! 🚗✨**
