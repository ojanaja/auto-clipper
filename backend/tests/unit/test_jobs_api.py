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
