"""Integration test face-tracking pada video nyata berwajah manusia.

Butuh: jaringan, ffmpeg, model YuNet. Jalankan manual:

    cd backend
    source .venv/bin/activate
    pytest -m integration tests/integration/test_face_tracking_real.py -v
"""

import subprocess
from pathlib import Path

import pytest

from config import AppConfig
from job_manager import JobManager, JobStatus
from orchestrator import PipelineOrchestrator
from pipeline.download import download_video
from pipeline.face_detect import detect_faces_sampled, ensure_model
from pipeline.highlight import Segment
from pipeline.render import probe_dimensions
from progress import ProgressBroadcaster

# Video publik pendek yang menyertakan wajah manusia.
SHORT_PUBLIC_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # 19 detik


@pytest.fixture(scope="module")
def downloaded_video_path(tmp_path_factory):
    """Download video publik pendek untuk test face-tracking."""
    tmp_path = tmp_path_factory.mktemp("face_tracking")
    try:
        meta = download_video(SHORT_PUBLIC_VIDEO, tmp_path)
    except Exception as exc:
        pytest.skip(f"Tidak bisa download video integrasi: {exc}")
    return Path(meta.filepath)


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


@pytest.mark.integration
def test_face_tracking_detects_faces_and_renders(downloaded_video_path, tmp_path):
    ensure_model()  # Pastikan model YuNet tersedia (download bila perlu).

    frame_w, frame_h = probe_dimensions(downloaded_video_path)
    # Jalankan deteksi wajah pada 6 detik pertama.
    end_t = min(6.0, _probe_duration(downloaded_video_path))
    timeline = detect_faces_sampled(
        downloaded_video_path, start=0.0, end=end_t, fps=2
    )
    # Minimal ada satu sample yang berhasil mendeteksi wajah.
    total_faces = sum(len(dets) for _t, dets in timeline)
    assert total_faces > 0, "YuNet tidak mendeteksi wajah sama sekali pada video nyata"

    manager = JobManager()
    broadcaster = ProgressBroadcaster()
    orchestrator = PipelineOrchestrator(manager, broadcaster)

    job = manager.create_job(SHORT_PUBLIC_VIDEO)
    job.video_path = str(downloaded_video_path)
    job.segments = [
        Segment(start=0.0, end=5.0, score=90, title="Face Tracking Test", reason="integration")
    ]
    job.status = JobStatus.READY

    cfg = AppConfig(
        face_tracking_enabled=True,
        face_sample_fps=2,
        speaker_min_dwell_s=0.5,
        resolution=720,
        aspect_ratio="9:16",
        subtitle_enabled=False,
        encoder="libx264",
    )
    orchestrator._config_provider = lambda: cfg

    output_dir = tmp_path / "out"
    output_dir.mkdir()

    orchestrator.run_render(job.job_id, segment_ids=["0"], output_dir=output_dir)

    assert job.status == JobStatus.DONE, f"job error: {job.error}"
    clip = job.clips["0"]
    assert clip["status"] == "done"
    out_path = Path(clip["path"])
    assert out_path.exists() and out_path.stat().st_size > 0

    duration = _probe_duration(out_path)
    assert 4.5 <= duration <= 5.5
