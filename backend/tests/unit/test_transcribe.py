from types import SimpleNamespace

import pytest

from pipeline.transcribe import TranscriptionFailedError, TranscriptWord, transcribe_audio


def _fake_segment(words):
    return SimpleNamespace(
        words=[SimpleNamespace(word=w, start=s, end=e) for w, s, e in words]
    )


@pytest.fixture
def fake_model(mocker):
    model = mocker.MagicMock()
    cls = mocker.patch("pipeline.transcribe.WhisperModel", return_value=model)
    return model, cls


def test_transcribe_returns_words_with_timestamps(fake_model, tmp_path):
    model, _ = fake_model
    model.transcribe.return_value = (
        iter(
            [
                _fake_segment([(" Hello", 0.0, 0.4), (" world.", 0.5, 0.9)]),
                _fake_segment([(" Test", 1.2, 1.6)]),
            ]
        ),
        SimpleNamespace(language="en"),
    )

    words = transcribe_audio(tmp_path / "audio.wav")

    assert words == [
        TranscriptWord(word="Hello", start=0.0, end=0.4),
        TranscriptWord(word="world.", start=0.5, end=0.9),
        TranscriptWord(word="Test", start=1.2, end=1.6),
    ]


def test_transcribe_requests_word_timestamps(fake_model, tmp_path):
    model, _ = fake_model
    model.transcribe.return_value = (iter([]), SimpleNamespace(language="en"))

    transcribe_audio(tmp_path / "audio.wav")

    kwargs = model.transcribe.call_args.kwargs
    assert kwargs.get("word_timestamps") is True


def test_silent_audio_returns_empty_list(fake_model, tmp_path):
    model, _ = fake_model
    model.transcribe.return_value = (iter([]), SimpleNamespace(language=None))

    assert transcribe_audio(tmp_path / "silent.wav") == []


def test_segment_without_words_skipped(fake_model, tmp_path):
    model, _ = fake_model
    model.transcribe.return_value = (
        iter([SimpleNamespace(words=None), _fake_segment([(" Ok", 0.0, 0.3)])]),
        SimpleNamespace(language="en"),
    )

    words = transcribe_audio(tmp_path / "audio.wav")
    assert words == [TranscriptWord(word="Ok", start=0.0, end=0.3)]


def test_model_failure_maps_to_specific_error(fake_model, tmp_path):
    model, _ = fake_model
    model.transcribe.side_effect = RuntimeError("cuda out of memory")

    with pytest.raises(TranscriptionFailedError):
        transcribe_audio(tmp_path / "audio.wav")
