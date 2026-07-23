import pytest

from job_manager import InvalidTransitionError, JobManager, JobNotFoundError, JobStatus


@pytest.fixture
def manager():
    return JobManager()


def test_create_job_starts_queued(manager):
    job = manager.create_job("https://www.youtube.com/watch?v=abc123")
    assert job.status == JobStatus.QUEUED
    assert job.youtube_url == "https://www.youtube.com/watch?v=abc123"
    assert job.progress == 0
    assert job.error is None
    assert job.job_id


def test_get_job_returns_created_job(manager):
    job = manager.create_job("https://youtu.be/abc123")
    assert manager.get_job(job.job_id) is job


def test_get_unknown_job_raises(manager):
    with pytest.raises(JobNotFoundError):
        manager.get_job("nonexistent-id")


def test_valid_transition_chain(manager):
    job = manager.create_job("https://youtu.be/abc123")
    for status in [
        JobStatus.DOWNLOADING,
        JobStatus.DOWNLOAD_READY,
        JobStatus.TRANSCRIBING,
        JobStatus.TRANSCRIPT_READY,
        JobStatus.ANALYZING,
        JobStatus.READY,
        JobStatus.RENDERING,
        JobStatus.DONE,
    ]:
        manager.transition(job.job_id, status)
        assert job.status == status


@pytest.mark.parametrize(
    "from_status",
    [
        JobStatus.QUEUED,
        JobStatus.DOWNLOADING,
        JobStatus.DOWNLOAD_READY,
        JobStatus.TRANSCRIBING,
        JobStatus.TRANSCRIPT_READY,
        JobStatus.ANALYZING,
        JobStatus.READY,
        JobStatus.RENDERING,
    ],
)
def test_any_active_status_can_error(manager, from_status):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = from_status
    manager.transition(job.job_id, JobStatus.ERROR, error="boom")
    assert job.status == JobStatus.ERROR
    assert job.error == "boom"


def test_done_is_terminal(manager):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = JobStatus.DONE
    with pytest.raises(InvalidTransitionError):
        manager.transition(job.job_id, JobStatus.RENDERING)


def test_error_is_terminal(manager):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = JobStatus.ERROR
    with pytest.raises(InvalidTransitionError):
        manager.transition(job.job_id, JobStatus.QUEUED)


def test_skipping_stage_rejected(manager):
    job = manager.create_job("https://youtu.be/abc123")
    with pytest.raises(InvalidTransitionError):
        manager.transition(job.job_id, JobStatus.RENDERING)


def test_backward_transition_rejected(manager):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = JobStatus.ANALYZING
    with pytest.raises(InvalidTransitionError):
        manager.transition(job.job_id, JobStatus.DOWNLOADING)


def test_job_defaults_resumable_true(manager):
    job = manager.create_job("https://youtu.be/abc123")
    assert job.resumable is True


def test_transition_to_error_stores_resumable_flag(manager):
    job = manager.create_job("https://youtu.be/abc123")
    manager.transition(job.job_id, JobStatus.ERROR, error="boom", resumable=False)
    assert job.resumable is False


def test_reset_for_retry_from_error_goes_to_queued(manager):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = JobStatus.ERROR
    job.error = "boom"
    job.resumable = False
    manager.reset_for_retry(job.job_id)
    assert job.status == JobStatus.QUEUED
    assert job.error is None
    assert job.resumable is True


@pytest.mark.parametrize(
    "failed_at,expected_resume",
    [
        (JobStatus.DOWNLOADING, JobStatus.QUEUED),
        (JobStatus.TRANSCRIBING, JobStatus.DOWNLOAD_READY),
        (JobStatus.ANALYZING, JobStatus.TRANSCRIPT_READY),
    ],
)
def test_reset_for_retry_resumes_from_checkpoint(manager, failed_at, expected_resume):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = failed_at
    manager.transition(job.job_id, JobStatus.ERROR, error="boom")
    manager.reset_for_retry(job.job_id)
    assert job.status == expected_resume
    assert job.error is None
    assert job.error_stage is None


def test_reset_for_retry_noop_when_not_error(manager):
    job = manager.create_job("https://youtu.be/abc123")
    job.status = JobStatus.TRANSCRIBING
    manager.reset_for_retry(job.job_id)
    assert job.status == JobStatus.TRANSCRIBING


def test_set_progress(manager):
    job = manager.create_job("https://youtu.be/abc123")
    manager.set_progress(job.job_id, 42)
    assert job.progress == 42


def test_progress_out_of_range_rejected(manager):
    job = manager.create_job("https://youtu.be/abc123")
    with pytest.raises(ValueError):
        manager.set_progress(job.job_id, 101)
    with pytest.raises(ValueError):
        manager.set_progress(job.job_id, -1)
