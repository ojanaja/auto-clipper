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


def make_llm_client():
    """Buat LLM client sesuai env: LLM_PROVIDER=gemini (default) | anthropic.

    Raises:
        RuntimeError: API key untuk provider terpilih tidak diset.
    """
    provider = os.environ.get("LLM_PROVIDER", "gemini")
    if provider == "anthropic":
        return AnthropicLLMClient()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY belum diset. Ambil key gratis di https://aistudio.google.com/apikey"
        )
    return GeminiLLMClient(api_key=key)
