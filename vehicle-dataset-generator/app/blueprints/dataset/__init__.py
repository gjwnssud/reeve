"""
Dataset Blueprint
데이터셋 생성 관련 라우트
"""

from flask import Blueprint

dataset_bp = Blueprint('dataset', __name__)

from . import routes
