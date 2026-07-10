"""Integrasi mocked: pipeline menerapkan konfigurasi custom."""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from config import AppConfig
from job_manager import JobManager
from orchestrator import PipelineOrchestrator
from pipeline.highlight import Segment
from pipeline.transcribe import TranscriptWord

URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

FAKE_META = SimpleNamespace(
    video_id="dQw4w9WgXcQ",
    title="Video",
    duration=100,
    width=1920,
    height=1080,
    filepath="/tmp/work/dQw4w9WgXcQ.mp4",
)
FAKE_WORDS = [TranscriptWord(word="halo", start=1.0, end=1.5)]
FAKE_SEGMENTS = [Segment(start=1.0, end=20.0, score=90, title="A", reason="r")]


def test_config_16_9_applied_to_render():
    """Config rasio 16:9 @ 720p membuat render menerima dimensi landscape."""
    manager = JobManager()
    broadcaster = MagicMock()

    render_calls = []

    def capture_render(src, seg, words, out, work_dir, progress_cb=None, **kwargs):
        render_calls.append(kwargs)
        return out

    deps = {
        "download_fn": MagicMock(return_value=FAKE_META),
        "transcribe_fn": MagicMock(return_value=FAKE_WORDS),
        "highlight_fn": MagicMock(return_value=FAKE_SEGMENTS),
        "render_fn": MagicMock(side_effect=capture_render),
        "llm_client": MagicMock(),
        "config_provider": lambda: AppConfig(aspect_ratio="16:9", resolution=720),
    }

    orch = PipelineOrchestrator(manager, broadcaster, **deps)
    job = manager.create_job(URL)
    orch.run_analysis(job.job_id)
    orch.run_render(job.job_id, segment_ids=["0"], output_dir=Path("/tmp/out"))

    assert render_calls
    kwargs = render_calls[0]
    assert kwargs["target_ratio"] == 16 / 9
    assert kwargs["output_width"] == 1280
    assert kwargs["output_height"] == 720
