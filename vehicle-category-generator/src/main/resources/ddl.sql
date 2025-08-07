# 제조사
CREATE TABLE `manufacturers`
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
  AUTO_INCREMENT = 76
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;

# 차량 모델
CREATE TABLE `vehicle_models`
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
  AUTO_INCREMENT = 931
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_general_ci;
