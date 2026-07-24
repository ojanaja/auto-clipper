import json

import pytest
from fastapi.testclient import TestClient

from app import app
from customization import CustomizationConfig, save_customization


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTOCLIP_CONFIG_DIR", str(tmp_path))
    return TestClient(app)


def test_get_customization_returns_defaults(client):
    resp = client.get("/customization")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["subtitle"] == {"enabled": True}
    assert data["watermark"] == {"enabled": False}


def test_put_customization_updates_top_level_enabled(client):
    resp = client.put("/customization", json={"enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_put_customization_partial_section_update_preserves_other_fields(client):
    resp = client.put("/customization", json={"watermark": {"enabled": True}})
    assert resp.status_code == 200
    data = resp.json()
    assert data["watermark"]["enabled"] is True
    # Section lain tak ikut berubah.
    assert data["subtitle"]["enabled"] is True


def test_put_customization_persists_to_disk(client, tmp_path):
    client.put("/customization", json={"color_grade": {"enabled": True}})
    saved = json.loads((tmp_path / "customization.json").read_text())
    assert saved["color_grade"]["enabled"] is True


def test_put_customization_unknown_field_ignored(client):
    resp = client.put("/customization", json={"foo": "bar", "enabled": True})
    assert resp.status_code == 200
    assert resp.json()["enabled"] is True


def test_reset_customization_restores_defaults(client):
    cfg = CustomizationConfig(enabled=True)
    cfg.watermark.enabled = True
    save_customization(cfg)

    resp = client.post("/customization/reset")
    assert resp.status_code == 200
    data = resp.json()
    assert data["enabled"] is False
    assert data["watermark"]["enabled"] is False

    # Verify benar-benar tersimpan, bukan cuma response sesaat.
    assert client.get("/customization").json() == data
