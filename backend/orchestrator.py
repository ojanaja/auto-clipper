import re
import sys
import tempfile
from pathlib import Path

import anthropic

from config import load_config, resolve_output_dir
from job_manager import JobManager, JobStatus
from pipeline.crop_path import build_crop_path
from pipeline.download import InvalidURLError, VideoUnavailableError, download_video
from pipeline.face_detect import detect_faces_sampled, sample_frames
from pipeline.highlight import find_highlights
from pipeline.llm_client import LLMAuthError, make_llm_client
from pipeline.render import probe_dimensions, render_segment
from pipeline.speaker import build_active_timeline, compute_motion_scores
from pipeline.transcribe import transcribe_audio

# Kesalahan yang PASTI gagal lagi kalau diulang tanpa user memperbaiki
# sesuatu (URL salah, video privat, API key ditolak/belum diset) -> jangan
# tampilkan tombol "Coba Lagi". Selain ini dianggap resumable (jaringan
# putus, server API down, dll) -- default aman: klik retry yang gagal lagi
# lebih ringan daripada menyembunyikan tombol padahal sebenarnya bisa diulang.
_NON_RESUMABLE_ERRORS = (
    InvalidURLError,
    VideoUnavailableError,
    LLMAuthError,
    anthropic.AuthenticationError,
    anthropic.PermissionDeniedError,
    anthropic.BadRequestError,
    anthropic.NotFoundError,
    anthropic.UnprocessableEntityError,
    anthropic.RequestTooLargeError,
)


