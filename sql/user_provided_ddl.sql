# 제조사
CREATE TABLE IF NOT EXISTS `manufacturers`
(
    `id`           bigint                                  NOT NULL AUTO_INCREMENT,
    `code`         varchar(50) COLLATE utf8mb4_general_ci  NOT NULL,
    `english_name` varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
    `korean_name`  varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
    `is_domestic`  tinyint(1)                              NOT NULL DEFAULT '0',
    `created_at`   timestamp                               NULL     DEFAULT CURRENT_TIMESTAMP,
    `updated_at`   timestamp                               NULL     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `code` (`code`),
    KEY `idx_code` (`code`),
    KEY `idx_domestic_code` (`is_domestic`, `code`)
) ENGINE = InnoDB
  AUTO_INCREMENT = 1
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;

# 차량 모델
CREATE TABLE IF NOT EXISTS `vehicle_models`
(
    `id`                bigint                                  NOT NULL AUTO_INCREMENT,
    `code`              varchar(100) COLLATE utf8mb4_general_ci NOT NULL,
    `manufacturer_id`   bigint                                  NOT NULL,
    `manufacturer_code` varchar(50) COLLATE utf8mb4_general_ci  NOT NULL,
    `english_name`      varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
    `korean_name`       varchar(200) COLLATE utf8mb4_general_ci NOT NULL,
    `created_at`        timestamp                               NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        timestamp                               NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_code` (`code`),
    KEY `idx_manufacturer_id` (`manufacturer_id`),
    KEY `idx_manufacturer_code` (`manufacturer_code`),
    CONSTRAINT `vehicle_models_ibfk_1` FOREIGN KEY (`manufacturer_id`) REFERENCES `manufacturers` (`id`) ON DELETE CASCADE
) ENGINE = InnoDB
  AUTO_INCREMENT = 1
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;

# 분석 결과 테이블
CREATE TABLE IF NOT EXISTS `analyzed_vehicles`
(
    `id`                      bigint                                  NOT NULL AUTO_INCREMENT,
    `image_path`              varchar(500) COLLATE utf8mb4_general_ci NOT NULL COMMENT '크롭 이미지 경로',
    `original_image_path`     varchar(500) COLLATE utf8mb4_general_ci          DEFAULT NULL COMMENT '원본 업로드 이미지 경로',
    `source`                  varchar(20) COLLATE utf8mb4_general_ci  NOT NULL DEFAULT 'file' COMMENT '데이터 출처: file/folder',
    `client_uuid`             varchar(36) COLLATE utf8mb4_general_ci           DEFAULT NULL COMMENT '브라우저 UUID',
    `raw_result`              json                                             DEFAULT NULL COMMENT 'OpenAI Vision API 원본 응답',
    `manufacturer`            varchar(100) COLLATE utf8mb4_general_ci          DEFAULT NULL COMMENT '추출된 제조사명',
    `model`                   varchar(200) COLLATE utf8mb4_general_ci          DEFAULT NULL COMMENT '추출된 모델명',
    `year`                    varchar(50) COLLATE utf8mb4_general_ci           DEFAULT NULL COMMENT '추출된 연식',
    `matched_manufacturer_id` bigint                                           DEFAULT NULL COMMENT '매칭된 제조사 ID',
    `matched_model_id`        bigint                                           DEFAULT NULL COMMENT '매칭된 모델 ID',
    `confidence_score`        decimal(5, 2)                                    DEFAULT NULL COMMENT '신뢰도 점수 (0-100)',
    `is_verified`             tinyint(1)                              NOT NULL DEFAULT '0' COMMENT '검수 완료 여부 (review_status 호환용)',
    `review_status`           enum('pending','approved','on_hold','rejected') NOT NULL DEFAULT 'pending' COMMENT '검수 상태',
    `review_reason`           varchar(255) COLLATE utf8mb4_general_ci          DEFAULT NULL COMMENT '보류/반려 사유',
    `verified_by`             varchar(100) COLLATE utf8mb4_general_ci          DEFAULT NULL COMMENT '검수자',
    `verified_at`             timestamp                               NULL     DEFAULT NULL COMMENT '검수 일시',
    `notes`                   text COLLATE utf8mb4_general_ci                  DEFAULT NULL COMMENT '검수 메모',
    `processing_stage`        varchar(50) COLLATE utf8mb4_general_ci           DEFAULT 'analysis_complete' COMMENT '처리 단계: uploaded/yolo_detected/analysis_complete/verified',
    `yolo_detections`         json                                             DEFAULT NULL COMMENT 'YOLO 감지 결과 bbox 목록',
    `selected_bbox`           json                                             DEFAULT NULL COMMENT '사용자 선택 bbox',
    `created_at`              timestamp                               NULL     DEFAULT CURRENT_TIMESTAMP,
    `updated_at`              timestamp                               NULL     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    KEY `idx_image_path` (`image_path`),
    KEY `idx_is_verified` (`is_verified`),
    KEY `idx_matched_manufacturer_id` (`matched_manufacturer_id`),
    KEY `idx_matched_model_id` (`matched_model_id`),
    KEY `idx_created_at` (`created_at`),
    KEY `idx_processing_stage` (`processing_stage`),
    KEY `idx_processing_stage_verified_created` (`processing_stage`, `is_verified`, `created_at`),
    KEY `idx_client_source_verified` (`client_uuid`, `source`, `is_verified`),
    KEY `idx_review_status` (`review_status`),
    KEY `idx_status_confidence` (`review_status`, `confidence_score`),
    CONSTRAINT `fk_analyzed_manufacturer` FOREIGN KEY (`matched_manufacturer_id`) REFERENCES `manufacturers` (`id`) ON DELETE SET NULL,
    CONSTRAINT `fk_analyzed_model` FOREIGN KEY (`matched_model_id`) REFERENCES `vehicle_models` (`id`) ON DELETE SET NULL
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci
  COMMENT = 'OpenAI Vision API 분석 결과 저장 테이블';

# 학습 데이터셋 테이블
CREATE TABLE IF NOT EXISTS `training_dataset`
(
    `id`                bigint                                  NOT NULL AUTO_INCREMENT,
    `image_path`        varchar(500) COLLATE utf8mb4_general_ci NOT NULL COMMENT '검증된 이미지 경로',
    `manufacturer_id`   bigint                                  NOT NULL COMMENT '제조사 ID',
    `model_id`          bigint                                  NOT NULL COMMENT '모델 ID',
    `created_at`        timestamp                               NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at`        timestamp                               NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_image_path` (`image_path`),
    KEY `idx_manufacturer_id` (`manufacturer_id`),
    KEY `idx_model_id` (`model_id`),
    KEY `idx_created_at` (`created_at`),
    CONSTRAINT `fk_training_manufacturer` FOREIGN KEY (`manufacturer_id`) REFERENCES `manufacturers` (`id`) ON DELETE CASCADE,
    CONSTRAINT `fk_training_model` FOREIGN KEY (`model_id`) REFERENCES `vehicle_models` (`id`) ON DELETE CASCADE
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci
  COMMENT = '검증된 학습 데이터셋 저장 테이블';

