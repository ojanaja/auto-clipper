import pytest
from fastapi.testclient import TestClient

from app import app, broadcaster


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _create_job(client):
    return client.post(
        "/jobs", json={"youtube_url": "https://www.youtube.com/watch?v=abc123"}
    ).json()["job_id"]


def test_ws_receives_published_events_in_order(client):
    job_id = _create_job(client)
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        # Event pembuka menandakan subscription aktif — hindari race publish-sebelum-subscribe.
        assert ws.receive_json() == {"stage": "connected", "progress": 0, "message": ""}

        broadcaster.publish(job_id, {"stage": "downloading", "progress": 10, "message": "mulai"})
        broadcaster.publish(job_id, {"stage": "downloading", "progress": 50, "message": "separuh"})

        assert ws.receive_json() == {"stage": "downloading", "progress": 10, "message": "mulai"}
        assert ws.receive_json() == {"stage": "downloading", "progress": 50, "message": "separuh"}


def test_ws_only_receives_events_for_own_job(client):
    job_a = _create_job(client)
    job_b = _create_job(client)
    with client.websocket_connect(f"/ws/jobs/{job_a}") as ws:
        ws.receive_json()  # connected

        broadcaster.publish(job_b, {"stage": "downloading", "progress": 99, "message": "lain"})
        broadcaster.publish(job_a, {"stage": "downloading", "progress": 5, "message": "punyaku"})

        # Event pertama yang diterima harus milik job_a, bukan job_b.
        assert ws.receive_json()["message"] == "punyaku"
