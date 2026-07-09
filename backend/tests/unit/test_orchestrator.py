from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from job_manager import JobManager, JobStatus
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
FAKE_SEGMENTS = [
    Segment(start=1.0, end=20.0, score=90, title="A", reason="r"),
    Segment(start=30.0, end=50.0, score=80, title="B", reason="r"),
]


@pytest.fixture
def deps(tmp_path):
    return {
        "download_fn": MagicMock(return_value=FAKE_META),
        "transcribe_fn": MagicMock(return_value=FAKE_WORDS),
        "highlight_fn": MagicMock(return_value=FAKE_SEGMENTS),
        "render_fn": MagicMock(side_effect=lambda src, seg, words, out, work_dir: out),
        "llm_client": MagicMock(),
        "work_root": tmp_path,
    }


@pytest.fixture
def manager():
    return JobManager()


@pytest.fixture
def broadcaster():
    return MagicMock()


def _orchestrator(manager, broadcaster, deps):
    return PipelineOrchestrator(manager, broadcaster, **deps)


# --- run_analysis ---


def test_analysis_calls_pipeline_in_order_and_stores_results(manager, broadcaster, deps):
    job = manager.create_job(URL)
    orch = _orchestrator(manager, broadcaster, deps)

    orch.run_analysis(job.job_id)

    assert job.status == JobStatus.READY
    deps["download_fn"].assert_called_once()
    assert deps["download_fn"].call_args.args[0] == URL
    deps["transcribe_fn"].assert_called_once_with(FAKE_META.filepath)
    assert deps["highlight_fn"].call_args.args[0] == FAKE_WORDS
    assert job.words == FAKE_WORDS
    assert job.segments == FAKE_SEGMENTS
    assert job.video_path == FAKE_META.filepath


def test_analysis_publishes_progress_events(manager, broadcaster, deps):
    job = manager.create_job(URL)
    _orchestrator(manager, broadcaster, deps).run_analysis(job.job_id)

    stages = [c.args[1]["stage"] for c in broadcaster.publish.call_args_list]
    assert "downloading" in stages
    assert "transcribing" in stages
    assert "analyzing" in stages
    assert "ready" in stages
    # Semua event untuk job_id yang benar.
    assert all(c.args[0] == job.job_id for c in broadcaster.publish.call_args_list)


def test_analysis_download_error_sets_job_error(manager, broadcaster, deps):
    deps["download_fn"].side_effect = RuntimeError("video privat")
    job = manager.create_job(URL)

    _orchestrator(manager, broadcaster, deps).run_analysis(job.job_id)  # tidak raise

    assert job.status == JobStatus.ERROR
    assert "video privat" in job.error
    deps["transcribe_fn"].assert_not_called()


def test_analysis_llm_error_sets_job_error(manager, broadcaster, deps):
    deps["highlight_fn"].side_effect = RuntimeError("API limit")
    job = manager.create_job(URL)

    _orchestrator(manager, broadcaster, deps).run_analysis(job.job_id)

    assert job.status == JobStatus.ERROR
    assert "API limit" in job.error


# --- run_render ---


def _ready_job(manager, deps, broadcaster):
    job = manager.create_job(URL)
    _orchestrator(manager, broadcaster, deps).run_analysis(job.job_id)
    return job


def test_render_selected_segments_batch(manager, broadcaster, deps, tmp_path):
    job = _ready_job(manager, deps, broadcaster)
    orch = _orchestrator(manager, broadcaster, deps)

    orch.run_render(job.job_id, segment_ids=["0", "1"], output_dir=tmp_path)

    assert job.status == JobStatus.DONE
    assert deps["render_fn"].call_count == 2
    # Output path unik per segmen.
    outputs = [c.args[3] for c in deps["render_fn"].call_args_list]
    assert len(set(outputs)) == 2
    assert all(str(tmp_path) in str(o) for o in outputs)
    # Clip state terlacak per segmen.
    assert job.clips["0"]["status"] == "done"
    assert job.clips["1"]["status"] == "done"


def test_render_subset_only(manager, broadcaster, deps, tmp_path):
    job = _ready_job(manager, deps, broadcaster)
    _orchestrator(manager, broadcaster, deps).run_render(
        job.job_id, segment_ids=["1"], output_dir=tmp_path
    )

    assert deps["render_fn"].call_count == 1
    rendered_segment = deps["render_fn"].call_args.args[1]
    assert rendered_segment.title == "B"


def test_render_one_clip_fails_others_continue(manager, broadcaster, deps, tmp_path):
    job = _ready_job(manager, deps, broadcaster)

    def flaky(src, seg, words, out, work_dir):
        if seg.title == "A":
            raise RuntimeError("encoder crash")
        return out

    deps["render_fn"].side_effect = flaky
    _orchestrator(manager, broadcaster, deps).run_render(
        job.job_id, segment_ids=["0", "1"], output_dir=tmp_path
    )

    assert job.clips["0"]["status"] == "error"
    assert job.clips["1"]["status"] == "done"
    # Job selesai walau satu klip gagal (tidak crash total).
    assert job.status == JobStatus.DONE


def test_render_unknown_segment_id_rejected(manager, broadcaster, deps, tmp_path):
    job = _ready_job(manager, deps, broadcaster)
    with pytest.raises(ValueError):
        _orchestrator(manager, broadcaster, deps).run_render(
            job.job_id, segment_ids=["99"], output_dir=tmp_path
        )


def test_render_output_filenames_safe(manager, broadcaster, deps, tmp_path):
    deps["highlight_fn"].return_value = [
        Segment(start=0, end=5, score=50, title="Judul/Aneh: <ok>?", reason="r")
    ]
    job = _ready_job(manager, deps, broadcaster)
    _orchestrator(manager, broadcaster, deps).run_render(
        job.job_id, segment_ids=["0"], output_dir=tmp_path
    )
    out = Path(deps["render_fn"].call_args.args[3])
    assert "/" not in out.name and ":" not in out.name and "<" not in out.name
