from dataclasses import dataclass
from pathlib import Path

from faster_whisper import WhisperModel


class TranscriptionFailedError(Exception):
    pass


@dataclass
class TranscriptWord:
    word: str
    start: float
    end: float


def transcribe_audio(
    audio_path: Path,
    model_size: str = "small",
    device: str = "auto",
) -> list[TranscriptWord]:
    """Transkripsi audio jadi list kata dengan timestamp per kata.

    Audio tanpa suara/bahasa tak dikenali menghasilkan list kosong (bukan error),
    supaya job bisa lanjut dengan status peringatan.

    Raises:
        TranscriptionFailedError: model gagal berjalan (bukan karena audio kosong).
    """
    try:
        model = WhisperModel(model_size, device=device, compute_type="int8")
        segments, _info = model.transcribe(str(audio_path), word_timestamps=True)
        words = []
        for segment in segments:
            for w in segment.words or []:
                words.append(TranscriptWord(word=w.word.strip(), start=w.start, end=w.end))
        return words
    except Exception as e:
        raise TranscriptionFailedError(f"Transkripsi gagal: {e}") from e
