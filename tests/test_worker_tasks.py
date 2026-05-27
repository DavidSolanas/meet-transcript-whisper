"""Tests for Celery worker task state handling."""

import datetime
from types import SimpleNamespace

from src.core.models import JobData, JobStatus
from src.worker import tasks


def make_job() -> JobData:
    """Create a minimal processing job for task state tests."""
    return JobData(
        job_id="job-123",
        status=JobStatus.PROCESSING,
        progress=20.0,
        message="Running diarization and transcription",
        created_at=datetime.datetime.now(datetime.UTC),
        file_path="/tmp/audio.wav",
    )


def test_failure_stays_processing_when_retry_available(monkeypatch):
    """A retryable failure should not expose the job as failed yet."""
    job = make_job()
    saved_jobs: list[JobData] = []
    task = SimpleNamespace(request=SimpleNamespace(retries=1), max_retries=3)

    monkeypatch.setattr(tasks, "get_job", lambda job_id: job)
    monkeypatch.setattr(tasks, "save_job", saved_jobs.append)

    can_retry = tasks.update_job_failure_for_retry(task, "job-123", RuntimeError("boom"))

    assert can_retry is True
    assert saved_jobs == [job]
    assert job.status == JobStatus.PROCESSING
    assert job.error is None
    assert job.message == "Retrying transcription (2/3)"


def test_failure_marks_failed_when_retries_exhausted(monkeypatch):
    """The job should only become failed once Celery has no retries left."""
    job = make_job()
    saved_jobs: list[JobData] = []
    task = SimpleNamespace(request=SimpleNamespace(retries=3), max_retries=3)

    monkeypatch.setattr(tasks, "get_job", lambda job_id: job)
    monkeypatch.setattr(tasks, "save_job", saved_jobs.append)

    can_retry = tasks.update_job_failure_for_retry(task, "job-123", RuntimeError("boom"))

    assert can_retry is False
    assert saved_jobs == [job]
    assert job.status == JobStatus.FAILED
    assert job.error == "boom"
    assert job.message == "Transcription failed"
