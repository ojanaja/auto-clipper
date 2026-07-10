import os

import anthropic
import httpx


class AnthropicLLMClient:
    """Implementasi LLMClient (lihat pipeline.highlight) memakai Claude API.

    API key diambil dari konstruktor atau env var ANTHROPIC_API_KEY
    (resolusi standar SDK) — sesuai PRD, key milik user disimpan lokal.
    """

    def __init__(self, model: str = "claude-opus-4-8", api_key: str | None = None):
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self._model = model

    def complete(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}],
        )
        for block in response.content:
            if block.type == "text":
                return block.text
        raise ValueError("Respons LLM tidak mengandung blok teks")


class GeminiLLMClient:
    """Implementasi LLMClient memakai Google Gemini API (free tier tersedia).

    Pakai REST langsung via httpx — tidak butuh SDK tambahan.
    API key gratis dari https://aistudio.google.com/apikey.
    """

    _BASE = "https://generativelanguage.googleapis.com/v1beta/models"

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self._api_key = api_key
        self._model = model

    def complete(self, prompt: str) -> str:
        response = httpx.post(
            f"{self._BASE}/{self._model}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=120,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Gemini API error {response.status_code}: {response.text[:300]}")
        candidates = response.json().get("candidates", [])
        if not candidates:
            raise ValueError("Respons Gemini tidak mengandung kandidat")
        return candidates[0]["content"]["parts"][0]["text"]


def make_llm_client(
    provider: str | None = None,
    gemini_api_key: str | None = None,
    anthropic_api_key: str | None = None,
    model: str | None = None,
):
    """Buat LLM client sesuai konfigurasi atau env.

    Args:
        provider: "gemini" atau "anthropic". Default dari env LLM_PROVIDER atau "gemini".
        gemini_api_key: API key Gemini; fallback ke env GEMINI_API_KEY.
        anthropic_api_key: API key Anthropic; fallback ke env ANTHROPIC_API_KEY.
        model: Model spesifik; fallback ke env GEMINI_MODEL / ANTHROPIC_MODEL.

    Raises:
        RuntimeError: API key untuk provider terpilih tidak diset.
    """
    provider = (provider or os.environ.get("LLM_PROVIDER", "gemini")).lower()

    if provider == "anthropic":
        key = anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        default_model = os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-8")
        return AnthropicLLMClient(model=model or default_model, api_key=key or None)

    key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY belum diset. Ambil key gratis di https://aistudio.google.com/apikey"
        )
    default_model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
    return GeminiLLMClient(api_key=key, model=model or default_model)
