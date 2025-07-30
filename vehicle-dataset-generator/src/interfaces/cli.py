import glob
import os

from dotenv import load_dotenv

from src.core.dataset_manager import DatasetManager
from src.core.vehicle_data_extractor import VehicleDataExtractor

# .env 파일 로드
load_dotenv()


def main():
    """메인 실행 함수"""
    print("=== 차량 데이터셋 생성기 ===")
    print("LLM 파인튜닝용 차량 데이터 추출 도구")
    print()

    # VehicleDataExtractor 인스턴스 생성
    extractor = VehicleDataExtractor()

    # DatasetManager 인스턴스 생성
    dataset_manager = DatasetManager()

    while True:
        print("\n옵션을 선택하세요:")
        print("1. 텍스트 설명으로 차량 분석")
        print("2. 단일 이미지 파일로 차량 분석")
        print("3. 다중 이미지 파일로 차량 분석")
        print("4. 데이터셋 통계 보기")
        print("5. 종료")

        choice = input("\n선택 (1-5): ").strip()

        if choice == "1":
            analyze_text(extractor, dataset_manager)
        elif choice == "2":
            analyze_single_image(extractor, dataset_manager)
        elif choice == "3":
            analyze_multiple_images(extractor, dataset_manager)
        elif choice == "4":
            show_dataset_stats(dataset_manager)
        elif choice == "5":
            print("프로그램을 종료합니다.")
            break
        else:
            print("잘못된 선택입니다.")


def analyze_text(extractor, dataset_manager):
    """텍스트 분석"""
    description = input("차량 설명을 입력하세요: ").strip()
    if not description:
        print("설명을 입력해주세요.")
        return

    print("분석 중...")
    result = extractor.analyze_vehicle_from_text(description)
    result['input'] = description

    print("\n=== 분석 결과 ===")
    print_result(result)

    # 데이터셋 저장 여부 확인
    save = input("\n결과를 데이터셋에 저장하시겠습니까? (y/n): ").strip().lower()
    if save == 'y':
        save_to_dataset([result], dataset_manager, "text")


def analyze_single_image(extractor, dataset_manager):
    """단일 이미지 분석"""
    # 환경변수에서 기본 이미지 디렉토리 가져오기
    default_image_dir = os.getenv('IMAGE_DIR', '../../images_daytime')

    image_path = input(f"이미지 파일 경로를 입력하세요 (또는 상대경로 {default_image_dir}/filename.jpg): ").strip()

    # 상대경로 처리
    if not os.path.isabs(image_path) and not os.path.exists(image_path):
        # 기본 이미지 폴더에서 찾기
        default_path = os.path.join(default_image_dir, image_path)
        if os.path.exists(default_path):
            image_path = default_path

    if not os.path.exists(image_path):
        print("파일이 존재하지 않습니다.")
        return

    print("분석 중...")
    result = extractor.analyze_vehicle_from_image(image_path)
    result['input'] = os.path.basename(image_path)
    result['input_path'] = image_path

    print("\n=== 분석 결과 ===")
    print_result(result)

    # 데이터셋 저장 여부 확인
    save = input("\n결과를 데이터셋에 저장하시겠습니까? (y/n): ").strip().lower()
    if save == 'y':
        save_to_dataset([result], dataset_manager, "image")


def analyze_multiple_images(extractor, dataset_manager):
    """다중 이미지 분석"""
    print("다중 이미지 분석 옵션:")
    print("1. 폴더 내 모든 이미지 분석")
    print("2. 파일 경로들을 직접 입력")

    option = input("선택 (1-2): ").strip()

    if option == "1":
        analyze_folder_images(extractor, dataset_manager)
    elif option == "2":
        analyze_manual_images(extractor, dataset_manager)
    else:
        print("잘못된 선택입니다.")


def analyze_folder_images(extractor, dataset_manager):
    """폴더 내 이미지들 분석"""
    # 환경변수에서 기본 이미지 디렉토리 가져오기
    default_image_dir = os.getenv('IMAGE_DIR', '../../images_daytime')

    folder_path = input(f"이미지 폴더 경로를 입력하세요 (기본값: {default_image_dir}): ").strip()

    if not folder_path:
        folder_path = default_image_dir

    if not os.path.exists(folder_path):
        print("폴더가 존재하지 않습니다.")
        return

    # 이미지 파일들 찾기
    extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.gif']
    image_files = []

    for ext in extensions:
        pattern = os.path.join(folder_path, ext)
        image_files.extend(glob.glob(pattern))
        # 대소문자 구분 없이
        pattern_upper = os.path.join(folder_path, ext.upper())
        image_files.extend(glob.glob(pattern_upper))

    if not image_files:
        print("폴더에서 이미지 파일을 찾을 수 없습니다.")
        return

    print(f"찾은 이미지 파일: {len(image_files)}개")

    # 분석할 파일 수 제한
    max_files = input(f"분석할 파일 수를 입력하세요 (최대 {len(image_files)}개, 엔터시 전체): ").strip()

    if max_files and max_files.isdigit():
        max_files = int(max_files)
        image_files = image_files[:max_files]

    print(f"{len(image_files)}개 파일 분석을 시작합니다...")

    def progress_callback(current, total, filename):
        print(f"진행률: {current + 1}/{total} - {filename}")

    results = extractor.analyze_multiple_images(image_files, progress_callback)

    print(f"\n=== 분석 완료 ({len(results)}개) ===")
    print_multiple_results(results)

    # 데이터셋 저장 여부 확인
    save = input("\n결과를 데이터셋에 저장하시겠습니까? (y/n): ").strip().lower()
    if save == 'y':
        save_to_dataset(results, dataset_manager, "image")


