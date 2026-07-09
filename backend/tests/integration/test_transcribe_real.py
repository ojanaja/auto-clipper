"""Integration test transkripsi dengan model faster-whisper asli.

Download model tiny (~75MB) saat pertama kali. Jalankan manual:
    pytest -m integration tests/integration/test_transcribe_real.py
"""

from pathlib import Path

import pytest

from pipeline.transcribe import transcribe_audio

FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures"


@pytest.mark.integration
def test_transcribe_real_speech():
    words = transcribe_audio(FIXTURES / "speech_short.wav", model_size="tiny")

    assert len(words) >= 5
    text = " ".join(w.word.lower() for w in words)
    assert "hello" in text
    assert "world" in text
    # Timestamp harus monoton tidak menurun.
    starts = [w.start for w in words]
    assert starts == sorted(starts)
    assert all(w.end >= w.start for w in words)


@pytest.mark.integration
def test_transcribe_real_silent_returns_empty():
    words = transcribe_audio(FIXTURES / "silent.wav", model_size="tiny")
    assert words == []
