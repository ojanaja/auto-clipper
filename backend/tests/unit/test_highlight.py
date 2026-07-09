import json

import pytest

from pipeline.highlight import (
    LLMAnalysisError,
    Segment,
    build_prompt,
    chunk_transcript,
    find_highlights,
    parse_llm_response,
)
from pipeline.transcribe import TranscriptWord


def _words(*items):
    """items: (word, start, end)"""
    return [TranscriptWord(word=w, start=s, end=e) for w, s, e in items]


SAMPLE_WORDS = _words(
    ("Halo", 0.0, 0.3),
    ("semua,", 0.4, 0.8),
    ("hari", 1.0, 1.2),
    ("ini", 1.3, 1.5),
    ("kita", 1.6, 1.9),
    ("bahas", 2.0, 2.4),
    ("rahasia", 2.5, 3.0),
    ("sukses.", 3.1, 3.6),
)

VALID_RESPONSE = json.dumps(
    [
        {
            "start": 0.0,
            "end": 3.6,
            "score": 85,
            "title": "Rahasia Sukses",
            "reason": "Hook kuat di pembukaan",
        }
    ]
)


class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


# --- build_prompt ---


def test_prompt_contains_transcript_text_and_timestamps():
    prompt = build_prompt(SAMPLE_WORDS)
    assert "rahasia" in prompt
    assert "0.0" in prompt  # timestamp awal muncul
    assert "JSON" in prompt  # instruksi format output


# --- parse_llm_response ---


def test_parse_valid_json_response():
    segments = parse_llm_response(VALID_RESPONSE)
    assert len(segments) == 1
    seg = segments[0]
    assert seg == Segment(
        start=0.0, end=3.6, score=85, title="Rahasia Sukses", reason="Hook kuat di pembukaan"
    )


def test_parse_response_wrapped_in_markdown_fences():
    fenced = f"```json\n{VALID_RESPONSE}\n```"
    assert len(parse_llm_response(fenced)) == 1


def test_parse_invalid_json_raises():
    with pytest.raises(LLMAnalysisError):
        parse_llm_response("bukan json sama sekali")


def test_parse_skips_malformed_segments():
    resp = json.dumps(
        [
            {"start": 0, "end": 5, "score": 70, "title": "Ok", "reason": "bagus"},
            {"start": 9, "end": 3, "score": 70, "title": "Mundur", "reason": "start>end"},
            {"title": "Tanpa waktu"},
        ]
    )
    segments = parse_llm_response(resp)
    assert len(segments) == 1
    assert segments[0].title == "Ok"


def test_parse_clamps_score_to_0_100():
    resp = json.dumps(
        [{"start": 0, "end": 5, "score": 150, "title": "X", "reason": "y"}]
    )
    assert parse_llm_response(resp)[0].score == 100


# --- chunk_transcript ---


def test_short_transcript_single_chunk():
    chunks = chunk_transcript(SAMPLE_WORDS, max_chars=10_000)
    assert len(chunks) == 1
    assert chunks[0] == SAMPLE_WORDS


def test_long_transcript_split_into_chunks():
    words = _words(*((f"kata{i}", float(i), float(i) + 0.5) for i in range(100)))
    chunks = chunk_transcript(words, max_chars=100)

    assert len(chunks) > 1
    # Tidak ada kata hilang ataupun duplikat, urutan terjaga.
    flattened = [w for c in chunks for w in c]
    assert flattened == words
    # Tiap chunk hormati batas karakter.
    for c in chunks:
        assert sum(len(w.word) + 1 for w in c) <= 100


def test_chunk_empty_transcript():
    assert chunk_transcript([], max_chars=100) == []


# --- find_highlights ---


def test_find_highlights_single_chunk():
    client = FakeLLM([VALID_RESPONSE])
    segments = find_highlights(SAMPLE_WORDS, client)
    assert len(segments) == 1
    assert segments[0].title == "Rahasia Sukses"
    assert len(client.prompts) == 1


def test_find_highlights_multiple_chunks_merged_sorted():
    words = _words(*((f"kata{i}", float(i), float(i) + 0.5) for i in range(100)))
    resp_a = json.dumps([{"start": 50, "end": 60, "score": 90, "title": "B", "reason": "r"}])
    resp_b = json.dumps([{"start": 5, "end": 15, "score": 80, "title": "A", "reason": "r"}])
    client = FakeLLM([resp_a, resp_b])

    # 100 kata ~690 char; budget 350 -> tepat 2 chunk.
    segments = find_highlights(words, client, max_chunk_chars=350)

    assert len(client.prompts) == 2
    assert [s.title for s in segments] == ["A", "B"]  # terurut by start


def test_find_highlights_empty_transcript_returns_empty():
    client = FakeLLM([])
    assert find_highlights([], client) == []
    assert client.prompts == []


# --- retry & fallback ---


def test_find_highlights_retries_then_succeeds():
    client = FakeLLM([TimeoutError("timeout"), VALID_RESPONSE])
    segments = find_highlights(SAMPLE_WORDS, client)
    assert len(segments) == 1
    assert len(client.prompts) == 2


def test_find_highlights_gives_up_after_retries():
    client = FakeLLM([TimeoutError("t1"), TimeoutError("t2"), TimeoutError("t3")])
    with pytest.raises(LLMAnalysisError):
        find_highlights(SAMPLE_WORDS, client)
    # 1 percobaan awal + 2 retry = 3 panggilan.
    assert len(client.prompts) == 3
