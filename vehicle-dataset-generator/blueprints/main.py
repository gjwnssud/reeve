from flask import Blueprint, render_template, jsonify

from database import db
from dataset_generator import dataset_generator
from config import Config

main = Blueprint('main', __name__)
config = Config()

@main.route('/')
def index():
    """메인 페이지"""
    return render_template('index.html', yolo_model=config.YOLO_MODEL.rstrip('.pt'))

# @main.route('/analysis')
# def analysis():
#     """분석 페이지"""
#     return render_template('analysis.html', yolo_model=config.YOLO_MODEL.rstrip('.pt'))

@main.route('/manufacturers')
def get_manufacturers():
    """제조사 목록 API"""
    try:
        manufacturers = db.get_all_manufacturers()
        return jsonify({
            'status': 'success',
            'data': manufacturers
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@main.route('/manufacturers/<manufacturer_code>/models')
def get_models(manufacturer_code):
    """제조사별 모델 목록 API"""
    try:
        models = db.get_models_by_manufacturer(manufacturer_code)
        return jsonify({
            'status': 'success',
            'data': models
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@main.route('/dataset/statistics')
def dataset_statistics():
    """데이터셋 통계 API"""
    try:
        stats = dataset_generator.get_dataset_statistics()
        return jsonify({
            'status': 'success',
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500
