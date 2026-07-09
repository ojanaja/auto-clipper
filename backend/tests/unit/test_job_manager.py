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
        JobStatus.TRANSCRIBING,
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
        JobStatus.TRANSCRIBING,
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
