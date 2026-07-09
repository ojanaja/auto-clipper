"""Integration test download nyata terhadap YouTube.

Tidak jalan di CI reguler (deselect via addopts). Jalankan manual:
    pytest -m integration tests/integration/test_download_real.py
"""

from pathlib import Path

import pytest

from pipeline.download import download_video

# Video publik pendek yang stabil (Me at the zoo, 19 detik).
SHORT_PUBLIC_VIDEO = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


@pytest.mark.integration
def test_download_real_short_video(tmp_path):
    meta = download_video(SHORT_PUBLIC_VIDEO, tmp_path)
    assert meta.video_id == "jNQXAC9IVRw"
    assert meta.duration > 0
    assert Path(meta.filepath).exists()
    assert Path(meta.filepath).stat().st_size > 0
