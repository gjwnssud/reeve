import os
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

from PIL import Image, ImageTk

from src.core.dataset_manager import DatasetManager
from src.core.vehicle_data_extractor import VehicleDataExtractor


class VehicleDatasetGeneratorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("차량 데이터셋 생성기")
        self.root.geometry("1400x1000")  # 더 큰 기본 사이즈
        self.root.minsize(1200, 800)  # 최소 사이즈 설정

        # 다크 테마 대응 색상 설정
        self.setup_colors()

        # 배경색 설정
        self.root.configure(bg=self.colors['bg_main'])

        # VehicleDataExtractor 인스턴스
        self.extractor = VehicleDataExtractor()

        # DatasetManager 인스턴스
        self.dataset_manager = DatasetManager()

        # 스타일 설정
        self.setup_styles()

        # GUI 구성
        self.create_widgets()

        # 결과 저장용
        self.last_result = None
        self.selected_image_paths = []  # 다중 이미지 경로

    def setup_colors(self):
        """다크 테마 대응 색상 설정"""
        # 시스템 다크 모드 감지 시도
        try:
            # macOS 다크 모드 감지
            import subprocess
            result = subprocess.run(['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                                    capture_output=True, text=True, timeout=1)
            is_dark = result.stdout.strip() == 'Dark'
        except:
            # Windows/Linux 다크 모드 감지 시도
            try:
                import tkinter.ttk as ttk_test
                test_style = ttk_test.Style()
                # 시스템 테마에서 다크모드 감지
                current_theme = test_style.theme_use()
                is_dark = 'dark' in current_theme.lower() or 'black' in current_theme.lower()
            except:
                # 기본값: 라이트 모드
                is_dark = False

        if is_dark:
            # 다크 테마 색상 (가독성 강화)
            self.colors = {
                'bg_main': '#1e1e1e',
                'bg_secondary': '#2d2d2d',
                'bg_input': '#383838',
                'bg_button': '#0078d4',
                'bg_button_hover': '#106ebe',
                'text_primary': '#ffffff',
                'text_secondary': '#e1e1e1',
                'text_accent': '#00d4ff',
                'border': '#484848',
                'success': '#107c10',
                'error': '#d13438'
            }
        else:
            # 라이트 테마 색상
            self.colors = {
                'bg_main': '#f5f5f5',
                'bg_secondary': '#ffffff',
                'bg_input': '#ffffff',
                'bg_button': '#0078d4',
                'bg_button_hover': '#106ebe',
                'text_primary': '#323130',
                'text_secondary': '#605e5c',
                'text_accent': '#0078d4',
                'border': '#e1dfdd',
                'success': '#107c10',
                'error': '#d13438'
            }

    def setup_styles(self):
        """GUI 스타일 설정"""
        style = ttk.Style()

        # 테마 선택 (다크 모드에 따라)
        if self.colors['bg_main'] == '#2b2b2b':
            style.theme_use('alt')  # 다크 모드에 더 적합
        else:
            style.theme_use('clam')

        # 버튼 스타일 설정
        style.configure('Action.TButton',
                        padding=(20, 12),
                        font=('Arial', 12, 'bold'),
                        background=self.colors['bg_button'],
                        foreground='white',
                        borderwidth=0,
                        focuscolor='none')

        style.map('Action.TButton',
                  background=[('active', self.colors['bg_button_hover']),
                              ('pressed', self.colors['bg_button'])])

        # 노트북 스타일 설정
        style.configure('TNotebook',
                        background=self.colors['bg_main'],
                        borderwidth=0)

        style.configure('TNotebook.Tab',
                        padding=(20, 10),
                        font=('Arial', 11),
                        background=self.colors['bg_secondary'],
                        foreground=self.colors['text_primary'])

        # 프레임 스타일
        style.configure('Title.TFrame',
                        background=self.colors['bg_secondary'],
                        relief='flat')

    def create_widgets(self):
        """GUI 위젯 생성"""
        # 전체 스크롤 가능한 캔버스 생성
        self.main_canvas = tk.Canvas(self.root, bg=self.colors['bg_main'])
        self.scrollbar = ttk.Scrollbar(self.root, orient="vertical", command=self.main_canvas.yview)
        self.scrollable_frame = tk.Frame(self.main_canvas, bg=self.colors['bg_main'])

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        )

        self.main_canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.main_canvas.configure(yscrollcommand=self.scrollbar.set)

        # 마우스 휠 이벤트 바인딩 (모든 OS 지원)
        def _on_mousewheel(event):
            if event.delta:
                self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                # macOS의 경우
                self.main_canvas.yview_scroll(int(-1 * event.delta), "units")

        def _bind_mousewheel(event):
            self.main_canvas.bind_all("<MouseWheel>", _on_mousewheel)  # Windows
            self.main_canvas.bind_all("<Button-4>", lambda e: self.main_canvas.yview_scroll(-1,
                                                                                            "units"))  # Linux/macOS
            self.main_canvas.bind_all("<Button-5>", lambda e: self.main_canvas.yview_scroll(1,
                                                                                            "units"))  # Linux/macOS

        def _unbind_mousewheel(event):
            self.main_canvas.unbind_all("<MouseWheel>")
            self.main_canvas.unbind_all("<Button-4>")
            self.main_canvas.unbind_all("<Button-5>")

        self.main_canvas.bind('<Enter>', _bind_mousewheel)
        self.main_canvas.bind('<Leave>', _unbind_mousewheel)

        # 스크롤바와 캔버스 배치
        self.main_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # 메인 타이틀
        title_frame = ttk.Frame(self.scrollable_frame, style='Title.TFrame')
        title_frame.pack(fill='x', padx=15, pady=10)

        title_label = tk.Label(title_frame,
                               text="🚗 차량 데이터셋 생성기",
                               font=('Arial', 20, 'bold'),
                               bg=self.colors['bg_secondary'],
                               fg=self.colors['text_accent'])
        title_label.pack(pady=20)

        # 이미지 분석 영역만 생성
        self.create_image_area()

        # 결과 표시 영역
        self.create_result_area()

    def create_image_area(self):
        """이미지 분석 영역 생성"""
        image_frame = tk.LabelFrame(self.scrollable_frame, text="이미지 분석",
                                    font=('Arial', 16, 'bold'),
                                    bg=self.colors['bg_main'],
                                    fg=self.colors['text_accent'],
                                    bd=2, relief='groove')
        image_frame.pack(fill='x', padx=20, pady=15)

        # 설명 레이블
        desc_label = tk.Label(image_frame,
                              text="차량 이미지를 선택하고 분석하세요 (다중 선택 가능)",
                              font=('Arial', 12),
                              bg=self.colors['bg_main'],
                              fg=self.colors['text_secondary'])
        desc_label.pack(pady=20)

        # 파일 선택 버튼
        select_file_btn = ttk.Button(image_frame,
                                     text="📁 이미지 파일 선택 (다중 선택 가능)",
                                     style='Action.TButton',
                                     command=self.select_image_files)
        select_file_btn.pack(pady=15)

        # 선택된 파일 목록 표시
        list_frame = tk.Frame(image_frame, bg=self.colors['bg_main'])
        list_frame.pack(fill='x', padx=15, pady=10)

        self.file_list_text = scrolledtext.ScrolledText(list_frame,
                                                        height=3,  # 높이 줄임
                                                        font=('Arial', 11),
                                                        bg=self.colors['bg_input'],
                                                        fg=self.colors['text_primary'],
                                                        insertbackground=self.colors[
                                                            'text_primary'],
                                                        selectbackground=self.colors['text_accent'],
                                                        wrap='word')
        self.file_list_text.pack(fill='both', expand=True)

        # 이미지 미리보기 (크기 대폭 축소)
        self.image_preview_frame = tk.Frame(image_frame,
                                            bg=self.colors['bg_input'],
                                            relief='sunken', bd=2)
        self.image_preview_frame.pack(fill='x', padx=15, pady=15, ipady=60)  # ipady 120 → 60으로 축소

        self.image_preview_label = tk.Label(self.image_preview_frame,
                                            text="이미지를 선택하면 여기에 미리보기가 표시됩니다",
                                            bg=self.colors['bg_input'],
                                            fg=self.colors['text_secondary'],
                                            font=('Arial', 12))
        self.image_preview_label.pack(expand=True)

        # 분석 버튼
        analyze_btn = ttk.Button(image_frame,
                                 text="🔍 이미지 분석 시작",
                                 style='Action.TButton',
                                 command=self.analyze_images)
        analyze_btn.pack(pady=20)

    def create_result_area(self):
        """결과 표시 영역 생성"""
        result_frame = tk.LabelFrame(self.scrollable_frame, text="분석 결과",
                                     font=('Arial', 16, 'bold'),
                                     bg=self.colors['bg_main'],
                                     fg=self.colors['text_accent'],
                                     bd=2, relief='groove')
        result_frame.pack(fill='both', expand=True, padx=20, pady=15)

        # 결과 텍스트 영역 (높이 고정)
        self.result_text = scrolledtext.ScrolledText(result_frame,
                                                     height=12,  # 고정 높이로 설정
                                                     font=('Consolas', 11),
                                                     bg=self.colors['bg_input'],
                                                     fg=self.colors['text_primary'],
                                                     insertbackground=self.colors['text_primary'],
                                                     selectbackground=self.colors['text_accent'])
        self.result_text.pack(fill='x', padx=20, pady=(20, 10))  # expand=True 제거

        # 버튼 프레임 (항상 보이도록 설정)
        button_frame = tk.Frame(result_frame, bg=self.colors['bg_main'], height=60)
        button_frame.pack(fill='x', padx=20, pady=15)
        button_frame.pack_propagate(False)  # 최소 높이 유지

        # 데이터셋 저장 버튼 (새로 추가)
        save_dataset_btn = ttk.Button(button_frame,
                                      text="💾 데이터셋에 저장",
                                      style='Action.TButton',
                                      command=self.save_to_dataset)
        save_dataset_btn.pack(side='left', padx=(0, 15))

        # 통계 버튼
        stats_btn = ttk.Button(button_frame,
                               text="📊 데이터셋 통계",
                               style='Action.TButton',
                               command=self.show_dataset_stats)
        stats_btn.pack(side='left', padx=(0, 15))

        # 결과 클리어 버튼
        clear_btn = ttk.Button(button_frame,
                               text="🗑️ 결과 지우기",
                               style='Action.TButton',
                               command=self.clear_result)
        clear_btn.pack(side='right')

    def select_image_files(self):
        """다중 이미지 파일 선택"""
        # 환경변수에서 이미지 디렉토리 가져오기
        default_image_dir = os.getenv('IMAGE_DIR', '../../images_daytime')

        file_paths = filedialog.askopenfilenames(
            title="차량 이미지 선택 (다중 선택 가능)",
            filetypes=[
                ("이미지 파일", "*.jpg *.jpeg *.png *.bmp *.gif"),
                ("모든 파일", "*.*")
            ],
            initialdir=default_image_dir  # 환경변수 사용
        )

        if file_paths:
            self.selected_image_paths = list(file_paths)
            self.update_file_list()
            self.show_first_image_preview()

    def update_file_list(self):
        """선택된 파일 목록 업데이트"""
        self.file_list_text.delete('1.0', 'end')
        if self.selected_image_paths:
            file_list = "\n".join([f"{i + 1}. {os.path.basename(path)}"
                                   for i, path in enumerate(self.selected_image_paths)])
            self.file_list_text.insert('1.0',
                                       f"선택된 파일 ({len(self.selected_image_paths)}개):\n{file_list}")

    def show_first_image_preview(self):
        """첫 번째 이미지 미리보기 표시"""
        if self.selected_image_paths:
            self.show_image_preview(self.selected_image_paths[0])

    def show_image_preview(self, image_path):
        """이미지 미리보기 표시"""
        try:
            # 이미지 로드 및 리사이즈
            image = Image.open(image_path)
            # 미리보기 크기 조정
            image.thumbnail((400, 200), Image.Resampling.LANCZOS)

            # Tkinter용 이미지로 변환
            photo = ImageTk.PhotoImage(image)

            # 기존 미리보기 제거
            for widget in self.image_preview_frame.winfo_children():
                widget.destroy()

            # 새 이미지 표시
            self.image_preview_label = tk.Label(self.image_preview_frame,
                                                image=photo,
                                                bg=self.colors['bg_input'])
            self.image_preview_label.image = photo  # 참조 유지
            self.image_preview_label.pack(expand=True)

        except Exception as e:
            messagebox.showerror("오류", f"이미지 미리보기 실패: {str(e)}")

    def analyze_images(self):
        """다중 이미지 분석 실행"""
        if not self.selected_image_paths:
            messagebox.showwarning("경고", "분석할 이미지를 선택해주세요.")
            return

        # 존재하지 않는 파일 확인
        valid_paths = []
        for path in self.selected_image_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                messagebox.showwarning("경고", f"파일을 찾을 수 없습니다: {os.path.basename(path)}")

        if not valid_paths:
            messagebox.showerror("오류", "유효한 이미지 파일이 없습니다.")
            return

        self.show_loading(f"{len(valid_paths)}개 이미지 분석 중...")

        # 별도 스레드에서 분석 실행
        thread = threading.Thread(target=self._analyze_images_thread, args=(valid_paths,))
        thread.daemon = True
        thread.start()

    def _analyze_images_thread(self, image_paths):
        """다중 이미지 분석 스레드"""
        try:
            def progress_callback(current, total, filename):
                self.root.after(0, self.update_progress, current, total, filename)

            results = self.extractor.analyze_multiple_images(image_paths, progress_callback)
            self.root.after(0, self.display_multiple_results, results)
        except Exception as e:
            self.root.after(0, self.show_error, f"이미지 분석 오류: {str(e)}")

    def update_progress(self, current, total, filename):
        """진행률 업데이트"""
        progress_text = f"{current + 1}/{total} - {filename} 분석 중..."
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', f"🔄 {progress_text}\n잠시만 기다려주세요...")
        self.root.update()

    def display_multiple_results(self, results):
        """다중 분석 결과 표시"""
        self.last_result = results  # 다중 결과 저장

        self.result_text.delete('1.0', 'end')

        # 헤더
        header = f"=== 다중 이미지 분석 결과 ({len(results)}개) ===\n\n"
        self.result_text.insert('end', header)

        # 각 결과 표시
        for i, result in enumerate(results):
            filename = result.get('input', f'이미지_{i + 1}')
            self.result_text.insert('end', f"📸 {i + 1}. {filename}\n")

            if 'error' in result:
                self.result_text.insert('end', f"   ❌ 오류: {result['error']}\n\n")
            else:
                brand_kr = result.get('brand_kr', 'N/A')
                brand_en = result.get('brand_en', 'N/A')
                model_kr = result.get('model_kr', 'N/A')
                model_en = result.get('model_en', 'N/A')
                year = result.get('year', 'N/A')
                confidence = result.get('confidence', 0)

                self.result_text.insert('end', f"   🏷️ 브랜드: {brand_kr} ({brand_en})\n")
                self.result_text.insert('end', f"   🚗 차종: {model_kr} ({model_en})\n")
                self.result_text.insert('end', f"   📅 연식: {year}\n")
                self.result_text.insert('end', f"   📊 신뢰도: {confidence}%\n\n")

        # 요약 정보
        success_count = len([r for r in results if 'error' not in r])
        error_count = len(results) - success_count

        self.result_text.insert('end', f"\n=== 분석 요약 ===\n")
        self.result_text.insert('end', f"✅ 성공: {success_count}개\n")
        self.result_text.insert('end', f"❌ 실패: {error_count}개\n")
        self.result_text.insert('end', f"📊 전체: {len(results)}개\n")

    def show_loading(self, message):
        """로딩 메시지 표시"""
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', f"🔄 {message}\n잠시만 기다려주세요...")
        self.root.update()

    def show_error(self, error_message):
        """오류 메시지 표시"""
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', f"❌ {error_message}")
        messagebox.showerror("분석 오류", error_message)

    def save_to_dataset(self):
        """결과를 데이터셋에 저장"""
        if not self.last_result:
            messagebox.showwarning("경고", "저장할 결과가 없습니다.")
            return

        try:
            # 리스트인지 확인 (다중 결과)
            if isinstance(self.last_result, list):
                results_to_save = self.last_result
            else:
                results_to_save = [self.last_result]

            # 데이터셋에 저장
            save_info = self.dataset_manager.save_results(results_to_save, "image")

            if save_info:
                message = f"""데이터셋 저장 완료!

저장 파일: {os.path.basename(save_info['saved_file'])}
새로 추가된 항목: {save_info['new_items']}개
전체 항목 수: {save_info['total_items']}개
파일 크기: {save_info['file_size_mb']}MB"""

                messagebox.showinfo("저장 완료", message)
            else:
                messagebox.showerror("저장 실패", "데이터셋 저장 중 오류가 발생했습니다.")

        except Exception as e:
            messagebox.showerror("저장 오류", f"데이터셋 저장 중 오류:\n{str(e)}")

    def show_dataset_stats(self):
        """데이터셋 통계 표시"""
        try:
            stats = self.dataset_manager.get_dataset_stats()

            message = f"""데이터셋 통계

📁 데이터셋 경로: {stats['dataset_path']}
📄 파일 수: {stats['total_files']}개
📊 전체 항목 수: {stats['total_items']}개
💾 전체 크기: {stats['total_size_mb']}MB"""

            messagebox.showinfo("데이터셋 통계", message)

        except Exception as e:
            messagebox.showerror("통계 오류", f"통계 정보 조회 중 오류:\n{str(e)}")

    def clear_result(self):
        """결과 영역 클리어"""
        self.result_text.delete('1.0', 'end')
        self.last_result = None


def main():
    """메인 함수"""
    # 환경변수 체크
    if not os.getenv('OPENAI_API_KEY'):
        messagebox.showerror("설정 오류",
                             "OPENAI_API_KEY 환경변수가 설정되지 않았습니다.\n"
                             ".env 파일을 확인해주세요.")
        return

    root = tk.Tk()
    app = VehicleDatasetGeneratorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
