"""
Identifier 서비스의 OpenAPI 스키마를 JSON으로 stdout에 덤프.

Frontend TS 타입 생성(scripts/gen-types.ts)에서 사용.
identifier.main 의 라우트 정의는 torch/ultralytics 등 ML 스택에 의존하므로,
이 스크립트는 해당 스택이 설치된 환경(Identifier 컨테이너 등)에서만 실행 가능.
"""
from __future__ import annotations

import json
import os
import sys

# 모델 파일 존재 여부와 무관하게 import가 가능하도록 lazy 경로로 진행.
# FastAPI 앱 객체를 임포트만 하고 lifespan은 실행하지 않는다.
os.environ.setdefault("IDENTIFIER_SKIP_STARTUP", "1")

from identifier.main import app  # noqa: E402


def dump() -> dict:
    return app.openapi()


if __name__ == "__main__":
    json.dump(dump(), sys.stdout, ensure_ascii=False)
