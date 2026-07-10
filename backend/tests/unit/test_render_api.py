from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app
from job_manager import JobStatus
from pipeline.highlight import Segment


@pytest.fixture
def client(monkeypatch):
    # Jalankan background task secara sinkron di test.
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *args: fn(*args))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def fake_orchestrator(monkeypatch):
    orch = MagicMock()

    def fake_analysis(job_id):
        job = app_module.job_manager.get_job(job_id)
        job.status = JobStatus.READY
        job.segments = [
            Segment(start=1.0, end=20.0, score=90, title="Momen A", reason="hook"),
            Segment(start=30.0, end=50.0, score=75, title="Momen B", reason="insight"),
        ]

    def fake_render(job_id, segment_ids, output_dir):
        job = app_module.job_manager.get_job(job_id)
        job.status = JobStatus.DONE
        for sid in segment_ids:
            job.clips[sid] = {"status": "done", "progress": 100, "path": f"/out/{sid}.mp4"}

    orch.run_analysis.side_effect = fake_analysis
    orch.run_render.side_effect = fake_render
    monkeypatch.setattr(app_module, "orchestrator", orch)
    return orch


def _create(client):
    return client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
    ).json()["job_id"]


def test_post_jobs_triggers_analysis(client, fake_orchestrator):
    job_id = _create(client)
    fake_orchestrator.run_analysis.assert_called_once_with(job_id)
    assert client.get(f"/jobs/{job_id}").json()["status"] == "ready"


def test_get_segments(client, fake_orchestrator):
    job_id = _create(client)
    resp = client.get(f"/jobs/{job_id}/segments")
    assert resp.status_code == 200
    segments = resp.json()["segments"]
    assert len(segments) == 2
    assert segments[0] == {
        "id": "0",
        "start": 1.0,
        "end": 20.0,
        "score": 90,
        "title": "Momen A",
        "reason": "hook",
    }


def test_get_segments_unknown_job_404(client, fake_orchestrator):
    assert client.get("/jobs/nope/segments").status_code == 404


def test_post_render_triggers_batch(client, fake_orchestrator):
    job_id = _create(client)
    resp = client.post(f"/jobs/{job_id}/render", json={"segment_ids": ["0", "1"]})
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"
    fake_orchestrator.run_render.assert_called_once()
    assert fake_orchestrator.run_render.call_args.args[1] == ["0", "1"]


def test_post_render_uses_config_output_dir(client, fake_orchestrator, tmp_path, monkeypatch):
    from config import AppConfig, save_config

    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    save_config(AppConfig(output_dir=str(tmp_path / "custom")), tmp_path / "config.json")

    job_id = _create(client)
    client.post(f"/jobs/{job_id}/render", json={"segment_ids": ["0"]})

    output_dir = fake_orchestrator.run_render.call_args.args[2]
    assert str(output_dir) == str(tmp_path / "custom")


def test_post_render_empty_ids_rejected(client, fake_orchestrator):
    job_id = _create(client)
    resp = client.post(f"/jobs/{job_id}/render", json={"segment_ids": []})
    assert resp.status_code == 422


def test_get_render_status(client, fake_orchestrator):
    job_id = _create(client)
    client.post(f"/jobs/{job_id}/render", json={"segment_ids": ["0"]})

    resp = client.get(f"/jobs/{job_id}/render-status")
    assert resp.status_code == 200
    clips = resp.json()["clips"]
    assert clips == [{"segment_id": "0", "status": "done", "progress": 100}]


def test_get_output_files(client, fake_orchestrator):
    job_id = _create(client)
    client.post(f"/jobs/{job_id}/render", json={"segment_ids": ["0", "1"]})

    resp = client.get(f"/jobs/{job_id}/output")
    files = resp.json()["files"]
    assert len(files) == 2
    assert files[0]["segment_id"] == "0"
    assert files[0]["path"] == "/out/0.mp4"
    assert files[0]["duration"] == 19.0  # end - start
