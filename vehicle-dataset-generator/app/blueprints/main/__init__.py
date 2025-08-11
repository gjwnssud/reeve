"""
Main Blueprint
메인 페이지 관련 라우트
"""

from flask import Blueprint

main_bp = Blueprint('main', __name__)

from . import routes
