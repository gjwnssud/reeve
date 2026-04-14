-- training_dataset 테이블에서 qdrant_id 컬럼 및 인덱스 제거
-- stack/no-qdrant 브랜치 전용 마이그레이션
-- 실행 전 반드시 백업 권장: mysqldump -u root -p reeve training_dataset > training_dataset_backup.sql

ALTER TABLE training_dataset DROP INDEX idx_qdrant_id;
ALTER TABLE training_dataset DROP COLUMN qdrant_id;
