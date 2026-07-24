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
    assert data["subtitle"]["enabled"] is True
    assert data["subtitle"]["template"] == "karaoke_pop"
    assert data["watermark"]["enabled"] is False
    assert data["watermark"]["text"] == "AutoClip"
    assert data["overlay_gambar"] == {
        "enabled": False,
        "image_path": "",
        "size": 20,
        "opacity": 100,
        "rotate": 0.0,
        "pos_x": 85,
        "pos_y": 12,
    }


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


def test_put_customization_section_partial_update_preserves_sibling_fields(client):
    client.put("/customization", json={"subtitle": {"template": "hormozi"}})
    resp = client.put("/customization", json={"subtitle": {"opacity": 60}})
    assert resp.status_code == 200
    data = resp.json()["subtitle"]
    assert data["opacity"] == 60
    assert data["template"] == "hormozi"  # tak ketimpa update sebelumnya


def test_put_customization_invalid_subtitle_template_rejected(client):
    resp = client.put("/customization", json={"subtitle": {"template": "invalid"}})
    assert resp.status_code == 422
    assert "template" in resp.text


def test_put_customization_invalid_subtitle_opacity_rejected(client):
    resp = client.put("/customization", json={"subtitle": {"opacity": 200}})
    assert resp.status_code == 422
    assert "opacity" in resp.text


def test_put_customization_invalid_hex_color_rejected(client):
    resp = client.put("/customization", json={"subtitle": {"text_color": "white"}})
    assert resp.status_code == 422
    assert "text_color" in resp.text


def test_put_customization_invalid_field_does_not_persist(client, tmp_path):
    client.put("/customization", json={"subtitle": {"template": "hormozi"}})
    resp = client.put("/customization", json={"subtitle": {"opacity": 999}})
    assert resp.status_code == 422

    saved = json.loads((tmp_path / "customization.json").read_text())
    assert saved["subtitle"]["template"] == "hormozi"
    assert saved["subtitle"]["opacity"] == 100


def test_put_customization_color_grade_partial_update(client):
    client.put("/customization", json={"color_grade": {"preset": "cinematic", "vignette": 0.35}})
    resp = client.put("/customization", json={"color_grade": {"contrast": 1.2}})
    assert resp.status_code == 200
    data = resp.json()["color_grade"]
    assert data["contrast"] == 1.2
    assert data["preset"] == "cinematic"  # tak ketimpa
    assert data["vignette"] == 0.35


def test_put_customization_invalid_color_grade_preset_rejected(client):
    resp = client.put("/customization", json={"color_grade": {"preset": "invalid"}})
    assert resp.status_code == 422
    assert "preset" in resp.text


def test_put_customization_invalid_color_grade_contrast_rejected(client):
    resp = client.put("/customization", json={"color_grade": {"contrast": 5.0}})
    assert resp.status_code == 422
    assert "contrast" in resp.text


def test_put_customization_watermark_partial_update_preserves_sibling_fields(client):
    client.put("/customization", json={"watermark": {"text": "Klip Keren", "rotate": -15}})
    resp = client.put("/customization", json={"watermark": {"enabled": True}})
    assert resp.status_code == 200
    data = resp.json()["watermark"]
    assert data["enabled"] is True
    assert data["text"] == "Klip Keren"  # tak ketimpa
    assert data["rotate"] == -15


def test_put_customization_invalid_watermark_opacity_rejected(client):
    resp = client.put("/customization", json={"watermark": {"opacity": 999}})
    assert resp.status_code == 422
    assert "watermark.opacity" in resp.text


def test_put_customization_invalid_overlay_sumber_color_rejected(client):
    resp = client.put("/customization", json={"overlay_sumber": {"color": "notacolor"}})
    assert resp.status_code == 422
    assert "overlay_sumber.color" in resp.text


def test_put_customization_overlay_gambar_partial_update(client):
    client.put("/customization", json={"overlay_gambar": {"image_path": "/tmp/logo.png"}})
    resp = client.put("/customization", json={"overlay_gambar": {"size": 40}})
    assert resp.status_code == 200
    data = resp.json()["overlay_gambar"]
    assert data["size"] == 40
    assert data["image_path"] == "/tmp/logo.png"  # tak ketimpa


def test_put_customization_invalid_overlay_gambar_rotate_rejected(client):
    resp = client.put("/customization", json={"overlay_gambar": {"rotate": 500}})
    assert resp.status_code == 422
    assert "overlay_gambar.rotate" in resp.text


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
