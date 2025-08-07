# 🚗 차량 데이터셋 생성기 - 빠른 시작 가이드

**Python만 있으면 3분 안에 실행 가능!** 복잡한 설정 없이 바로 시작하세요.

## 🚀 즉시 시작하기

### 🍎 **macOS/Linux 사용자**
```bash
# 1. 실행 권한 부여 (최초 1회만)
chmod +x run_macos.sh

# 2. 실행
./run_macos.sh
```

### 🪟 **Windows 사용자**
```cmd
# 더블클릭하거나 명령어로 실행
run_windows.bat
```

**끝!** 이제 모든 설정이 자동으로 진행됩니다.

---

## ✨ 자동으로 처리되는 것들

스크립트를 실행하면 다음이 **자동으로** 진행됩니다:

- ✅ **Python 설치 확인** - 없으면 설치 안내
- ✅ **가상환경 생성** - `.venv` 폴더 자동 생성
- ✅ **패키지 설치** - 필요한 라이브러리 자동 설치
- ✅ **환경 파일 생성** - `.env` 파일 자동 생성
- ✅ **API 키 설정 도움** - 에디터 자동 실행
- ✅ **인터페이스 선택** - 원하는 방식으로 실행

---

## 📋 **사전 준비사항**

### 1. 🐍 Python 설치
- **Python 3.8 이상** 필요
- 📥 다운로드: https://www.python.org/downloads/

#### Windows 주의사항
설치 시 **"Add Python to PATH"** 옵션을 반드시 체크하세요!

### 2. 🔑 OpenAI API 키 발급
1. OpenAI 계정 생성: https://platform.openai.com
2. API 키 발급: https://platform.openai.com/api-keys
3. 키를 복사해두세요 (나중에 설정에서 사용)

### 3. 🍎 macOS 추가 설정
```bash
# tkinter 설치 (GUI 사용 시 필요)
brew install python-tk
```

---

## 🎯 **실행 후 선택 메뉴**

스크립트 실행 시 다음 옵션들을 선택할 수 있습니다:

### 1. 🌐 **웹 인터페이스** (추천)
- 브라우저에서 실행: `http://localhost:4000`
- 직관적인 UI
- 드래그 앤 드롭 지원
- 실시간 결과 확인

### 2. 🖥️ **GUI 인터페이스**
- 데스크톱 애플리케이션
- 파일 선택기 제공
- 이미지 미리보기
- 결과 저장 기능

### 3. 💻 **CLI 인터페이스**
- 터미널/명령창에서 실행
- 배치 처리 최적화
- 폴더 단위 분석
- 스크립트 자동화 가능

### 4. 🧪 **테스트 모드**
- 시스템 동작 확인
- API 연결 테스트
- 설치 상태 점검

---

## 🔑 **API 키 설정**

스크립트 실행 시 `.env` 파일이 자동으로 생성되고 에디터가 열립니다.

### 설정할 내용:
```bash
# 발급받은 API 키를 여기에 입력
OPENAI_API_KEY=sk-your-actual-api-key-here

# 사용할 모델 (기본값 사용 권장)
OPENAI_MODEL=gpt-4o-mini

# 이미지 폴더 경로 (필요시 변경)
IMAGE_DIR=../../images_daytime

# 데이터셋 저장 경로 (필요시 변경)
DATASET_DIR=../../dataset
```

**중요**: `sk-`로 시작하는 실제 API 키를 입력해야 합니다!

---

## 🌐 **웹 인터페이스 사용법**

### 📸 이미지 분석
1. 웹 브라우저에서 접속
2. "이미지 업로드" 버튼 클릭
3. 차량 이미지 선택
4. 자동으로 분석 결과 표시
5. "데이터셋에 저장" 버튼으로 저장

### 📝 텍스트 분석
1. "텍스트 분석" 탭 선택
2. 차량 설명 입력 (예: "2022년식 현대 소나타")
3. "분석" 버튼 클릭
4. 결과 확인 및 저장

### 📊 결과 예시
```json
{
  "brand_kr": "현대",
  "brand_en": "Hyundai",
  "model_kr": "소나타", 
  "model_en": "Sonata",
  "year": "2022",
  "confidence": 85
}
```

---

## 🖥️ **GUI 인터페이스 사용법**

### 🎛️ 주요 기능
- **파일 선택**: 이미지 파일 브라우저
- **다중 선택**: 여러 이미지 동시 분석
- **미리보기**: 선택한 이미지 확인
- **실시간 결과**: 분석 진행 상황 표시
- **데이터셋 관리**: 저장, 통계, 관리

### 📁 지원 파일 형식
- JPG, JPEG, PNG, BMP, GIF

---

## 💻 **CLI 인터페이스 사용법**