def _is_resumable(exc: Exception) -> bool:
    return not isinstance(exc, _NON_RESUMABLE_ERRORS)


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
        config_provider=load_config,
        detect_faces_fn=detect_faces_sampled,
        sample_frames_fn=sample_frames,
        build_active_timeline_fn=build_active_timeline,
        build_crop_path_fn=build_crop_path,
    ):
        self._jobs = job_manager
        self._broadcaster = broadcaster
        self._download = download_fn
        self._transcribe = transcribe_fn
        self._highlight = highlight_fn
        self._render = render_fn
        self._llm_client = llm_client
        self._config_provider = config_provider
        self._detect_faces = detect_faces_fn
        self._sample_frames = sample_frames_fn
        self._build_active_timeline = build_active_timeline_fn
        self._build_crop_path = build_crop_path_fn
        self._work_root = Path(work_root or tempfile.gettempdir()) / "autoclip"

    def _publish(
        self,
        job_id: str,
        stage: str,
        progress: int,
        message: str = "",
        resumable: bool | None = None,
    ):
        event = {"stage": stage, "progress": progress, "message": message}
        if resumable is not None:
            event["resumable"] = resumable
        self._broadcaster.publish(job_id, event)

    def run_analysis(self, job_id: str) -> None:
        """download -> transcribe -> highlight; status queued -> ... -> ready.

        Retry setelah error: tahap yang hasilnya sudah ada (video_path/words)
        dilewati, jadi user tidak perlu mengulang dari unduh (checkpoint).
        ponytail: skip pakai truthy check; audio bisu yang sah menghasilkan
        words=[] akan re-transkrip saat retry (boros tapi bukan bug), upgrade
        ke flag boolean terpisah kalau kasus ini ternyata sering kejadian.

        Exception dari tahap manapun ditangkap: job jadi error dengan pesan
        yang bisa dibaca user, tidak pernah crash keluar.
        """
        job = self._jobs.get_job(job_id)
        work_dir = self._work_root / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        if job.status == JobStatus.ERROR:
            self._jobs.reset_for_retry(job_id)
        try:
            self._jobs.transition(job_id, JobStatus.DOWNLOADING)
            if job.video_path:
                self._publish(job_id, "downloading", 100, "Video sudah ada, lewati unduh")
            else:
                self._publish(job_id, "downloading", 0, "Mengunduh video")
                meta = self._download(
                    job.youtube_url,
                    work_dir,
                    progress_cb=lambda pct, msg: self._publish(job_id, "downloading", pct, msg),
                )
                job.video_path = meta.filepath

            cfg = self._config_provider()

            self._jobs.transition(job_id, JobStatus.TRANSCRIBING)
            if job.words:
                self._publish(job_id, "transcribing", 100, "Transkrip sudah ada, lewati")
            else:
                self._publish(job_id, "transcribing", 0, "Transkripsi audio")
                job.words = self._transcribe(
                    job.video_path,
                    model_size=cfg.whisper_model,
                    progress_cb=lambda pct, msg: self._publish(job_id, "transcribing", pct, msg),
                )

            self._jobs.transition(job_id, JobStatus.ANALYZING)
            self._publish(job_id, "analyzing", 0, "Mencari momen menarik")
            if self._llm_client is None:
                # Lazy: resolve dari konfigurasi/env di sini supaya key yang
                # hilang jadi pesan error job yang jelas, bukan crash startup.
                self._llm_client = make_llm_client(
                    provider=cfg.llm_provider,
                    gemini_api_key=cfg.gemini_api_key or None,
                    anthropic_api_key=cfg.anthropic_api_key or None,
                    model=cfg.llm_model or None,
                )
            job.segments = self._highlight(
                job.words,
                self._llm_client,
                duration_min=cfg.duration_min,
                duration_max=cfg.duration_max,
                count=cfg.segment_count,
            )

            self._jobs.transition(job_id, JobStatus.READY)
            self._publish(job_id, "ready", 100, f"{len(job.segments)} segmen kandidat")
        except Exception as e:
            resumable = _is_resumable(e)
            self._jobs.transition(job_id, JobStatus.ERROR, error=str(e), resumable=resumable)
            self._publish(job_id, "error", 0, str(e), resumable=resumable)

    def run_render(
        self, job_id: str, segment_ids: list[str], output_dir: Path | None = None
    ) -> None:
        """Render batch segmen terpilih; tiap klip punya state sendiri.

        Kegagalan satu klip tidak menghentikan klip lain — job tetap selesai
        dengan clip status error per segmen yang gagal (sesuai PRD keandalan).
        Job bisa di-render ulang dari status DONE/ERROR.

        ponytail: render sekuensial (concurrency 1); paralel terbatas kalau
        render batch besar terasa lambat di device ber-GPU.
        """
        job = self._jobs.get_job(job_id)
        for seg_id in segment_ids:
            if not seg_id.isdigit() or int(seg_id) >= len(job.segments):
                raise ValueError(f"Segment id tidak dikenal: {seg_id}")

        # Izinkan render ulang setelah selesai/gagal sebelumnya.
        self._jobs.reset_for_render(job_id)

        try:
            cfg = self._config_provider()
            if output_dir is None:
                output_dir = resolve_output_dir(cfg)
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            work_dir = self._work_root / job_id
            work_dir.mkdir(parents=True, exist_ok=True)

            output_width, output_height = cfg.output_dimensions()
            target_ratio = cfg.target_ratio()
            face_tracking_enabled = cfg.face_tracking_enabled

            frame_w, frame_h = 0, 0
            if face_tracking_enabled and job.video_path:
                try:
                    frame_w, frame_h = probe_dimensions(job.video_path)
                except Exception:
                    face_tracking_enabled = False

            self._jobs.transition(job_id, JobStatus.RENDERING)
            total = len(segment_ids)
            successes = 0
            failure_msgs: list[str] = []
            for i, seg_id in enumerate(segment_ids):
                segment = job.segments[int(seg_id)]
                filename = f"{job_id[:8]}_{seg_id}_{_safe_filename(segment.title)}.mp4"
                output_path = output_dir / filename

                # Checkpoint: klip yang sudah sukses & filenya masih ada dilewati,
                # supaya retry render cuma mengulang klip yang gagal saja.
                existing = job.clips.get(seg_id)
                if (
                    existing
                    and existing["status"] == "done"
                    and existing["path"]
                    and Path(existing["path"]).exists()
                ):
                    successes += 1
                    overall = (i + 1) * 100 // total
                    msg = f"Klip {i + 1}/{total} sudah ada, lewati"
                    self._publish(job_id, "rendering", overall, msg)
                    continue

                job.clips[seg_id] = {"status": "rendering", "progress": 0, "path": None}

                def on_clip_progress(clip_pct, _msg, i=i, seg_id=seg_id):
                    # Petakan progress klip ke progress keseluruhan batch.
                    overall = (i * 100 + clip_pct) // total
                    job.clips[seg_id]["progress"] = clip_pct
                    self._publish(
                        job_id, "rendering", overall, f"Klip {i + 1}/{total} • {clip_pct}%"
                    )

                on_clip_progress(0, "")
                crop_path = None
                try:
                    if face_tracking_enabled:
                        timeline = self._detect_faces(
                            job.video_path,
                            segment.start,
                            segment.end,
                            fps=cfg.face_sample_fps,
                        )
                        frames, scale = self._sample_frames(
                            job.video_path,
                            segment.start,
                            segment.end,
                            fps=cfg.face_sample_fps,
                        )
                        motion_scores = compute_motion_scores(frames, scale, timeline)
                        active_timeline = self._build_active_timeline(
                            timeline, motion_scores, min_dwell_s=cfg.speaker_min_dwell_s
                        )
                        crop_path = self._build_crop_path(
                            frame_w, frame_h, active_timeline, target_ratio
                        )
                except Exception as e:
                    self._publish(
                        job_id,
                        "rendering",
                        i * 100 // total,
                        f"Face-tracking gagal untuk klip {seg_id}, fallback center: {e}",
                    )

                try:
                    self._render(
                        job.video_path,
                        segment,
                        job.words,
                        output_path,
                        work_dir=work_dir,
                        progress_cb=on_clip_progress,
                        target_ratio=target_ratio,
                        output_width=output_width,
                        output_height=output_height,
                        subtitle_enabled=cfg.subtitle_enabled,
                        subtitle_font_size=cfg.subtitle_font_size,
                        encoder=cfg.encoder,
                        crop_path=crop_path,
                    )
                    job.clips[seg_id] = {
                        "status": "done",
                        "progress": 100,
                        "path": str(output_path),
                    }
                    successes += 1
                except Exception as e:
                    msg = f"Klip {seg_id} gagal: {e}"
                    failure_msgs.append(msg)
                    job.clips[seg_id] = {"status": "error", "progress": 0, "path": None}
                    print(msg, file=sys.stderr, flush=True)
                    self._publish(job_id, "rendering", i * 100 // total, msg)

            if successes:
                self._jobs.transition(job_id, JobStatus.DONE)
                self._publish(job_id, "done", 100, "Render selesai")
            else:
                # Ambil dari BELAKANG: ffmpeg selalu cetak banner version/build config
                # dulu, pesan error sungguhan ada di baris-baris terakhir stderr.
                snippet = failure_msgs[0] if failure_msgs else "tidak diketahui"
                detail = f"Semua klip gagal dirender. Contoh: {snippet[-300:]}"
                self._jobs.transition(job_id, JobStatus.ERROR, error=detail)
                self._publish(job_id, "error", 0, detail)
        except Exception as e:
            self._jobs.transition(job_id, JobStatus.ERROR, error=str(e))
            self._publish(job_id, "error", 0, str(e))
