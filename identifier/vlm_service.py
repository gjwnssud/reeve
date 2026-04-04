"""
VLM (Vision Language Model) 서비스
Ollama API를 통한 Qwen3-VL 기반 차량 판별
"""
import base64
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import List, Optional

import httpx
from PIL import Image

from identifier.config import settings

logger = logging.getLogger(__name__)


@dataclass
class VLMCandidate:
    """Qdrant에서 가져온 후보 정보 (VLM 프롬프트용)"""
    manufacturer_id: int
    model_id: int
    manufacturer_korean: str
    manufacturer_english: str
    model_korean: str
    model_english: str
    similarity: float


@dataclass
class VLMResult:
    """VLM 판별 결과"""
    selected_index: Optional[int]       # 선택된 후보 인덱스 (None이면 해당없음)
    manufacturer_id: Optional[int]
    model_id: Optional[int]
    manufacturer_korean: Optional[str]
    manufacturer_english: Optional[str]
    model_korean: Optional[str]
    model_english: Optional[str]
    confidence: float                    # VLM 자체 판단 신뢰도
    reasoning: str                       # VLM 판단 이유 (디버깅용)
    raw_response: str                    # 원본 응답


class VLMService:
    """Ollama API를 통한 VLM 서비스"""

    def __init__(self):
        self._client: Optional[httpx.Client] = None
        self.model_name: str = settings.vlm_model_name  # 런타임 변경 가능

    def initialize(self):
        """HTTP 클라이언트 초기화 + Ollama 연결 확인"""
        self._client = httpx.Client(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.vlm_timeout,
                write=5.0,
                pool=5.0,
            ),
        )
        self._check_model_available()

    def reload(self, model_name: str) -> None:
        """
        VLM 모델 핫리로드 — Ollama 재시작 없이 모델명 교체.
        파인튜닝 완료 후 새 모델을 Ollama에 등록한 뒤 호출.
        """
        old = self.model_name
        self.model_name = model_name
        self._check_model_available()
        logger.info(f"VLM model reloaded: {old} → {model_name}")

    def _check_model_available(self):
        """Ollama에 모델이 로드되어 있는지 확인 (non-fatal)"""
        try:
            resp = self._client.get("/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                names = [m.get("name", "") for m in models]
                if any(self.model_name in n for n in names):
                    logger.info(f"VLM model '{self.model_name}' available in Ollama")
                else:
                    logger.warning(
                        f"VLM model '{self.model_name}' not found in Ollama. "
                        f"Available: {names}. Run: ollama pull {self.model_name}"
                    )
        except Exception as e:
            logger.warning(f"Cannot reach Ollama at {settings.ollama_base_url}: {e}")

    # ──────────────────────────────────────────────
    # 공개 API
    # ──────────────────────────────────────────────

    def identify_with_candidates(
        self,
        image: Image.Image,
        candidates: List[VLMCandidate],
    ) -> VLMResult:
        """
        Visual RAG: 이미지 + Qdrant 후보 목록 → VLM 최종 판별

        Args:
            image: YOLO 크롭된 차량 이미지
            candidates: Qdrant 유사 검색 결과에서 집계된 고유 (manufacturer, model) 후보

        Returns:
            VLMResult
        """
        prompt = self._build_visual_rag_prompt(candidates)
        return self._call_vlm(image, prompt, candidates)

    def identify_freeform(self, image: Image.Image) -> VLMResult:
        """
        VLM-only 모드: 후보 없이 이미지만으로 차량 판별

        Returns:
            VLMResult (selected_index는 항상 None)
        """
        prompt = self._build_freeform_prompt()
        return self._call_vlm(image, prompt, candidates=None)

    def health_check(self) -> dict:
        """Ollama + VLM 모델 상태 확인"""
        try:
            resp = self._client.get("/api/tags")
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                available = any(self.model_name in m.get("name", "") for m in models)
                return {
                    "ollama": "connected",
                    "vlm_model": "available" if available else "not_found",
                    "vlm_model_name": self.model_name,
                }
        except Exception:
            pass
        return {
            "ollama": "disconnected",
            "vlm_model": "unknown",
            "vlm_model_name": self.model_name,
        }

    # ──────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────

    def _image_to_base64(self, image: Image.Image) -> str:
        """PIL Image → base64 문자열 (Ollama API 형식)"""
        max_size = 1024
        w, h = image.size
        if max(w, h) > max_size:
            scale = max_size / max(w, h)
            image = image.resize(
                (int(w * scale), int(h * scale)),
                Image.Resampling.LANCZOS
            )
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _build_visual_rag_prompt(self, candidates: List[VLMCandidate]) -> str:
        """Visual RAG용 프롬프트 생성"""
        candidate_lines = []
        for i, c in enumerate(candidates):
            candidate_lines.append(
                f"  {i}: {c.manufacturer_korean}({c.manufacturer_english}) "
                f"{c.model_korean}({c.model_english}) "
                f"[유사도={c.similarity:.3f}]"
            )
        candidate_text = "\n".join(candidate_lines)

        return (
            "이 차량 이미지를 보고, 아래 후보 중에서 가장 적합한 차량을 선택하세요.\n\n"
            f"후보 목록:\n{candidate_text}\n\n"
            "규칙:\n"
            "- 이미지의 차량과 가장 일치하는 후보의 번호를 선택하세요.\n"
            "- 어떤 후보도 맞지 않으면 selected_index를 null로 설정하세요.\n"
            "- confidence는 0.0~1.0 사이로, 선택에 대한 확신 정도입니다.\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요:\n"
            '{"selected_index": <번호 또는 null>, "confidence": <0.0~1.0>, "reasoning": "<판단 이유>"}'
        )

    def _build_freeform_prompt(self) -> str:
        """VLM-only 모드용 프롬프트"""
        return (
            "이 차량 이미지에서 제조사와 모델을 식별하세요.\n\n"
            "반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트 없이 JSON만 출력하세요:\n"
            '{"manufacturer_korean": "<제조사 한글>", "manufacturer_english": "<제조사 영문>", '
            '"model_korean": "<모델 한글>", "model_english": "<모델 영문>", '
            '"confidence": <0.0~1.0>, "reasoning": "<판단 이유>"}\n\n'
            "식별할 수 없으면 모든 이름 필드를 null로, confidence를 0.0으로 설정하세요."
        )

    def _call_vlm(
        self,
        image: Image.Image,
        prompt: str,
        candidates: Optional[List[VLMCandidate]],
    ) -> VLMResult:
        """Ollama /api/chat 엔드포인트 호출"""
        img_b64 = self._image_to_base64(image)

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [img_b64],
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 512,
                "think": False,  # Qwen3 thinking 모드 비활성화 (빈 응답 방지)
            },
            "format": "json",
        }

        start = time.time()
        try:
            resp = self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            elapsed = time.time() - start

            data = resp.json()
            raw_content = data.get("message", {}).get("content", "")
            logger.info(f"VLM response ({elapsed:.1f}s): {raw_content[:200]}")

            return self._parse_response(raw_content, candidates)

        except httpx.TimeoutException:
            logger.error(f"VLM timeout after {settings.vlm_timeout}s")
            raise
        except Exception as e:
            logger.error(f"VLM call failed: {e}")
            raise

    def _parse_response(
        self,
        raw: str,
        candidates: Optional[List[VLMCandidate]],
    ) -> VLMResult:
        """VLM JSON 응답 파싱 (방어적)"""
        try:
            # 마크다운 코드블록 제거
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                json_lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(json_lines).strip()

            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"VLM returned non-JSON: {raw[:200]}")
            return VLMResult(
                selected_index=None, manufacturer_id=None, model_id=None,
                manufacturer_korean=None, manufacturer_english=None,
                model_korean=None, model_english=None,
                confidence=0.0, reasoning="JSON 파싱 실패",
                raw_response=raw,
            )

        confidence = float(parsed.get("confidence", 0.0))
        reasoning = str(parsed.get("reasoning", ""))

        if candidates is not None:
            # Visual RAG 모드: selected_index로 후보 매핑
            idx = parsed.get("selected_index")
            if idx is not None and isinstance(idx, int) and 0 <= idx < len(candidates):
                c = candidates[idx]
                return VLMResult(
                    selected_index=idx,
                    manufacturer_id=c.manufacturer_id,
                    model_id=c.model_id,
                    manufacturer_korean=c.manufacturer_korean,
                    manufacturer_english=c.manufacturer_english,
                    model_korean=c.model_korean,
                    model_english=c.model_english,
                    confidence=confidence,
                    reasoning=reasoning,
                    raw_response=raw,
                )
            else:
                return VLMResult(
                    selected_index=None, manufacturer_id=None, model_id=None,
                    manufacturer_korean=None, manufacturer_english=None,
                    model_korean=None, model_english=None,
                    confidence=0.0,
                    reasoning=reasoning or "후보 중 일치하는 차량 없음",
                    raw_response=raw,
                )
        else:
            # VLM-only 모드: 자유 응답 매핑
            return VLMResult(
                selected_index=None,
                manufacturer_id=None,
                model_id=None,
                manufacturer_korean=parsed.get("manufacturer_korean"),
                manufacturer_english=parsed.get("manufacturer_english"),
                model_korean=parsed.get("model_korean"),
                model_english=parsed.get("model_english"),
                confidence=confidence,
                reasoning=reasoning,
                raw_response=raw,
            )
