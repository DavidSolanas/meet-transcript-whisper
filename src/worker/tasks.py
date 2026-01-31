"""Celery tasks for transcription processing."""

from datetime import datetime
from pathlib import Path

import redis
import structlog

from src.core.config import get_settings
from src.core.models import JobData, JobStatus
from src.services.pipeline import TranscriptionPipeline
from src.utils.audio import cleanup_temp_files, preprocess_audio
from src.utils.formatters import format_json
from src.utils.logging import bind_job_context, clear_job_context
from src.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)


def get_redis_client() -> redis.Redis:
    """Get Redis client instance."""
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


def get_job(job_id: str) -> JobData | None:
    """Retrieve job data from Redis."""
    client = get_redis_client()
    data = client.get(f"job:{job_id}")
    if data:
        return JobData.model_validate_json(data)
    return None


def save_job(job: JobData) -> None:
    """Save job data to Redis."""
    settings = get_settings()
    client = get_redis_client()
    client.setex(
        f"job:{job.job_id}",
        settings.result_ttl_seconds,
        job.model_dump_json(),
    )


def update_job_progress(job_id: str, progress: float, message: str | None = None) -> None:
    """Update job progress."""
    job = get_job(job_id)
    if job:
        job.progress = progress
        if message:
            job.message = message
        save_job(job)


@celery_app.task(bind=True, name="transcription.process")
def process_transcription(self, job_id: str) -> dict:
    """
    Process a transcription job.

    This task:
    1. Retrieves job data from Redis
    2. Preprocesses the audio file
    3. Runs the transcription pipeline
    4. Saves results back to Redis
    """
    bind_job_context(job_id)
    temp_files: list[Path] = []

    try:
        logger.info("Starting transcription task", job_id=job_id)

        # Get job data
        job = get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        if not job.file_path:
            raise ValueError(f"Job {job_id} has no file path")

        # Update status to processing
        job.status = JobStatus.PROCESSING
        job.progress = 0.0
        job.message = "Processing started"
        save_job(job)

        # Preprocess audio
        update_job_progress(job_id, 10.0, "Preprocessing audio")
        audio_path = Path(job.file_path)
        processed_path = preprocess_audio(audio_path)
        temp_files.append(processed_path)

        # Run pipeline
        update_job_progress(job_id, 20.0, "Running diarization and transcription")

        result = TranscriptionPipeline.process(
            audio_path=processed_path,
            language=job.language,
            enable_diarization=job.enable_diarization,
            min_speakers=job.min_speakers,
            max_speakers=job.max_speakers,
            word_timestamps=job.word_timestamps,
        )

        update_job_progress(job_id, 90.0, "Finalizing results")

        # Format result for storage
        result_data = format_json(
            segments=result.segments,
            duration_seconds=result.duration_seconds,
            language=result.language,
            speakers=result.speakers,
        )

        # Update job with results
        job.status = JobStatus.COMPLETED
        job.progress = 100.0
        job.message = "Transcription completed"
        job.completed_at = datetime.utcnow()
        job.result = result_data
        save_job(job)

        logger.info(
            "Transcription task completed",
            job_id=job_id,
            duration_seconds=result.duration_seconds,
            speaker_count=len(result.speakers),
            segment_count=len(result.segments),
        )

        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        logger.error("Transcription task failed", job_id=job_id, error=str(e))

        # Update job with error
        job = get_job(job_id)
        if job:
            job.status = JobStatus.FAILED
            job.error = str(e)
            job.message = "Transcription failed"
            save_job(job)

        # Re-raise for Celery retry mechanism
        raise

    finally:
        # Cleanup temp files
        cleanup_temp_files(temp_files)
        clear_job_context()
