import json
import re
from dataclasses import dataclass
from typing import Protocol

from pipeline.transcribe import TranscriptWord


class LLMAnalysisError(Exception):
    pass


class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...


@dataclass
class Segment:
    start: float
    end: float
    score: int
    title: str
    reason: str


_PROMPT_TEMPLATE = """\
Kamu adalah editor video profesional. Berikut transkrip video dengan timestamp \
(format: [detik] teks). Temukan momen paling menarik untuk dijadikan klip pendek \
vertikal (durasi ideal 20-60 detik): hook kuat, insight, punchline, atau momen emosional.

TRANSKRIP:
{transcript}

Balas HANYA dengan JSON array (tanpa teks lain), tiap elemen:
{{"start": <detik mulai>, "end": <detik selesai>, "score": <0-100 seberapa menarik>, \
"title": "<judul singkat menarik>", "reason": "<alasan singkat>"}}
"""

_WORDS_PER_LINE = 15


def build_prompt(words: list[TranscriptWord]) -> str:
    lines = []
    for i in range(0, len(words), _WORDS_PER_LINE):
        group = words[i : i + _WORDS_PER_LINE]
        text = " ".join(w.word for w in group)
        lines.append(f"[{group[0].start:.1f}] {text}")
    return _PROMPT_TEMPLATE.format(transcript="\n".join(lines))


def parse_llm_response(response: str) -> list[Segment]:
    """Parse respons LLM jadi list Segment. Elemen malformed dilewati.

    Raises:
        LLMAnalysisError: respons bukan JSON array yang valid.
    """
    text = response.strip()
    # Buang markdown fence bila ada.
    m = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise LLMAnalysisError(f"Respons LLM bukan JSON valid: {e}") from e
    if not isinstance(data, list):
        raise LLMAnalysisError("Respons LLM bukan JSON array")

    segments = []
    for item in data:
        try:
            start = float(item["start"])
            end = float(item["end"])
            if end <= start:
                continue
            segments.append(
                Segment(
                    start=start,
                    end=end,
                    score=max(0, min(100, int(item.get("score", 0)))),
                    title=str(item.get("title", "")),
                    reason=str(item.get("reason", "")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return segments


def chunk_transcript(
    words: list[TranscriptWord], max_chars: int = 30_000
) -> list[list[TranscriptWord]]:
    """Pecah transkrip jadi chunk berurutan sesuai budget karakter (kata + 1 spasi)."""
    chunks: list[list[TranscriptWord]] = []
    current: list[TranscriptWord] = []
    size = 0
    for w in words:
        cost = len(w.word) + 1
        if current and size + cost > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append(w)
        size += cost
    if current:
        chunks.append(current)
    return chunks


_MAX_RETRIES = 2


def find_highlights(
    words: list[TranscriptWord],
    client: LLMClient,
    max_chunk_chars: int = 30_000,
) -> list[Segment]:
    """Cari golden moment via LLM. Transkrip panjang di-chunk, hasil digabung terurut.

    Timestamp kata bersifat absolut terhadap video sumber, jadi hasil antar-chunk
    bisa langsung digabung tanpa penyesuaian offset.

    Raises:
        LLMAnalysisError: LLM gagal setelah retry, atau respons tak bisa diparse.
    """
    segments: list[Segment] = []
    for chunk in chunk_transcript(words, max_chars=max_chunk_chars):
        response = _complete_with_retry(client, build_prompt(chunk))
        segments.extend(parse_llm_response(response))
    return sorted(segments, key=lambda s: s.start)


def _complete_with_retry(client: LLMClient, prompt: str) -> str:
    last_error: Exception | None = None
    for _ in range(1 + _MAX_RETRIES):
        try:
            return client.complete(prompt)
        except Exception as e:
            last_error = e
    raise LLMAnalysisError(
        f"LLM gagal setelah {_MAX_RETRIES} retry: {last_error}"
    ) from last_error
