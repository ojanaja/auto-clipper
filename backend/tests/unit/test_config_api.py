import json

import pytest
from fastapi.testclient import TestClient

from app import app
from config import AppConfig, save_config


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    return TestClient(app)


def test_get_config_returns_public_defaults(client):
    resp = client.get("/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["aspect_ratio"] == "9:16"
    assert data["resolution"] == 1080
    assert "gemini_api_key" not in data
    assert "anthropic_api_key" not in data
    assert data["gemini_key_set"] is False
    assert data["anthropic_key_set"] is False


def test_put_config_updates_fields(client):
    resp = client.put("/config", json={"aspect_ratio": "1:1", "resolution": 720})
    assert resp.status_code == 200
    data = resp.json()
    assert data["aspect_ratio"] == "1:1"
    assert data["resolution"] == 720
    assert data["gemini_key_set"] is False


def test_put_config_empty_key_does_not_overwrite_existing_key(client, tmp_path):
    cfg = AppConfig(gemini_api_key="secret123")
    save_config(cfg)

    resp = client.put("/config", json={"aspect_ratio": "16:9"})
    assert resp.status_code == 200
    assert resp.json()["gemini_key_set"] is True

    # Verify file masih menyimpan key lama.
    saved = json.loads((tmp_path / "config.json").read_text())
    assert saved["gemini_api_key"] == "secret123"


def test_put_config_sets_key_when_non_empty(client):
    resp = client.put("/config", json={"gemini_api_key": "newkey"})
    assert resp.status_code == 200
    assert resp.json()["gemini_key_set"] is True


def test_put_config_invalid_aspect_ratio(client):
    resp = client.put("/config", json={"aspect_ratio": "3:2"})
    assert resp.status_code == 422
    assert "aspect_ratio" in resp.text


def test_put_config_invalid_duration(client):
    resp = client.put("/config", json={"duration_min": 90, "duration_max": 30})
    assert resp.status_code == 422
    assert "duration_min" in resp.text or "duration" in resp.text


def test_put_config_unknown_field_ignored(client):
    resp = client.put("/config", json={"foo": "bar", "resolution": 480})
    assert resp.status_code == 200
    assert resp.json()["resolution"] == 480
