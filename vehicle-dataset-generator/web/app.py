import os

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify

from src.core.dataset_manager import DatasetManager
from src.core.vehicle_data_extractor import VehicleDataExtractor

# .env 파일 로드
load_dotenv()

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

extractor = VehicleDataExtractor()
dataset_manager = DatasetManager()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analyze_text', methods=['POST'])
def analyze_text():
    try:
        data = request.get_json()
        text = data.get('text', '')

        if not text.strip():
            return jsonify({'error': '분석할 텍스트를 입력해주세요.'}), 400

        result = extractor.analyze_vehicle_from_text(text)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_multiple_images', methods=['POST'])
def analyze_multiple_images():
    """다중 이미지 분석"""
    try:
        if 'images' not in request.files:
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        files = request.files.getlist('images')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': '이미지 파일들을 선택해주세요.'}), 400

        results = []
        temp_files = []

        try:
            # 각 파일 처리
            for i, file in enumerate(files):
                if file.filename == '':
                    continue

                # 임시 파일로 저장
                temp_path = f"temp_{i}_{file.filename}"
                file.save(temp_path)
                temp_files.append(temp_path)

                # 분석 실행
                result = extractor.analyze_vehicle_from_image(temp_path)
                result['input'] = file.filename
                results.append(result)

            return jsonify({
                'results': results,
                'total_count': len(results),
                'success_count': len([r for r in results if 'error' not in r])
            })

        finally:
            # 임시 파일들 삭제
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/save_to_dataset', methods=['POST'])
def save_to_dataset():
    """결과를 데이터셋에 저장"""
    try:
        data = request.get_json()
        results = data.get('results', [])

        if not results:
            return jsonify({'error': '저장할 결과가 없습니다.'}), 400

        # 데이터셋에 저장
        save_info = dataset_manager.save_results(results, "image")

        if save_info:
            return jsonify({
                'message': '데이터셋 저장 완료',
                'save_info': save_info
            })
        else:
            return jsonify({'error': '데이터셋 저장 실패'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/dataset_stats')
def get_dataset_stats():
    """데이터셋 통계 조회"""
    try:
        stats = dataset_manager.get_dataset_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/analyze_image', methods=['POST'])
def analyze_image():
    try:
        if 'image' not in request.files:
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '이미지 파일을 선택해주세요.'}), 400

        # 임시 파일로 저장
        temp_path = f"temp_{file.filename}"
        file.save(temp_path)

        try:
            result = extractor.analyze_vehicle_from_image(temp_path)
            return jsonify(result)
        finally:
            # 임시 파일 삭제
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=4000)
