#!/usr/bin/env python3
"""
Vehicle Dataset Generator - Main Entry Point
Flask 웹 애플리케이션 실행을 위한 엔트리 포인트
"""

import os
import sys
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app import create_app

def main():
    """메인 실행 함수"""
    app = create_app()
    
    # 개발 환경에서는 디버그 모드 활성화
    debug_mode = os.getenv('FLASK_ENV', 'development') == 'development'
    
    print("🚗 Vehicle Dataset Generator Starting...")
    print(f"📍 Running in {'DEBUG' if debug_mode else 'PRODUCTION'} mode")
    print(f"🌐 Access the application at: http://localhost:4000")
    
    app.run(
        host='0.0.0.0',
        port=4000,
        debug=debug_mode,
        use_reloader=debug_mode
    )

if __name__ == '__main__':
    main()
