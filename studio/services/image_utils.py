"""
이미지 처리 유틸리티
이미지 검증, 리사이징, 최적화
"""
import os
from pathlib import Path
from typing import Tuple, Optional
import logging
from PIL import Image
import hashlib

from studio.config import settings

logger = logging.getLogger(__name__)


class ImageProcessor:
    """이미지 처리 및 저장 관리"""

    def __init__(self, upload_dir: str = "data/uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def validate_image(self, file_path: str) -> bool:
        """
        이미지 파일 유효성 검증

        Args:
            file_path: 이미지 파일 경로

        Returns:
            유효 여부
        """
        try:
            with Image.open(file_path) as img:
                # 이미지 포맷 확인
                if img.format.lower() not in ['jpeg', 'jpg', 'png', 'webp']:
                    logger.warning(f"Invalid image format: {img.format}")
                    return False

                # 이미지 크기 확인 (최소 크기)
                if img.width < 100 or img.height < 100:
                    logger.warning(f"Image too small: {img.width}x{img.height}")
                    return False

                # 이미지가 손상되지 않았는지 확인
                img.verify()

                return True

        except Exception as e:
            logger.error(f"Image validation failed: {e}")
            return False

    def get_image_hash(self, file_path: str) -> str:
        """
        이미지 파일 해시 생성 (중복 체크용)

        Args:
            file_path: 이미지 파일 경로

        Returns:
            SHA256 해시 문자열
        """
        hash_sha256 = hashlib.sha256()

        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)

        return hash_sha256.hexdigest()

    def resize_image(
        self,
        file_path: str,
        max_width: int = 1920,
        max_height: int = 1080,
        quality: int = 85
    ) -> str:
        """
        이미지 리사이징 및 최적화

        Args:
            file_path: 원본 이미지 경로
            max_width: 최대 너비
            max_height: 최대 높이
            quality: JPEG 품질 (1-100)

        Returns:
            리사이징된 이미지 경로
        """
        try:
            with Image.open(file_path) as img:
                # EXIF 방향 정보 적용
                try:
                    from PIL import ExifTags
                    for orientation in ExifTags.TAGS.keys():
                        if ExifTags.TAGS[orientation] == 'Orientation':
                            break
                    exif = img._getexif()
                    if exif is not None:
                        orientation_value = exif.get(orientation)
                        if orientation_value == 3:
                            img = img.rotate(180, expand=True)
                        elif orientation_value == 6:
                            img = img.rotate(270, expand=True)
                        elif orientation_value == 8:
                            img = img.rotate(90, expand=True)
                except (AttributeError, KeyError, IndexError):
                    pass

                # 비율 유지하면서 리사이징
                img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # RGB로 변환 (RGBA 등에서)
                if img.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background

                # 저장 경로 생성
                path = Path(file_path)
                resized_path = path.parent / f"{path.stem}_resized{path.suffix}"

                # 저장
                img.save(resized_path, 'JPEG', quality=quality, optimize=True)

                logger.info(f"Image resized: {file_path} -> {resized_path}")
                return str(resized_path)

        except Exception as e:
            logger.error(f"Image resizing failed: {e}")
            return file_path  # 실패 시 원본 경로 반환

    def get_image_info(self, file_path: str) -> dict:
        """
        이미지 정보 추출

        Args:
            file_path: 이미지 파일 경로

        Returns:
            이미지 정보 딕셔너리
        """
        try:
            with Image.open(file_path) as img:
                return {
                    "format": img.format,
                    "mode": img.mode,
                    "width": img.width,
                    "height": img.height,
                    "size_bytes": os.path.getsize(file_path),
                    "aspect_ratio": round(img.width / img.height, 2)
                }
        except Exception as e:
            logger.error(f"Failed to get image info: {e}")
            return {}

    def cleanup_old_images(self, days: int = 30):
        """
        오래된 이미지 파일 정리

        Args:
            days: 보관 기간 (일)
        """
        import time
        from datetime import datetime, timedelta

        cutoff_time = (datetime.now() - timedelta(days=days)).timestamp()
        deleted_count = 0

        for file_path in self.upload_dir.rglob("*"):
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        deleted_count += 1
                    except Exception as e:
                        logger.error(f"Failed to delete {file_path}: {e}")

        logger.info(f"Cleaned up {deleted_count} old image files")
        return deleted_count


# 전역 인스턴스
image_processor = ImageProcessor()
