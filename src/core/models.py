"""Pydantic models for API requests, responses, and internal data structures."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Status of a transcription job."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OutputFormat(str, Enum):
    """Supported output formats."""

    JSON = "json"
    SRT = "srt"
    VTT = "vtt"


# =============================================================================
# Internal Data Models
# =============================================================================


class Word(BaseModel):
    """A single word with timing information."""

    text: str
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    speaker: str | None = None


class SpeakerSegment(BaseModel):
    """A speaker segment from diarization."""

    speaker: str
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")


class TranscriptSegment(BaseModel):
    """A transcript segment with speaker attribution."""

    speaker: str
    start: float = Field(..., description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str
    words: list[Word] | None = None


# =============================================================================
# API Request/Response Models
# =============================================================================


class TranscriptionRequest(BaseModel):
    """Request parameters for transcription (query params)."""

    language: str | None = Field(
        None, description="Language code (e.g., 'en', 'es'). Auto-detect if not specified."
    )
    min_speakers: int | None = Field(None, ge=1, le=20, description="Minimum number of speakers")
    max_speakers: int | None = Field(None, ge=1, le=20, description="Maximum number of speakers")
    enable_diarization: bool = Field(True, description="Enable speaker diarization")
    word_timestamps: bool = Field(True, description="Include word-level timestamps")


class JobCreatedResponse(BaseModel):
    """Response when a transcription job is created."""

    job_id: str
    status: JobStatus = JobStatus.PENDING
    message: str = "Transcription job queued"
    created_at: datetime = Field(default_factory=datetime.utcnow)


class JobStatusResponse(BaseModel):
    """Response for job status check."""

    job_id: str
    status: JobStatus
    progress: float | None = Field(None, ge=0.0, le=100.0, description="Progress percentage")
    message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class TranscriptionResult(BaseModel):
    """Complete transcription result."""

    job_id: str
    status: JobStatus = JobStatus.COMPLETED
    duration_seconds: float
    language: str | None = None
    speakers: list[str]
    segments: list[TranscriptSegment]
    created_at: datetime
    completed_at: datetime


class TranscriptionResponse(BaseModel):
    """Full API response combining status and result."""

    job_id: str
    status: JobStatus
    progress: float | None = None
    message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    # Result fields (only present when completed)
    duration_seconds: float | None = None
    language: str | None = None
    speakers: list[str] | None = None
    segments: list[TranscriptSegment] | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str
    models_loaded: dict[str, bool] = Field(default_factory=dict)
    redis_connected: bool = False


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    detail: str | None = None
    job_id: str | None = None


# =============================================================================
# Internal Job Storage Model
# =============================================================================


class JobData(BaseModel):
    """Internal job data stored in Redis."""

    job_id: str
    status: JobStatus
    progress: float = 0.0
    message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    # Request parameters
    language: str | None = None
    min_speakers: int | None = None
    max_speakers: int | None = None
    enable_diarization: bool = True
    word_timestamps: bool = True
    # File info
    filename: str | None = None
    file_path: str | None = None
    # Result
    result: dict[str, Any] | None = None

    def to_status_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            created_at=self.created_at,
            completed_at=self.completed_at,
            error=self.error,
        )

    def to_full_response(self) -> TranscriptionResponse:
        response = TranscriptionResponse(
            job_id=self.job_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            created_at=self.created_at,
            completed_at=self.completed_at,
            error=self.error,
        )
        if self.result and self.status == JobStatus.COMPLETED:
            response.duration_seconds = self.result.get("duration_seconds")
            response.language = self.result.get("language")
            response.speakers = self.result.get("speakers", [])
            response.segments = [
                TranscriptSegment(**seg) for seg in self.result.get("segments", [])
            ]
        return response
