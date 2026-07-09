"""CLI entrypoint for the PyInstaller-packaged backend sidecar."""

import os
import sys

import uvicorn


def main():
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
