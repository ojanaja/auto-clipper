import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOAD_READY = "download_ready"
    TRANSCRIBING = "transcribing"
    TRANSCRIPT_READY = "transcript_ready"
    ANALYZING = "analyzing"
    READY = "ready"
    RENDERING = "rendering"
    DONE = "done"
    ERROR = "error"


# Urutan pipeline; transisi maju hanya boleh ke tahap tepat berikutnya.
# DOWNLOAD_READY/TRANSCRIPT_READY adalah jeda preview yang nunggu user klik
# "Lanjutkan" (lihat PipelineOrchestrator.dispatch) sebelum lanjut ke tahap berikutnya.
_PIPELINE_ORDER = [
    JobStatus.QUEUED,
    JobStatus.DOWNLOADING,
    JobStatus.DOWNLOAD_READY,
    JobStatus.TRANSCRIBING,
    JobStatus.TRANSCRIPT_READY,
    JobStatus.ANALYZING,
    JobStatus.READY,
    JobStatus.RENDERING,
    JobStatus.DONE,
]

_TERMINAL = {JobStatus.DONE, JobStatus.ERROR}

# Tahap PROCESSING (bukan jeda) yang gagal -> retry harus resume dari
# checkpoint SEBELUM tahap itu, bukan dari awal lagi (video/transkrip yang
# sudah ada dipakai ulang). Default ke QUEUED kalau error_stage tak diketahui
# (mis. test yang set job.status = ERROR langsung tanpa lewat transition()).
_RETRY_RESUME_STATUS = {
    JobStatus.DOWNLOADING: JobStatus.QUEUED,
    JobStatus.TRANSCRIBING: JobStatus.DOWNLOAD_READY,
    JobStatus.ANALYZING: JobStatus.TRANSCRIPT_READY,
}


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
    # True kalau retry masuk akal (mis. koneksi putus); False untuk kesalahan
    # yang pasti gagal lagi (URL invalid, API key ditolak) -> sembunyikan "Coba Lagi".
    resumable: bool = True
    # Tahap PROCESSING yang lagi jalan saat error terjadi (diisi transition());
    # dipakai reset_for_retry buat resume dari checkpoint yang tepat.
    error_stage: JobStatus | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Hasil pipeline (diisi orchestrator).
    video_path: str | None = None
    video_title: str = ""
    video_duration: int = 0
    video_width: int | None = None
    video_height: int | None = None
    video_thumbnail: str | None = None
    words: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    # State render per segmen: {segment_id: {status, progress, path}}.
    clips: dict = field(default_factory=dict)


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

    def transition(
        self,
        job_id: str,
        new_status: JobStatus,
        error: str | None = None,
        resumable: bool = True,
    ) -> Job:
        job = self.get_job(job_id)

        if job.status in _TERMINAL:
            raise InvalidTransitionError(f"{job.status.value} bersifat terminal")

        if new_status == JobStatus.ERROR:
            job.error_stage = job.status
            job.status = JobStatus.ERROR
            job.error = error
            job.resumable = resumable
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

    def reset_for_render(self, job_id: str) -> Job:
        """Izinkan render ulang dari status terminal (DONE/ERROR) -> READY."""
        job = self.get_job(job_id)
        if job.status in _TERMINAL:
            job.status = JobStatus.READY
            job.error = None
        return job

    def reset_for_retry(self, job_id: str) -> Job:
        """Izinkan retry setelah ERROR -> checkpoint sebelum tahap yang gagal.

        video_path/words/segments yang sudah ada TIDAK dihapus — orchestrator
        memakainya untuk melewati tahap yang sudah selesai (checkpoint).
        """
        job = self.get_job(job_id)
        if job.status == JobStatus.ERROR:
            job.status = _RETRY_RESUME_STATUS.get(job.error_stage, JobStatus.QUEUED)
            job.error = None
            job.error_stage = None
            job.resumable = True
        return job