def analyze_manual_images(extractor, dataset_manager):
    """수동으로 입력된 이미지들 분석"""
    print("이미지 파일 경로들을 입력하세요 (빈 줄 입력시 종료):")

    image_paths = []
    while True:
        path = input(f"{len(image_paths) + 1}. ").strip()
        if not path:
            break

        # 상대경로 처리
        if not os.path.isabs(path) and not os.path.exists(path):
            default_image_dir = os.getenv('IMAGE_DIR', '../../images_daytime')
            default_path = os.path.join(default_image_dir, path)
            if os.path.exists(default_path):
                path = default_path

        if os.path.exists(path):
            image_paths.append(path)
        else:
            print(f"파일을 찾을 수 없습니다: {path}")

    if not image_paths:
        print("입력된 이미지가 없습니다.")
        return

    print(f"{len(image_paths)}개 파일 분석을 시작합니다...")

    def progress_callback(current, total, filename):
        print(f"진행률: {current + 1}/{total} - {filename}")

    results = extractor.analyze_multiple_images(image_paths, progress_callback)

    print(f"\n=== 분석 완료 ({len(results)}개) ===")
    print_multiple_results(results)

    # 데이터셋 저장 여부 확인
    save = input("\n결과를 데이터셋에 저장하시겠습니까? (y/n): ").strip().lower()
    if save == 'y':
        save_to_dataset(results, dataset_manager, "image")


def print_result(result):
    """단일 결과 출력"""
    if 'error' in result:
        print(f"❌ 오류: {result['error']}")
    else:
        brand_kr = result.get('brand_kr', 'N/A')
        brand_en = result.get('brand_en', 'N/A')
        model_kr = result.get('model_kr', 'N/A')
        model_en = result.get('model_en', 'N/A')
        year = result.get('year', 'N/A')
        year_info = result.get('year_info', 'N/A')
        confidence = result.get('confidence', 0)

        print(f"🏷️  브랜드 (한글): {brand_kr}")
        print(f"🏷️  브랜드 (영문): {brand_en}")
        print(f"🚗 차종 (한글): {model_kr}")
        print(f"🚗 차종 (영문): {model_en}")
        print(f"📅 연식: {year}")
        if year_info and year_info != 'N/A':
            print(f"📋 연식 근거: {year_info}")
        print(f"📊 신뢰도: {confidence}%")


def print_multiple_results(results):
    """다중 결과 출력"""
    success_count = 0
    error_count = 0

    for i, result in enumerate(results):
        filename = result.get('input', f'파일_{i + 1}')
        print(f"\n📸 {i + 1}. {filename}")

        if 'error' in result:
            print(f"   ❌ 오류: {result['error']}")
            error_count += 1
        else:
            brand_kr = result.get('brand_kr', 'N/A')
            brand_en = result.get('brand_en', 'N/A')
            model_kr = result.get('model_kr', 'N/A')
            model_en = result.get('model_en', 'N/A')
            year = result.get('year', 'N/A')
            confidence = result.get('confidence', 0)

            print(f"   🏷️ 브랜드: {brand_kr} ({brand_en})")
            print(f"   🚗 차종: {model_kr} ({model_en})")
            print(f"   📅 연식: {year}")
            print(f"   📊 신뢰도: {confidence}%")
            success_count += 1

    print(f"\n=== 분석 요약 ===")
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {error_count}개")
    print(f"📊 전체: {len(results)}개")


def save_to_dataset(results, dataset_manager, source_type):
    """데이터셋에 저장"""
    try:
        save_info = dataset_manager.save_results(results, source_type)

        if save_info:
            print(f"\n✅ 데이터셋 저장 완료!")
            print(f"저장 파일: {os.path.basename(save_info['saved_file'])}")
            print(f"새로 추가된 항목: {save_info['new_items']}개")
            print(f"전체 항목 수: {save_info['total_items']}개")
            print(f"파일 크기: {save_info['file_size_mb']}MB")
        else:
            print("❌ 데이터셋 저장 실패")

    except Exception as e:
        print(f"❌ 저장 중 오류: {e}")


def show_dataset_stats(dataset_manager):
    """데이터셋 통계 표시"""
    try:
        stats = dataset_manager.get_dataset_stats()

        print("\n=== 데이터셋 통계 ===")
        print(f"📁 데이터셋 경로: {stats['dataset_path']}")
        print(f"📄 파일 수: {stats['total_files']}개")
        print(f"📊 전체 항목 수: {stats['total_items']}개")
        print(f"💾 전체 크기: {stats['total_size_mb']}MB")

        if stats['total_files'] > 0:
            avg_items = stats['total_items'] / stats['total_files']
            print(f"📈 파일당 평균 항목: {avg_items:.1f}개")

    except Exception as e:
        print(f"❌ 통계 조회 중 오류: {e}")


if __name__ == "__main__":
    main()
