"""
Studio 서비스의 OpenAPI 스키마를 JSON으로 stdout에 덤프하는 경량 엔트리.

목적: frontend TS 타입 생성(scripts/gen-types.ts)에서 torch, DB 드라이버 import 없이
      FastAPI 라우터 스키마만 빠르게 추출하기 위함.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from fastapi import FastAPI

from studio.api import admin, analyze, finetune


def build_app() -> FastAPI:
    app = FastAPI(
        title="Reeve Studio API",
        description="Studio 서비스 OpenAPI (타입 생성 전용)",
        version="1.0.0",
    )
    app.include_router(admin.router)
    app.include_router(analyze.router)
    app.include_router(finetune.router)
    return app


def dump() -> dict[str, Any]:
    return build_app().openapi()


if __name__ == "__main__":
    json.dump(dump(), sys.stdout, ensure_ascii=False)
