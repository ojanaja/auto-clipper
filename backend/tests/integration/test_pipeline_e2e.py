"""Smoke test end-to-end nyata: 1 video publik pendek melewati seluruh pipeline.

Butuh: jaringan, ffmpeg, model whisper, dan GEMINI_API_KEY.
Jalankan manual sebelum rilis:
    GEMINI_API_KEY=... pytest -m integration tests/integration/test_pipeline_e2e.py
"""

import os

import pytest

from job_manager import JobManager, JobStatus
from orchestrator import PipelineOrchestrator
from pipeline.transcribe import transcribe_audio

SHORT_PUBLIC_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # 19 detik


class _NullBroadcaster:
    def publish(self, job_id, event):
        print(f"[{event['stage']}] {event['message']}")


@pytest.mark.integration
@pytest.mark.skipif(not os.environ.get("GEMINI_API_KEY"), reason="butuh GEMINI_API_KEY")
def test_full_pipeline_real_video(tmp_path):
    manager = JobManager()
    orch = PipelineOrchestrator(
        manager,
        _NullBroadcaster(),
        transcribe_fn=lambda p: transcribe_audio(p, model_size="tiny"),
        work_root=tmp_path / "work",
    )
    job = manager.create_job(SHORT_PUBLIC_VIDEO)

    orch.run_analysis(job.job_id)
    assert job.status == JobStatus.READY, job.error
    assert len(job.segments) >= 1

    orch.run_render(job.job_id, segment_ids=["0"], output_dir=tmp_path / "out")
    assert job.status == JobStatus.DONE
    clip = job.clips["0"]
    assert clip["status"] == "done", clip
    out = clip["path"]
    assert os.path.exists(out) and os.path.getsize(out) > 0
