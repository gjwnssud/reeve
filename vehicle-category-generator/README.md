# Vehicle Category Generator

차량 분류 데이터를 처리하고 SQL 쿼리를 생성하는 Java 애플리케이션입니다.

## 프로젝트 개요

이 프로젝트는 차량 제조사와 모델 정보를 JSON 데이터로부터 읽어와서 데이터베이스 테이블에 삽입할 수 있는 SQL 쿼리를 생성합니다.

### 주요 기능

- 차량 제조사 분류 (국산/수입)
- 차량 모델 분류 및 매핑
- SQL DDL/DML 쿼리 자동 생성
- JSON 데이터 처리

## 기술 스택

- **Java**: 17+
- **Gradle**: 8.x
- **Jackson**: JSON 처리
- **JUnit 5**: 테스트 프레임워크

## 프로젝트 구조

```
src/
├── main/
│   ├── java/
│   │   └── com/reeve/vehicle/category/generator/
│   │       ├── ClassificationProcessor.java    # 차량 분류 처리
│   │       └── SqlQueryGenerator.java          # SQL 쿼리 생성
│   └── resources/
│       ├── classificated_vehicle.json          # 분류된 차량 데이터
│       ├── ddl.sql                            # 테이블 생성 쿼리
│       ├── dml.sql                            # 데이터 삽입 쿼리
│       ├── lookupMdlGrpTbl.json               # 모델 그룹 룩업 테이블
│       └── lookupMnfcTbl.json                 # 제조사 룩업 테이블
└── test/
    └── java/
```

## 실행 방법

### 1. 프로젝트 클론
```bash
git clone <repository-url>
cd vehicle-category-generator
```

### 2. 빌드
```bash
./gradlew build
```

### 3. 분류 처리 실행
```bash
./gradlew run -PmainClass=com.reeve.vehicle.category.generator.ClassificationProcessor
```

### 4. SQL 쿼리 생성
```bash
./gradlew run -PmainClass=com.reeve.vehicle.category.generator.SqlQueryGenerator
```

## 데이터 구조

### 제조사 (Manufacturers)
- `code`: 제조사 코드 (영문 소문자, 언더스코어)
- `korean`: 한글 제조사명
- `english`: 영문 제조사명

### 모델 (Models)
- `code`: 모델 코드 (영문 소문자, 언더스코어)
- `manufacturer_code`: 제조사 코드 참조
- `korean`: 한글 모델명
- `english`: 영문 모델명

## 출력 파일

- `ddl.sql`: 테이블 생성 쿼리
- `dml.sql`: 데이터 삽입 쿼리
- `classificated_vehicle.json`: 분류된 차량 데이터 (JSON 형식)

## 개발 환경 설정

### 필수 요구사항
- Java 17 이상
- Gradle 8.x

### IDE 설정
- IntelliJ IDEA 권장
- 프로젝트 SDK: Java 17

## 라이센스

이 프로젝트는 Reeve 내부 프로젝트입니다.

## 기여

내부 개발팀에서만 기여 가능합니다.