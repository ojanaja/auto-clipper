import re
import tempfile
from pathlib import Path

from job_manager import JobManager, JobStatus
from pipeline.download import download_video
from pipeline.highlight import find_highlights
from pipeline.llm_client import make_llm_client
from pipeline.render import render_segment
from pipeline.transcribe import transcribe_audio


def _safe_filename(text: str, max_len: int = 40) -> str:
    return re.sub(r"[^\w\-]+", "_", text)[:max_len].strip("_")


class PipelineOrchestrator:
    """Merangkai modul pipeline sesuai urutan dan mengelola status job.

    Semua dependency injectable supaya bisa di-stub di test tanpa I/O.
    Method sinkron; pemanggil (API layer) yang menjalankannya di worker thread.
    """

    def __init__(
        self,
        job_manager: JobManager,
        broadcaster,
        *,
        download_fn=download_video,
        transcribe_fn=transcribe_audio,
        highlight_fn=find_highlights,
        render_fn=render_segment,
        llm_client=None,
        work_root: Path | None = None,
    ):
        self._jobs = job_manager
        self._broadcaster = broadcaster
        self._download = download_fn
        self._transcribe = transcribe_fn
        self._highlight = highlight_fn
        self._render = render_fn
        self._llm_client = llm_client
        self._work_root = Path(work_root or tempfile.gettempdir()) / "autoclip"

    def _publish(self, job_id: str, stage: str, progress: int, message: str = ""):
        self._broadcaster.publish(
            job_id, {"stage": stage, "progress": progress, "message": message}
        )

    def run_analysis(self, job_id: str) -> None:
        """download -> transcribe -> highlight; status queued -> ... -> ready.

        Exception dari tahap manapun ditangkap: job jadi error dengan pesan
        yang bisa dibaca user, tidak pernah crash keluar.
        """
        job = self._jobs.get_job(job_id)
        work_dir = self._work_root / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._jobs.transition(job_id, JobStatus.DOWNLOADING)
            self._publish(job_id, "downloading", 0, "Mengunduh video")
            meta = self._download(
                job.youtube_url,
                work_dir,
                progress_cb=lambda pct, msg: self._publish(job_id, "downloading", pct, msg),
            )
            job.video_path = meta.filepath

            self._jobs.transition(job_id, JobStatus.TRANSCRIBING)
            self._publish(job_id, "transcribing", 0, "Transkripsi audio")
            job.words = self._transcribe(
                meta.filepath,
                progress_cb=lambda pct, msg: self._publish(job_id, "transcribing", pct, msg),
            )

            self._jobs.transition(job_id, JobStatus.ANALYZING)
            self._publish(job_id, "analyzing", 0, "Mencari momen menarik")
            if self._llm_client is None:
                # Lazy: resolve dari env di sini supaya key yang hilang jadi
                # pesan error job yang jelas, bukan crash saat startup app.
                self._llm_client = make_llm_client()
            job.segments = self._highlight(job.words, self._llm_client)

            self._jobs.transition(job_id, JobStatus.READY)
            self._publish(job_id, "ready", 100, f"{len(job.segments)} segmen kandidat")
        except Exception as e:
            self._jobs.transition(job_id, JobStatus.ERROR, error=str(e))
            self._publish(job_id, "error", 0, str(e))

    def run_render(self, job_id: str, segment_ids: list[str], output_dir: Path) -> None:
        """Render batch segmen terpilih; tiap klip punya state sendiri.

        Kegagalan satu klip tidak menghentikan klip lain — job tetap selesai
        dengan clip status error per segmen yang gagal (sesuai PRD keandalan).

        ponytail: render sekuensial (concurrency 1); paralel terbatas kalau
        render batch besar terasa lambat di device ber-GPU.
        """
        job = self._jobs.get_job(job_id)
        for seg_id in segment_ids:
            if not seg_id.isdigit() or int(seg_id) >= len(job.segments):
                raise ValueError(f"Segment id tidak dikenal: {seg_id}")

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        work_dir = self._work_root / job_id
        work_dir.mkdir(parents=True, exist_ok=True)

        self._jobs.transition(job_id, JobStatus.RENDERING)
        total = len(segment_ids)
        for i, seg_id in enumerate(segment_ids):
            segment = job.segments[int(seg_id)]
            filename = f"{job_id[:8]}_{seg_id}_{_safe_filename(segment.title)}.mp4"
            output_path = output_dir / filename
            job.clips[seg_id] = {"status": "rendering", "progress": 0, "path": None}
            self._publish(job_id, "rendering", i * 100 // total, f"Render klip {seg_id}")
            try:
                self._render(job.video_path, segment, job.words, output_path, work_dir=work_dir)
                job.clips[seg_id] = {"status": "done", "progress": 100, "path": str(output_path)}
            except Exception as e:
                job.clips[seg_id] = {"status": "error", "progress": 0, "path": None}
                self._publish(job_id, "rendering", i * 100 // total, f"Klip {seg_id} gagal: {e}")

        self._jobs.transition(job_id, JobStatus.DONE)
        self._publish(job_id, "done", 100, "Render selesai")
