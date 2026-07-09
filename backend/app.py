import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

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
    _spawn(orchestrator.run_render, job_id, req.segment_ids, _DEFAULT_OUTPUT_DIR)
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
