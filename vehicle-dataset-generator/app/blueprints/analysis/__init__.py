"""
Analysis Blueprint
데이터 분석 관련 라우트
"""

from flask import Blueprint

analysis_bp = Blueprint('analysis', __name__)

from . import routes
