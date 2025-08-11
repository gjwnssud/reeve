"""
Vehicle Info Blueprint
차량 정보 관련 라우트
"""

from flask import Blueprint

vehicle_info_bp = Blueprint('vehicle_info', __name__)

from . import routes
