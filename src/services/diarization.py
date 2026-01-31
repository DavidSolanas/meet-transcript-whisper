"""Speaker diarization service using pyannote.audio with lazy model loading."""

import threading
from pathlib import Path

import structlog
import torch
from pyannote.audio import Pipeline

from src.core.config import get_settings
from src.core.models import SpeakerSegment

logger = structlog.get_logger(__name__)


class DiarizationService:
    """Service for speaker diarization using pyannote.audio."""

    _pipeline: Pipeline | None = None
    _lock = threading.Lock()

    @classmethod
    def get_pipeline(cls) -> Pipeline:
        """Get or load the diarization pipeline (thread-safe lazy loading)."""
        if cls._pipeline is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._pipeline is None:
                    settings = get_settings()
                    device = cls._get_device()

                    logger.info(
                        "Loading diarization pipeline",
                        model=settings.diarization_model,
                        device=str(device),
                    )

                    cls._pipeline = Pipeline.from_pretrained(
                        settings.diarization_model,
                        use_auth_token=settings.huggingface_access_token,
                    )
                    cls._pipeline.to(device)

                    logger.info("Diarization pipeline loaded successfully")
        return cls._pipeline

    @classmethod
    def _get_device(cls) -> torch.device:
        """Determine the best available device."""
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if the pipeline is currently loaded."""
        return cls._pipeline is not None

    @classmethod
    def unload(cls) -> None:
        """Unload the pipeline to free memory."""
        with cls._lock:
            if cls._pipeline is not None:
                del cls._pipeline
                cls._pipeline = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("Diarization pipeline unloaded")

    @classmethod
    def diarize(
        cls,
        audio_path: str | Path,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> list[SpeakerSegment]:
        """
        Perform speaker diarization on an audio file.

        Args:
            audio_path: Path to the audio file
            min_speakers: Minimum number of speakers (optional hint)
            max_speakers: Maximum number of speakers (optional hint)

        Returns:
            List of SpeakerSegment objects with speaker labels and timestamps
        """
        pipeline = cls.get_pipeline()
        audio_path = str(audio_path)

        logger.info(
            "Starting diarization",
            audio_path=audio_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )

        # Build pipeline parameters
        params = {}
        if min_speakers is not None:
            params["min_speakers"] = min_speakers
        if max_speakers is not None:
            params["max_speakers"] = max_speakers

        try:
            diarization = pipeline(audio_path, **params)
        except Exception as e:
            logger.error("Diarization failed", error=str(e), audio_path=audio_path)
            raise

        # Convert to SpeakerSegment objects
        segments: list[SpeakerSegment] = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append(
                SpeakerSegment(
                    speaker=speaker,
                    start=turn.start,
                    end=turn.end,
                )
            )

        # Sort by start time
        segments.sort(key=lambda s: s.start)

        # Get unique speakers
        unique_speakers = sorted(set(s.speaker for s in segments))

        logger.info(
            "Diarization completed",
            audio_path=audio_path,
            segment_count=len(segments),
            speaker_count=len(unique_speakers),
            speakers=unique_speakers,
        )

        return segments


def diarize_audio(
    audio_path: str | Path,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list[SpeakerSegment]:
    """Convenience function for diarization."""
    return DiarizationService.diarize(
        audio_path=audio_path,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )
