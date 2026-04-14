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
        # 서킷 브레이커 상태
        self._consecutive_failures: int = 0
        self._circuit_opened_at: float = 0.0  # open 진입 시각

    def _create_client(self) -> httpx.Client:
        """httpx 클라이언트 생성 (커넥션 풀 명시)"""
        return httpx.Client(
            base_url=settings.ollama_base_url,
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.vlm_timeout,
                write=5.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
            ),
        )

    def initialize(self):
        """HTTP 클라이언트 초기화 + Ollama 연결 확인"""
        self._client = self._create_client()
        self._check_model_available()

    def reload(self, model_name: str) -> None:
        """
        VLM 모델 핫리로드 — Ollama 재시작 없이 모델명 교체.
        파인튜닝 완료 후 새 모델을 Ollama에 등록한 뒤 호출.
        """
        old = self.model_name
        self.model_name = model_name
        # 기존 클라이언트 정리 후 새 클라이언트 생성 (커넥션 누수 방지)
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = self._create_client()
        self._consecutive_failures = 0
        self._circuit_opened_at = 0.0
        self._check_model_available()
        logger.info(f"VLM model reloaded: {old} → {model_name}")

    # ──────────────────────────────────────────────
    # 서킷 브레이커
    # ──────────────────────────────────────────────

    def is_available(self) -> bool:
        """서킷 브레이커 상태 확인. False이면 호출을 건너뛴다."""
        threshold = settings.vlm_circuit_breaker_threshold
        if self._consecutive_failures < threshold:
            return True  # closed
        # open 상태 — cooldown 경과 시 half-open (1건 시험 허용)
        elapsed = time.time() - self._circuit_opened_at
        if elapsed >= settings.vlm_circuit_breaker_cooldown:
            return True  # half-open
        return False  # open

    def _record_success(self):
        """호출 성공 시 서킷 브레이커 리셋"""
        if self._consecutive_failures > 0:
            logger.info("VLM circuit breaker closed (recovered)")
        self._consecutive_failures = 0
        self._circuit_opened_at = 0.0

    def _record_failure(self):
        """호출 실패 시 서킷 브레이커 카운트 증가"""
        self._consecutive_failures += 1
        threshold = settings.vlm_circuit_breaker_threshold
        if self._consecutive_failures >= threshold and self._circuit_opened_at == 0.0:
            self._circuit_opened_at = time.time()
            logger.warning(
                f"VLM circuit breaker OPEN — {self._consecutive_failures} consecutive failures, "
                f"cooldown={settings.vlm_circuit_breaker_cooldown}s"
            )

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

    def identify_freeform(self, image: Image.Image) -> VLMResult:
        """
        VLM-only 모드: 후보 없이 이미지만으로 차량 판별

        Returns:
            VLMResult (selected_index는 항상 None)
        """
        prompt = self._build_freeform_prompt()
        return self._call_vlm(image, prompt)

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

    def _is_retryable(self, exc: Exception) -> bool:
        """재시도 가능한 오류인지 판별 (타임아웃, 5xx)"""
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code >= 500:
            return True
        return False

    def _call_vlm(
        self,
        image: Image.Image,
        prompt: str,
    ) -> VLMResult:
        """Ollama /api/chat 엔드포인트 호출 (지수 백오프 재시도 포함)"""
        if not self.is_available():
            raise RuntimeError("VLM circuit breaker is open — skipping call")

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
                "num_predict": 2048,  # thinking 토큰 소모 후에도 content 생성 여유 확보
                "num_ctx": 8192,      # KV 캐시 — 요청 단위 적용 (서버/모델 기본값 무시)
            },
        }

        max_retries = settings.vlm_max_retries
        last_exc: Optional[Exception] = None

        for attempt in range(1 + max_retries):
            start = time.time()
            try:
                resp = self._client.post("/api/chat", json=payload)
                resp.raise_for_status()
                elapsed = time.time() - start

                data = resp.json()
                msg = data.get("message", {})
                raw_content = msg.get("content", "")
                logger.info(f"VLM response ({elapsed:.1f}s): {raw_content[:200]}")

                self._record_success()
                return self._parse_response(raw_content)

            except Exception as e:
                last_exc = e
                if attempt < max_retries and self._is_retryable(e):
                    wait = 0.5 * (2 ** attempt)  # 0.5s, 1.0s
                    logger.warning(
                        f"VLM call failed (attempt {attempt + 1}/{1 + max_retries}): {e}. "
                        f"Retrying in {wait:.1f}s..."
                    )
                    time.sleep(wait)
                    continue
                break

        self._record_failure()
        logger.error(f"VLM call failed after {1 + max_retries} attempt(s): {last_exc}")
        raise last_exc

    def _parse_response(self, raw: str) -> VLMResult:
        """VLM JSON 응답 파싱 (방어적)"""
        try:
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
