from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from job_manager import JobManager, JobNotFoundError
from progress import ProgressBroadcaster

app = FastAPI(title="AutoClip Lokal Backend")
job_manager = JobManager()
broadcaster = ProgressBroadcaster()


class CreateJobRequest(BaseModel):
    youtube_url: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs", status_code=201)
def create_job(req: CreateJobRequest):
    job = job_manager.create_job(req.youtube_url)
    return {"job_id": job.job_id, "status": job.status.value}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        job = job_manager.get_job(job_id)
    except JobNotFoundError:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan") from None
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "progress": job.progress,
        "error": job.error,
    }


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
