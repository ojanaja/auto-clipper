"""CLI entrypoint for the PyInstaller-packaged backend sidecar."""

import os
import sys

import uvicorn


def _load_env_file():
    """Load bundled .env file shipped via Electron Builder extraResources."""
    candidates = [
        os.environ.get("AUTOCLIP_ENV_FILE"),
        os.path.join(os.path.dirname(os.path.dirname(sys.executable)), ".env"),
        os.path.join(os.path.dirname(sys.executable), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for env_path in candidates:
        if not env_path or not os.path.isfile(env_path):
            continue
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key and key not in os.environ:
                    os.environ[key] = value.strip().strip('"').strip("'")
        print(f"Loaded env file: {env_path}")
        break


def main():
    _load_env_file()

    port = int(os.environ.get("AUTOCLIP_BACKEND_PORT", "8237"))
    host = os.environ.get("AUTOCLIP_BACKEND_HOST", "127.0.0.1")

    # Make bundled ffmpeg/ffprobe discoverable if the bin/ directory exists
    # next to this executable (set by Electron via PATH) or in the cwd.
    exe_dir = os.path.dirname(sys.executable)
    for bin_dir in (
        os.path.join(exe_dir, "bin"),
        os.path.join(os.getcwd(), "bin"),
    ):
        if os.path.isdir(bin_dir) and bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")

    uvicorn.run("app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
