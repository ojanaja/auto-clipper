import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    READY = "ready"
    RENDERING = "rendering"
    DONE = "done"
    ERROR = "error"


# Urutan pipeline; transisi maju hanya boleh ke tahap tepat berikutnya.
_PIPELINE_ORDER = [
    JobStatus.QUEUED,
    JobStatus.DOWNLOADING,
    JobStatus.TRANSCRIBING,
    JobStatus.ANALYZING,
    JobStatus.READY,
    JobStatus.RENDERING,
    JobStatus.DONE,
]

_TERMINAL = {JobStatus.DONE, JobStatus.ERROR}


class JobNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


@dataclass
class Job:
    youtube_url: str
    job_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: JobStatus = JobStatus.QUEUED
    progress: int = 0
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class JobManager:
    def __init__(self):
        self._jobs: dict[str, Job] = {}

    def create_job(self, youtube_url: str) -> Job:
        job = Job(youtube_url=youtube_url)
        self._jobs[job.job_id] = job
        return job

    def get_job(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise JobNotFoundError(f"Job tidak ditemukan: {job_id}") from None

    def transition(self, job_id: str, new_status: JobStatus, error: str | None = None) -> Job:
        job = self.get_job(job_id)

        if job.status in _TERMINAL:
            raise InvalidTransitionError(f"{job.status.value} bersifat terminal")

        if new_status == JobStatus.ERROR:
            job.status = JobStatus.ERROR
            job.error = error
            return job

        current_idx = _PIPELINE_ORDER.index(job.status)
        target_idx = _PIPELINE_ORDER.index(new_status)
        if target_idx != current_idx + 1:
            raise InvalidTransitionError(
                f"Transisi tidak valid: {job.status.value} -> {new_status.value}"
            )

        job.status = new_status
        job.progress = 0
        return job

    def set_progress(self, job_id: str, progress: int) -> Job:
        job = self.get_job(job_id)
        if not 0 <= progress <= 100:
            raise ValueError(f"Progress harus 0-100, dapat: {progress}")
        job.progress = progress
        return job
