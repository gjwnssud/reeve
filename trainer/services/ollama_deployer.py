"""
Ollama 배포 서비스
병합된 파인튜닝 모델을 Ollama에 자동 등록하고 Identifier 서비스에 핫리로드 알림.

파이프라인:
  1. GGUF 변환 (llama.cpp convert_hf_to_gguf.py, GGUF_CONVERTER_PATH 설정 시)
  2. Modelfile 생성 + Ollama /api/create 호출
  3. Identifier /admin/reload-vlm 호출 (선택)
"""
import logging
import subprocess
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "당신은 차량 식별 전문가입니다. "
    "차량 이미지를 보고 제조사와 모델을 정확하게 식별합니다."
)


class OllamaDeployer:
    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        identifier_base_url: str = "http://localhost:8001",
        gguf_converter_path: Optional[str] = None,
    ):
        self.ollama_base_url = ollama_base_url
        self.identifier_base_url = identifier_base_url
        self.gguf_converter_path = gguf_converter_path

    def deploy(
        self,
        merged_model_dir: str,
        model_name: str,
        notify_identifier: bool = True,
    ) -> dict:
        """
        병합된 HuggingFace 모델 디렉토리 → Ollama 등록 → Identifier 핫리로드

        Args:
            merged_model_dir: export_model()로 생성된 병합 모델 디렉토리
            model_name: Ollama에 등록할 모델명 (예: reeve-vlm-v1)
            notify_identifier: True이면 완료 후 Identifier 서비스에 핫리로드 요청

        Returns:
            성공: {"model_name": ..., "gguf_path": ..., "status": "registered", ...}
            실패: {"error": ..., "hint": ..., "manual_cmd": ...}
        """
        merged_path = Path(merged_model_dir)
        if not merged_path.exists():
            return {"error": f"병합 모델 디렉토리를 찾을 수 없습니다: {merged_model_dir}"}

        gguf_path = merged_path / "model.gguf"

        # 1. GGUF 변환 (파일이 없을 때만)
        if not gguf_path.exists():
            if not self.gguf_converter_path:
                return {
                    "error": "GGUF 파일이 없고 변환기 경로가 설정되지 않았습니다.",
                    "hint": (
                        "docker/.env에 GGUF_CONVERTER_PATH=/path/to/llama.cpp/convert_hf_to_gguf.py 를 설정하거나, "
                        "아래 커맨드로 수동 변환 후 다시 시도하세요."
                    ),
                    "manual_cmd": (
                        f"python convert_hf_to_gguf.py {merged_model_dir} "
                        f"--outtype f16 --outfile {gguf_path}"
                    ),
                }
            result = self._convert_to_gguf(str(merged_path), str(gguf_path))
            if "error" in result:
                return result

        # 2. Ollama 등록
        result = self._register_with_ollama(str(gguf_path), model_name)
        if "error" in result:
            return result

        # 3. Identifier 핫리로드
        if notify_identifier:
            result["identifier_reload"] = self._notify_identifier(model_name)

        return result

    # ──────────────────────────────────────────────
    # 내부 메서드
    # ──────────────────────────────────────────────

    def _convert_to_gguf(self, merged_dir: str, gguf_path: str) -> dict:
        logger.info(f"GGUF 변환 시작: {merged_dir} → {gguf_path}")
        try:
            proc = subprocess.run(
                [
                    "python", self.gguf_converter_path,
                    merged_dir,
                    "--outtype", "f16",
                    "--outfile", gguf_path,
                ],
                capture_output=True,
                text=True,
                timeout=3600,
            )
            if proc.returncode != 0:
                return {"error": f"GGUF 변환 실패: {proc.stderr[:500]}"}
            logger.info(f"GGUF 변환 완료: {gguf_path}")
            return {"gguf_path": gguf_path}
        except subprocess.TimeoutExpired:
            return {"error": "GGUF 변환 타임아웃 (1시간 초과)"}
        except Exception as e:
            return {"error": f"GGUF 변환 오류: {e}"}

    def _register_with_ollama(self, gguf_path: str, model_name: str) -> dict:
        modelfile = f'FROM {gguf_path}\nSYSTEM "{_SYSTEM_PROMPT}"\n'
        logger.info(f"Ollama 모델 등록 시작: {model_name} (GGUF: {gguf_path})")
        try:
            with httpx.Client(base_url=self.ollama_base_url, timeout=300.0) as client:
                # Ollama /api/create는 스트리밍 응답 — 완료까지 읽음
                with client.stream("POST", "/api/create", json={
                    "name": model_name,
                    "modelfile": modelfile,
                }) as resp:
                    if resp.status_code not in (200, 201):
                        body = resp.read().decode()[:300]
                        return {"error": f"Ollama 등록 실패 ({resp.status_code}): {body}"}
                    # 스트림을 소비해야 완료 처리됨
                    for _ in resp.iter_lines():
                        pass

            logger.info(f"Ollama 모델 등록 완료: {model_name}")
            return {
                "model_name": model_name,
                "gguf_path": gguf_path,
                "status": "registered",
            }
        except httpx.ConnectError:
            return {"error": f"Ollama에 연결할 수 없습니다: {self.ollama_base_url}"}
        except Exception as e:
            return {"error": f"Ollama 등록 오류: {e}"}

    def _notify_identifier(self, model_name: str) -> dict:
        try:
            with httpx.Client(base_url=self.identifier_base_url, timeout=10.0) as client:
                resp = client.post("/admin/reload-vlm", json={"model_name": model_name})
                if resp.status_code == 200:
                    return {"status": "reloaded", "model_name": model_name}
                return {"status": "failed", "detail": resp.text[:200]}
        except Exception as e:
            return {"status": "unreachable", "detail": str(e)}