### 🎯 메뉴 옵션
1. **텍스트 분석** - 설명으로 차량 정보 추출
2. **단일 이미지** - 하나의 이미지 파일 분석
3. **다중 이미지** - 여러 이미지 일괄 분석
4. **데이터셋 통계** - 저장된 데이터 현황 확인

### 📂 폴더 분석 예시
```bash
# 폴더 전체 이미지 분석
선택: 3 (다중 이미지 분석)
→ 1 (폴더 내 모든 이미지)
→ 폴더 경로 입력: /path/to/images
```

---

## 💡 **자주 발생하는 문제와 해결법**

### ❌ "Python을 찾을 수 없습니다"
```bash
# 해결법:
# 1. Python 재설치 (PATH 옵션 체크)
# 2. 터미널 재시작
# 3. python3 명령어 시도
```

### ❌ "패키지 설치 실패"
```bash
# 해결법:
# 1. 인터넷 연결 확인
# 2. 수동 설치 시도
pip install openai python-dotenv pillow flask requests

# 3. pip 업그레이드
python -m pip install --upgrade pip
```

### ❌ "tkinter 모듈 없음" (macOS)
```bash
# 해결법:
# 1. Homebrew 설치
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2. tkinter 설치
brew install python-tk
```

### ❌ "API 키 오류"
- `.env` 파일에서 API 키 확인
- `sk-`로 시작하는지 확인
- OpenAI 계정 사용량 한도 확인
- 네트워크 연결 상태 확인

### ❌ "포트 4000 사용 중" (웹 인터페이스)
```bash
# 해결법:
# 1. 다른 프로그램 종료
# 2. 포트 변경 (web/app.py에서 port=4000 수정)
```

---

## 📁 **데이터셋 위치와 형식**

### 💾 저장 위치
```
../../dataset/
├── vehicle_dataset_001.json  # 첫 번째 데이터셋 파일
├── vehicle_dataset_002.json  # 두 번째 데이터셋 파일
└── ...
```

### 📊 파일 구조
```json
[
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
      "year": "2022",
      "year_info": "LED 헤드램프 디자인 특징으로 추정",
      "confidence": 85
    },
    "metadata": {
      "has_error": false,
      "processing_time": 2.3
    }
  }
]
```

---

## 🎯 **사용 팁**

### 📸 **이미지 분석 팁**
- **고해상도 이미지** 사용 권장
- **정면 또는 측면** 각도가 좋음
- **헤드램프와 그릴**이 잘 보이는 사진
- **밝은 조명**에서 촬영된 이미지

### 📝 **텍스트 분석 팁**
- **구체적인 특징** 명시 (LED 헤드램프, 그릴 디자인 등)
- **연식 정보** 포함
- **브랜드명과 모델명** 명확히 기재
- **한글/영문** 모두 가능

### 💾 **데이터셋 관리 팁**
- 정기적으로 **통계 확인**
- 신뢰도 낮은 결과는 **수동 검증**
- 백업을 위해 **정기적으로 복사**

---

## 🔄 **업데이트 방법**

```bash
# 1. 새 버전 다운로드
git pull

# 2. 패키지 업데이트
pip install -r requirements.txt --upgrade

# 3. 재실행
./run_macos.sh  # 또는 run_windows.bat
```

---

## 🆘 **추가 지원**

### 📞 문제 해결이 안 될 때
1. **GitHub Issues** 등록
2. **에러 메시지 전체** 복사하여 첨부
3. **운영체제 및 Python 버전** 명시
4. **실행한 명령어** 기록

### 📚 추가 자료
- [OpenAI API 가이드](https://platform.openai.com/docs)
- [Python 설치 가이드](https://www.python.org/downloads/)
- [Flask 문서](https://flask.palletsprojects.com/)

---

## 🎉 **성공적인 설치 확인**

다음이 표시되면 성공입니다:

```
✅ Python 확인됨: Python 3.x.x
✅ 가상환경 활성화됨
✅ 패키지 설치 완료
✅ .env 파일 생성됨
✅ API 키 설정됨

🎯 실행할 인터페이스를 선택하세요:
1. 🌐 웹 인터페이스 (추천)
2. 🖥️ GUI 인터페이스
3. 💻 CLI 인터페이스
4. 🧪 테스트 모드
```

**축하합니다! 이제 차량 데이터셋 생성을 시작할 수 있습니다! 🚗✨**

---

## 🚨 **주의사항**

- 💰 **API 사용료**: OpenAI API 사용 시 요금이 발생합니다
- 🌐 **인터넷 필요**: API 호출을 위해 인터넷 연결 필수
- 🔒 **API 키 보안**: .env 파일을 외부에 공유하지 마세요
- 📱 **방화벽**: 웹 인터페이스 사용 시 포트 4000 허용 필요

**안전하고 즐거운 데이터셋 생성 되세요!** 🎯
