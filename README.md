# Vehicle Recognition System

차량 인식 및 분석을 위한 AI 시스템 개발 프로젝트입니다.

## 프로젝트 구조

### 📁 vehicle-dataset-generator

LLM 파인튜닝을 위한 차량 데이터셋 생성 도구

- **목적**: ChatGPT API를 활용한 차량 정보 추출 및 JSON 데이터셋 구축
- **기능**: 텍스트/이미지 분석, 웹/GUI 인터페이스, 배치 처리
- **출력**: 브랜드, 차종, 연식 정보가 포함된 구조화된 JSON 데이터
- **활용**: 로컬 LLM 파인튜닝용 훈련 데이터 생성

## 개발 로드맵

### Phase 1: 데이터 수집 도구 ✅

- [x]  ChatGPT API 기반 차량 정보 추출
- [ ]  웹/GUI 인터페이스 구현
    - [x]  다중 이미지 파일 선택 후 분석
    - [x]  데이터셋 JSON 형식 저장
    - [x]  데이터셋 파일 파일 크기 및 항목 기준 로테이션 저장
    - [ ]  분석 결과 7개 필드 출력
    - [ ]  분결 결과 필드 수동 입력 기능
    - [ ]  중복 파일 분석 제외

### Phase 2: 데이터셋 구축 🔄

- [ ]  대량 이미지 데이터 수집
- [ ]  데이터 품질 검증 및 정제
- [ ]  훈련/검증 데이터셋 분리

### Phase 3: 로컬 LLM 파인튜닝 📋

- [ ]  모델 선택 및 준비
- [ ]  파인튜닝 파이프라인 구축
- [ ]  성능 평가 및 최적화

### Phase 4: 배포 및 서비스화 🎯

- [ ]  모델 서빙 인프라
- [ ]  API 서버 구축
- [ ]  프로덕션 배포

## 기술 스택

- **Language**: Python 3.8+
- **API**: OpenAI GPT-4o-mini
- **Web Framework**: Flask
- **GUI**: tkinter
- **Data Format**: JSON
- **Future**: Transformers, PyTorch, Datasets

## 저장소

[GitHub](https://github.com/gjwnssud/vehicle-recognition-system)

## 라이선스

MIT License