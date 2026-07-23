import pytest
from fastapi.testclient import TestClient

import app as app_module
from app import app


@pytest.fixture
def client(monkeypatch):
    # Matikan auto-trigger pipeline: test ini cuma menguji kontrak endpoint job.
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *args: None)
    with TestClient(app) as c:
        yield c


def test_post_jobs_creates_queued_job(client):
    resp = client.post("/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"]


def test_post_jobs_without_url_rejected(client):
    resp = client.post("/jobs", json={})
    assert resp.status_code == 422


def test_get_job_returns_status(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]

    resp = client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["status"] == "queued"
    assert body["progress"] == 0
    assert body["error"] is None


def test_get_unknown_job_returns_404(client):
    resp = client.get("/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_retry_unknown_job_returns_404(client):
    resp = client.post("/jobs/nonexistent-id/retry")
    assert resp.status_code == 404


def test_retry_non_error_job_rejected(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]

    resp = client.post(f"/jobs/{job_id}/retry")
    assert resp.status_code == 409


def test_retry_analysis_error_respawns_pipeline(client, monkeypatch):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.status = app_module.JobStatus.ERROR
    job.error = "API limit"

    calls = []
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *args: calls.append(args))

    resp = client.post(f"/jobs/{job_id}/retry")
    assert resp.status_code == 202
    assert calls == [(job_id,)]


def test_retry_non_resumable_error_rejected(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.status = app_module.JobStatus.ERROR
    job.resumable = False

    resp = client.post(f"/jobs/{job_id}/retry")
    assert resp.status_code == 409


def test_retry_render_error_rejected_use_render_endpoint_instead(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.status = app_module.JobStatus.ERROR
    job.segments = ["fake segment"]

    resp = client.post(f"/jobs/{job_id}/retry")
    assert resp.status_code == 409
    assert "Render" in resp.json()["detail"]


def test_continue_unknown_job_returns_404(client):
    resp = client.post("/jobs/nonexistent-id/continue")
    assert resp.status_code == 404


def test_continue_rejected_when_not_at_checkpoint(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]  # status queued, bukan jeda preview

    resp = client.post(f"/jobs/{job_id}/continue")
    assert resp.status_code == 409


@pytest.mark.parametrize(
    "status", [app_module.JobStatus.DOWNLOAD_READY, app_module.JobStatus.TRANSCRIPT_READY]
)
def test_continue_dispatches_next_stage_at_checkpoint(client, monkeypatch, status):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.status = status

    calls = []
    monkeypatch.setattr(app_module, "_spawn", lambda fn, *args: calls.append(args))

    resp = client.post(f"/jobs/{job_id}/continue")
    assert resp.status_code == 202
    assert calls == [(job_id,)]


def test_get_job_includes_video_preview_fields(client):
    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.video_title = "Judul Video"
    job.video_duration = 42
    job.video_width = 1920
    job.video_height = 1080
    job.video_thumbnail = "https://example.com/thumb.jpg"

    body = client.get(f"/jobs/{job_id}").json()
    assert body["video_title"] == "Judul Video"
    assert body["video_duration"] == 42
    assert body["video_width"] == 1920
    assert body["video_height"] == 1080
    assert body["video_thumbnail"] == "https://example.com/thumb.jpg"


def test_get_transcript_joins_words(client):
    from pipeline.transcribe import TranscriptWord

    job_id = client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]
    job = app_module.job_manager.get_job(job_id)
    job.words = [
        TranscriptWord(word="halo", start=0.0, end=0.3),
        TranscriptWord(word="dunia", start=0.3, end=0.6),
    ]

    resp = client.get(f"/jobs/{job_id}/transcript")
    assert resp.status_code == 200
    assert resp.json()["text"] == "halo dunia"


def test_get_transcript_unknown_job_404(client):
    assert client.get("/jobs/nope/transcript").status_code == 404
