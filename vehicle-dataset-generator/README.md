# Vehicle Dataset Generator

차량 이미지를 이용한 로컬 LLM 데이터셋 구축 도구

## 기능

### 핵심 기능
- **다중 이미지 업로드**: 여러 차량 이미지를 한번에 업로드
- **자동 차량 탐지**: YOLOv8을 이용한 정확한 차량 객체 탐지
- **지능형 차량 분석**: ChatGPT API를 통한 제조사 및 모델 자동 식별
- **LLaVa 데이터셋 생성**: 분석 결과를 LLaVa 언어 모델 학습용 형식으로 저장
- **수동 입력 지원**: AI 분석 실패시 수동으로 차량 정보 입력 가능
- **카테고리 관리**: 새로운 제조사 및 모델 등록 기능

### 차량 데이터베이스
- 제조사 75종 (국산/수입차 구분)
- 모델 930종
- MySQL 데이터베이스 기반 관리

### 웹 인터페이스
- Bootstrap 5.3 기반 반응형 UI
- 실시간 분석 진행 상황 표시
- 드래그 가능한 바운딩 박스 조정
- 배치 분석 지원 (1분에 2장 제한)

## 기술 스택

- **백엔드**: Flask, Python
- **프론트엔드**: Bootstrap 5.3, jQuery, Vanilla JavaScript
- **AI/ML**: YOLOv8, OpenAI GPT-4o
- **데이터베이스**: MySQL
- **이미지 처리**: OpenCV, Pillow

## 설치 및 실행

### 1. 의존성 설치

```bash
# 가상환경 생성 (선택사항)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 패키지 설치
pip install -r requirements.txt
```

### 2. 환경 설정

`.env` 파일 설정:
```env
# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4o

# 파일 경로 설정
UPLOAD_FOLDER=./temp
DATASET_FOLDER=./dataset

# 데이터베이스 설정
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_DATABASE=reeve
```

### 3. 데이터베이스 설정

MySQL 데이터베이스에 제조사 및 모델 테이블 생성:
```sql
-- manufacturers 테이블 생성 및 데이터 삽입
-- vehicle_models 테이블 생성 및 데이터 삽입
-- (프로젝트 문서 참조)
```

### 4. YOLOv8 모델 다운로드

```bash
# YOLOv8n 모델이 자동으로 다운로드됩니다
# 또는 수동으로 yolov8n.pt 파일을 프로젝트 루트에 배치
```

### 5. 애플리케이션 실행

```bash
python app.py
```

애플리케이션이 `http://localhost:5000`에서 실행됩니다.

## 사용 방법

### 1. 이미지 업로드
- 메인 페이지에서 차량 이미지를 선택하여 업로드
- 다중 선택 가능 (PNG, JPG, JPEG, GIF, BMP, WEBP)

### 2. 차량 탐지
- 업로드된 이미지에서 "탐지" 버튼 클릭
- YOLOv8이 자동으로 차량 객체를 탐지하여 바운딩 박스 표시

### 3. 바운딩 박스 조정
- 탐지된 차량에 자동으로 바운딩 박스가 표시됩니다
- **드래그 기능**: 마우스로 바운딩 박스를 드래그하여 위치 조정
- **리사이즈 기능**: 우하단 핸들을 드래그하여 크기 조정
- **박스 선택**: 클릭으로 바운딩 박스 선택 (녹색으로 표시)
- **리셋 기능**: 각 박스의 "리셋" 버튼으로 원래 위치로 복원
- **실시간 좌표 업데이트**: 박스 조정시 분석에 사용될 좌표가 실시간 반영

### 4. 차량 분석
- "분석" 버튼 클릭으로 ChatGPT API를 통한 제조사/모델 식별
- 1차: 제조사 식별
- 2차: 모델 식별 (30초 간격)

### 5. 결과 확인 및 저장
- 분석 결과를 확인하고 데이터셋에 저장
- 분석 실패시 수동 입력 또는 새 카테고리 등록 가능

### 6. 배치 분석
- "전체 이미지 분석 시작" 버튼으로 모든 업로드된 이미지를 순차 분석
- 1분에 2장씩 제한하여 API 사용량 최적화

## 데이터셋 형식

생성되는 LLaVa 데이터셋은 다음 형식으로 저장됩니다:

```json
{
  "id": "vehicle_20241217_143022_image.jpg",
  "image": "relative/path/to/image.jpg",
  "conversations": [
    {
      "from": "human",
      "value": "이 이미지에 있는 차량의 제조사와 모델을 알려주세요."
    },
    {
      "from": "gpt",
      "value": "이 차량은 현대(Hyundai)의 쏘나타(Sonata) 모델입니다."
    }
  ],
  "metadata": {
    "manufacturer_code": "hyundai",
    "model_code": "sonata",
    "confidence_scores": {...},
    "bbox": [x1, y1, x2, y2]
  }
}
```

## 프로젝트 구조

```
vehicle-dataset-generator/
├── app.py                 # Flask 메인 애플리케이션
├── config.py              # 설정 관리
├── database.py            # 데이터베이스 연결 및 쿼리
├── vehicle_detection.py   # YOLOv8 차량 탐지
├── vehicle_analysis.py    # ChatGPT API 차량 분석
├── dataset_generator.py   # LLaVa 데이터셋 생성
├── blueprints/
│   ├── main.py           # 메인 라우트
│   └── api.py            # API 라우트
├── templates/
│   ├── base.html
│   ├── index.html
│   └── analysis.html
├── static/
│   ├── js/
│   │   ├── main.js
│   │   └── analysis.js
│   └── css/
├── requirements.txt
├── .env
└── README.md
```

## API 엔드포인트

### 파일 업로드
- `POST /api/upload` - 다중 이미지 업로드

### 차량 분석
- `POST /api/detect` - 차량 탐지
- `POST /api/analyze` - 차량 분석

### 데이터 관리
- `GET /manufacturers` - 제조사 목록 조회
- `GET /manufacturers/{code}/models` - 제조사별 모델 목록
- `POST /api/add-manufacturer` - 새 제조사 추가
- `POST /api/add-model` - 새 모델 추가

### 데이터셋
- `POST /api/save-dataset` - 데이터셋 저장
- `GET /dataset/statistics` - 데이터셋 통계

## 제한사항

- OpenAI API 사용량 제한으로 1분에 2장 분석
- 최대 업로드 파일 크기: 16MB
- 데이터셋 파일당 최대 1000개 엔트리

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 기여

버그 리포트 및 기능 요청은 GitHub Issues를 통해 제출해주세요.
