# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AutoClip Lokal backend sidecar."""

import os
import sys

from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# PyInstaller does not provide __file__ in the spec namespace. The build script
# sets AUTOCLIP_BACKEND_ROOT to the backend directory; fall back to cwd.
PROJECT_ROOT = os.environ.get("AUTOCLIP_BACKEND_ROOT", os.getcwd())
ELECTRON_BUILD_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "electron-app", "build", "backend")

# Make sure project modules are importable during analysis.
sys.path.insert(0, PROJECT_ROOT)

YUNET_MODEL_FILENAME = "face_detection_yunet_2023mar.onnx"

added_datas = []
added_datas += collect_data_files(
    "faster_whisper", includes=["assets/silero_vad_v6.onnx"]
)
added_datas += collect_data_files("certifi")

bundled_model = os.path.join(PROJECT_ROOT, "models", YUNET_MODEL_FILENAME)
if os.path.exists(bundled_model):
    added_datas.append((bundled_model, "models"))

added_binaries = []
added_binaries += collect_dynamic_libs("ctranslate2")
added_binaries += collect_dynamic_libs("onnxruntime")
added_binaries += collect_dynamic_libs("av")

hiddenimports = [
    # ASGI server
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    # Web framework
    "fastapi",
    "websockets",
    "httptools",
    "uvloop",
    "watchfiles",
    "h11",
    "anyio",
    "sniffio",
    "pydantic",
    "pydantic_core",
    "starlette",
    "typing_extensions",
    "typing_inspection",
    "annotated_types",
    "certifi",
    "idna",
    # YouTube download
    "yt_dlp",
    "yt_dlp.extractor",
    "yt_dlp.extractor._extractors",
    "yt_dlp.extractor.lazy_extractors",
    "yt_dlp.downloader",
    "yt_dlp.postprocessor",
    "Cryptodome",
    "brotli",
    "mutagen",
    # LLM clients
    "anthropic",
    "anthropic._client",
    "anthropic.resources",
    "httpx",
    "httpcore",
    "jiter",
    "distro",
    # Whisper stack
    "faster_whisper",
    "faster_whisper.audio",
    "faster_whisper.feature_extractor",
    "faster_whisper.tokenizer",
    "faster_whisper.transcribe",
    "faster_whisper.utils",
    "faster_whisper.vad",
    "faster_whisper.version",
    "ctranslate2",
    "ctranslate2.extensions",
    "ctranslate2.models",
    "ctranslate2.specs",
    "ctranslate2.converters",
    "ctranslate2._ext",
    "ctranslate2.logging",
    "ctranslate2.version",
    "onnxruntime",
    "tokenizers",
    "numpy",
    "av",
    "huggingface_hub",
    "huggingface_hub.constants",
    "huggingface_hub.file_download",
    "tqdm",
    "tqdm.auto",
    "fsspec",
    "yaml",
    "packaging",
    # Project modules
    "app",
    "job_manager",
    "orchestrator",
    "progress",
    "pipeline",
    "pipeline.download",
    "pipeline.transcribe",
    "pipeline.highlight",
    "pipeline.llm_client",
    "pipeline.render",
    "pipeline.subtitle",
    "pipeline.reframe",
]

a = Analysis(
    ["main_cli.py"],
    pathex=[PROJECT_ROOT],
    binaries=added_binaries,
    datas=added_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_mock",
        "pytest_cov",
        "ruff",
        "pre_commit",
        "tkinter",
        "matplotlib",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="autoclip-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Final executable is written to the distpath passed via --distpath (electron-app/build/backend).
print(f"Sidecar spec complete: {exe.name}")
