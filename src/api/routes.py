"""API routes for transcription endpoints."""

import datetime
import tempfile
import uuid
from pathlib import Path

import redis
import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse

from src.core.config import get_settings
from src.core.models import (
    ErrorResponse,
    HealthResponse,
    JobCreatedResponse,
    JobData,
    JobStatus,
    OutputFormat,
    TranscriptionResponse,
)
from src.services.diarization import DiarizationService
from src.services.transcription import TranscriptionService
from src.utils.audio import SUPPORTED_FORMATS, validate_audio_file
from src.utils.formatters import format_srt, format_vtt
from src.worker.tasks import get_job, process_transcription, save_job

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_redis_client() -> redis.Redis:
    """Get Redis client for health checks."""
    settings = get_settings()
    return redis.from_url(settings.redis_url, decode_responses=True)


# =============================================================================
# Health Check
# =============================================================================


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check API health and model status."""
    redis_connected = False
    try:
        client = get_redis_client()
        client.ping()
        redis_connected = True
    except Exception:
        pass

    return HealthResponse(
        status="healthy",
        version="0.1.0",
        models_loaded={
            "whisper": TranscriptionService.is_loaded(),
            "diarization": DiarizationService.is_loaded(),
        },
        redis_connected=redis_connected,
    )


# =============================================================================
# Transcription Endpoints
# =============================================================================


@router.post(
    "/transcribe",
    response_model=JobCreatedResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
    tags=["Transcription"],
)
async def create_transcription(
    file: UploadFile = File(..., description="Audio file to transcribe"),
    language: str | None = Query(None, description="Language code (e.g., 'en', 'es')"),
    min_speakers: int | None = Query(None, ge=1, le=20, description="Minimum speakers"),
    max_speakers: int | None = Query(None, ge=1, le=20, description="Maximum speakers"),
    enable_diarization: bool = Query(True, description="Enable speaker diarization"),
    word_timestamps: bool = Query(True, description="Include word timestamps"),
):
    """
    Submit an audio file for transcription.

    Returns a job ID that can be used to check status and retrieve results.
    """
    settings = get_settings()

    # Validate file extension
    if file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format. Supported: {', '.join(SUPPORTED_FORMATS)}",
            )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Save uploaded file
    upload_dir = Path(tempfile.gettempdir()) / "meet-transcriber" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_ext = Path(file.filename).suffix if file.filename else ".wav"
    file_path = upload_dir / f"{job_id}{file_ext}"

    try:
        # Read and save file with size check
        content = await file.read()
        if len(content) > settings.max_upload_size_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum: {settings.max_upload_size_mb}MB",
            )

        file_path.write_bytes(content)

        # Validate audio file
        is_valid, error = validate_audio_file(file_path)
        if not is_valid:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=error)

    except HTTPException:
        raise
    except Exception as e:
        file_path.unlink(missing_ok=True)
        logger.error("Failed to save uploaded file", error=str(e))
        raise HTTPException(status_code=500, detail="Failed to process upload")

    # Create job record
    job = JobData(
        job_id=job_id,
        status=JobStatus.PENDING,
        created_at=datetime.datetime.now(datetime.UTC),
        language=language,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        enable_diarization=enable_diarization,
        word_timestamps=word_timestamps,
        filename=file.filename,
        file_path=str(file_path),
    )
    save_job(job)

    # Queue the task
    process_transcription.delay(job_id)

    logger.info(
        "Transcription job created",
        job_id=job_id,
        filename=file.filename,
        enable_diarization=enable_diarization,
    )

    return JobCreatedResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message="Transcription job queued",
        created_at=job.created_at,
    )


@router.get(
    "/transcribe/{job_id}",
    response_model=TranscriptionResponse,
    responses={404: {"model": ErrorResponse}},
    tags=["Transcription"],
)
async def get_transcription(job_id: str):
    """
    Get the status and results of a transcription job.

    Returns job status and, if completed, the full transcription with speaker labels.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return job.to_full_response()


@router.get(
    "/transcribe/{job_id}/download",
    responses={
        200: {"content": {"text/plain": {}}},
        404: {"model": ErrorResponse},
        400: {"model": ErrorResponse},
    },
    tags=["Transcription"],
)
async def download_transcription(
    job_id: str,
    format: OutputFormat = Query(OutputFormat.SRT, description="Output format"),
):
    """
    Download transcription in SRT or VTT format.

    Only available for completed jobs.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=400,
            detail=f"Job not completed. Current status: {job.status.value}",
        )

    if not job.result or "segments" not in job.result:
        raise HTTPException(status_code=400, detail="No transcription results available")

    # Convert result segments to TranscriptSegment objects for formatting
    from src.core.models import TranscriptSegment, Word

    segments = []
    for seg_data in job.result["segments"]:
        words = None
        if seg_data.get("words"):
            words = [Word(**w) for w in seg_data["words"]]
        segments.append(
            TranscriptSegment(
                speaker=seg_data["speaker"],
                start=seg_data["start"],
                end=seg_data["end"],
                text=seg_data["text"],
                words=words,
            )
        )

    # Format output
    if format == OutputFormat.SRT:
        content = format_srt(segments)
        media_type = "text/plain"
        filename = f"{job_id}.srt"
    elif format == OutputFormat.VTT:
        content = format_vtt(segments)
        media_type = "text/vtt"
        filename = f"{job_id}.vtt"
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
