import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from config import AppConfig, ConfigError, load_config, resolve_output_dir, save_config
from job_manager import JobManager, JobNotFoundError
from orchestrator import PipelineOrchestrator
from progress import ProgressBroadcaster

app = FastAPI(title="AutoClip Lokal Backend")
job_manager = JobManager()
broadcaster = ProgressBroadcaster()
orchestrator = PipelineOrchestrator(job_manager, broadcaster)

_DEFAULT_OUTPUT_DIR = Path(
    os.environ.get("AUTOCLIP_OUTPUT_DIR", Path.home() / "Movies" / "AutoClip")
)


def _spawn(fn, *args):
    """Jalankan fn di worker thread daemon (dipatch sinkron di test)."""
    threading.Thread(target=fn, args=args, daemon=True).start()


class CreateJobRequest(BaseModel):
    youtube_url: str


class RenderRequest(BaseModel):
    segment_ids: list[str] = Field(min_length=1)


class ConfigUpdate(BaseModel):
    aspect_ratio: str | None = None
    resolution: int | None = None
    duration_min: int | None = None
    duration_max: int | None = None
    subtitle_enabled: bool | None = None
    subtitle_font_size: int | None = None
    whisper_model: str | None = None
    segment_count: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    encoder: str | None = None
    output_dir: str | None = None
    face_tracking_enabled: bool | None = None
    face_sample_fps: int | None = None
    speaker_min_dwell_s: float | None = None


def _get_job_or_404(job_id: str):
    try:
        return job_manager.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan") from None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=201)
def create_job(req: CreateJobRequest):
    job = job_manager.create_job(req.youtube_url)
    _spawn(orchestrator.run_analysis, job.job_id)
    return {"job_id": job.job_id, "status": job.status.value}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = _get_job_or_404(job_id)
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
    }


@app.get("/jobs/{job_id}/segments")
def get_segments(job_id: str):
    job = _get_job_or_404(job_id)
    return {
        "segments": [
            {
                "id": str(i),
                "start": s.start,
                "end": s.end,
                "score": s.score,
                "title": s.title,
                "reason": s.reason,
            }
            for i, s in enumerate(job.segments)
        ]
    }


@app.post("/jobs/{job_id}/render", status_code=202)
def start_render(job_id: str, req: RenderRequest):
    _get_job_or_404(job_id)
    cfg = load_config()
    output_dir = resolve_output_dir(cfg, fallback=_DEFAULT_OUTPUT_DIR)
    _spawn(orchestrator.run_render, job_id, req.segment_ids, output_dir)
    return {"render_job_id": job_id, "status": "queued"}


@app.get("/jobs/{job_id}/render-status")
def render_status(job_id: str):
    job = _get_job_or_404(job_id)
    return {
        "clips": [
            {"segment_id": sid, "status": c["status"], "progress": c["progress"]}
            for sid, c in job.clips.items()
        ]
    }


@app.get("/jobs/{job_id}/output")
def output_files(job_id: str):
    job = _get_job_or_404(job_id)
    files = []
    for sid, clip in job.clips.items():
        if clip["status"] == "done":
            segment = job.segments[int(sid)]
            files.append(
                {
                    "segment_id": sid,
                    "path": clip["path"],
                    "duration": segment.end - segment.start,
                }
            )
    return {"files": files}


@app.get("/config")
def get_config():
    cfg = load_config()
    return cfg.to_public_dict()


@app.put("/config")
def update_config(update: ConfigUpdate):
    cfg = load_config()
    update_dict = update.model_dump(exclude_unset=True)

    # API key kosong/absen tidak boleh menghapus key lama.
    for key_field in ("gemini_api_key", "anthropic_api_key"):
        if key_field in update_dict and not update_dict[key_field]:
            update_dict.pop(key_field)

    # Field tak dikenang sudah diabaikan Pydantic; unknown juga diabaikan
    # (FastAPI/Pydantic v2 otomatis menolak unknown, jadi tidak perlu filter).
    new_cfg = AppConfig.from_dict({**cfg.to_dict(), **update_dict})
    try:
        new_cfg.validate()
    except ConfigError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    save_config(new_cfg)
    return new_cfg.to_public_dict()


@app.websocket("/ws/jobs/{job_id}")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    await websocket.accept()
    queue = broadcaster.subscribe(job_id)
    await websocket.send_json({"stage": "connected", "progress": 0, "message": ""})
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        broadcaster.unsubscribe(job_id, queue)
