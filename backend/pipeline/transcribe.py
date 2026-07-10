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
    progress_cb=None,
) -> list[TranscriptWord]:
    """Transkripsi audio jadi list kata dengan timestamp per kata.

    progress_cb(percent, message) dipanggil per segmen berdasarkan posisi waktu
    relatif terhadap durasi audio, supaya UI menunjukkan kemajuan transkrip.

    Audio tanpa suara/bahasa tak dikenali menghasilkan list kosong (bukan error),
    supaya job bisa lanjut dengan status peringatan.

    Raises:
        TranscriptionFailedError: model gagal berjalan (bukan karena audio kosong).
    """
    try:
        model = WhisperModel(model_size, device=device, compute_type="int8")
        # faster-whisper mengembalikan generator segmen + info berisi durasi.
        segments, info = model.transcribe(str(audio_path), word_timestamps=True)
        total = getattr(info, "duration", 0) or 0
        words = []
        for segment in segments:
            for w in segment.words or []:
                words.append(TranscriptWord(word=w.word.strip(), start=w.start, end=w.end))
            if progress_cb is not None and total:
                pct = min(100, int(segment.end / total * 100))
                progress_cb(pct, f"Transkripsi {pct}%")
        return words
    except Exception as e:
        raise TranscriptionFailedError(f"Transkripsi gagal: {e}") from e
