"""
로컬 Vision LLM 서비스
LLaVA-1.6 기반 차량 이미지 분석 (Phase 2 - 폐쇄망 환경)
"""
import logging
from typing import Dict, Optional
from pathlib import Path

from studio.config import settings

logger = logging.getLogger(__name__)


class LocalVisionLLM:
    """LLaVA-1.6 기반 로컬 Vision LLM"""

    def __init__(self):
        """LLaVA 모델 초기화"""
        self.model = None
        self.clip_model_path = None

        # llama-cpp-python 사용
        try:
            from llama_cpp import Llama
            from llama_cpp.llama_chat_format import Llava15ChatHandler

            model_path = Path(settings.llava_model_path)

            # 모델 파일 확인
            model_file = model_path / "llava-v1.6-mistral-7b.Q4_K_M.gguf"
            clip_file = model_path / "mmproj-model-f16.gguf"

            if not model_file.exists():
                logger.warning(f"LLaVA model not found: {model_file}")
                logger.info("Run 'python scripts/download_models.py' to download")
                return

            if not clip_file.exists():
                logger.warning(f"CLIP projector not found: {clip_file}")
                return

            # LLaVA 모델 로드
            logger.info(f"Loading LLaVA model from {model_file}...")

            chat_handler = Llava15ChatHandler(
                clip_model_path=str(clip_file)
            )

            self.model = Llama(
                model_path=str(model_file),
                chat_handler=chat_handler,
                n_ctx=settings.llava_n_ctx,
                n_gpu_layers=settings.llava_n_gpu_layers,
                verbose=False
            )

            self.clip_model_path = str(clip_file)

            logger.info("LLaVA model loaded successfully")

        except ImportError:
            logger.error("llama-cpp-python not installed")
            logger.info("Install: pip install llama-cpp-python")
        except Exception as e:
            logger.error(f"Failed to load LLaVA model: {e}")

    async def analyze_vehicle_image(
        self,
        image_path: str,
        additional_context: Optional[str] = None
    ) -> Dict:
        """
        차량 이미지 분석 (로컬 LLM 사용)

        Args:
            image_path: 분석할 이미지 경로
            additional_context: 추가 컨텍스트 정보

        Returns:
            분석 결과 딕셔너리
        """
        if not self.model:
            raise ValueError("LLaVA model not loaded")

        try:
            # 프롬프트 구성
            prompt = self._build_prompt(additional_context)

            # 이미지를 데이터 URL로 변환
            image_data_url = self._image_to_data_url(image_path)

            # LLaVA 추론
            response = self.model.create_chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}}
                        ]
                    }
                ],
                temperature=0.2,
                max_tokens=500
            )

            # 응답 파싱
            result = self._parse_response(response)

            logger.info(f"Local LLM analysis completed: {image_path}")
            return result

        except Exception as e:
            logger.error(f"Error analyzing image with local LLM {image_path}: {e}")
            raise

    def _image_to_data_url(self, image_path: str) -> str:
        """이미지를 base64 데이터 URL로 변환"""
        import base64
        from PIL import Image
        import io

        # 이미지 로드 및 리사이징 (성능 최적화)
        img = Image.open(image_path)

        # 최대 크기 제한
        max_size = (1024, 1024)
        img.thumbnail(max_size, Image.Resampling.LANCZOS)

        # JPEG로 변환
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        img_bytes = buffer.getvalue()

        # Base64 인코딩
        img_b64 = base64.b64encode(img_bytes).decode('utf-8')

        return f"data:image/jpeg;base64,{img_b64}"

    def _build_prompt(self, additional_context: Optional[str] = None) -> str:
        """분석용 프롬프트 생성"""
        base_prompt = """이미지에서 차량의 제조사, 모델, 연식을 식별해주세요.

다음 형식으로 정확하게 답변해주세요:

제조사: [제조사명 - 한글 또는 영문]
모델: [모델명 - 한글 또는 영문]
연식: [연식 - YYYY 형식, 불확실하면 "알 수 없음"]
신뢰도: [0.0-1.0 사이의 숫자]

추가 정보:
- 제조사는 "현대", "기아", "BMW", "벤츠" 등으로 표기
- 모델은 구체적으로 "소나타", "K5", "3시리즈" 등으로 표기
- 연식이 명확하지 않으면 "알 수 없음"으로 표기
- 신뢰도는 식별의 확실성 정도 (1.0이 가장 확실)

차량이 명확하게 보이지 않거나 식별이 불가능한 경우:
제조사: 알 수 없음
모델: 알 수 없음
연식: 알 수 없음
신뢰도: 0.0
"""

        if additional_context:
            base_prompt += f"\n\n참고 정보:\n{additional_context}"

        return base_prompt

    def _parse_response(self, response) -> Dict:
        """LLaVA 응답 파싱"""
        try:
            content = response['choices'][0]['message']['content']

            # 기본 값
            result = {
                "manufacturer": None,
                "model": None,
                "year": None,
                "confidence": 0.0,
                "raw_response": content
            }

            # 텍스트 파싱
            lines = content.strip().split('\n')
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    key = key.strip()
                    value = value.strip()

                    if '제조사' in key:
                        result["manufacturer"] = value if value != "알 수 없음" else None
                    elif '모델' in key:
                        result["model"] = value if value != "알 수 없음" else None
                    elif '연식' in key:
                        result["year"] = value if value != "알 수 없음" else None
                    elif '신뢰도' in key:
                        try:
                            result["confidence"] = float(value)
                        except ValueError:
                            result["confidence"] = 0.0

            return result

        except Exception as e:
            logger.error(f"Error parsing LLaVA response: {e}")
            return {
                "manufacturer": None,
                "model": None,
                "year": None,
                "confidence": 0.0,
                "raw_response": str(response),
                "error": str(e)
            }

    async def batch_analyze(
        self,
        image_paths: list[str],
        progress_callback: Optional[callable] = None
    ) -> list[Dict]:
        """
        여러 이미지 일괄 분석

        Args:
            image_paths: 이미지 경로 리스트
            progress_callback: 진행상황 콜백 함수

        Returns:
            분석 결과 리스트
        """
        results = []

        for idx, image_path in enumerate(image_paths):
            try:
                result = await self.analyze_vehicle_image(image_path)
                result["image_path"] = image_path
                results.append(result)

                if progress_callback:
                    progress_callback(idx + 1, len(image_paths))

            except Exception as e:
                logger.error(f"Failed to analyze {image_path}: {e}")
                results.append({
                    "image_path": image_path,
                    "error": str(e),
                    "manufacturer": None,
                    "model": None,
                    "year": None,
                    "confidence": 0.0
                })

        return results


# 전역 인스턴스
local_llm_service = LocalVisionLLM()
