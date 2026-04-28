-- analyzed_vehicles 테이블에 review_status enum, review_reason 컬럼 추가
-- 보류(on_hold) / 반려(rejected) 상태 도입 및 검수 사유 기록
-- 실행 전 백업 권장: mysqldump -u root -p reeve analyzed_vehicles > analyzed_vehicles_backup.sql

ALTER TABLE analyzed_vehicles
  ADD COLUMN review_status
    ENUM('pending','approved','on_hold','rejected')
    NOT NULL DEFAULT 'pending'
    AFTER is_verified,
  ADD COLUMN review_reason VARCHAR(255) NULL AFTER review_status,
  ADD INDEX idx_review_status (review_status),
  ADD INDEX idx_status_confidence (review_status, confidence_score);

-- 기존 데이터 마이그레이션: is_verified=1 → 'approved', is_verified=0 → 'pending'
UPDATE analyzed_vehicles
SET review_status = CASE WHEN is_verified = 1 THEN 'approved' ELSE 'pending' END;
