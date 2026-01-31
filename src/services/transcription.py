"""Whisper-based transcription service with lazy model loading."""

import threading
from pathlib import Path

import structlog
import torch
import whisper

from src.core.config import get_settings
from src.core.models import Word

logger = structlog.get_logger(__name__)


class TranscriptionService:
    """Service for audio transcription using OpenAI Whisper."""

    _model: whisper.Whisper | None = None
    _lock = threading.Lock()

    @classmethod
    def get_model(cls) -> whisper.Whisper:
        """Get or load the Whisper model (thread-safe lazy loading)."""
        if cls._model is None:
            with cls._lock:
                # Double-check after acquiring lock
                if cls._model is None:
                    settings = get_settings()
                    device = cls._get_device(settings.whisper_device)
                    logger.info(
                        "Loading Whisper model",
                        model=settings.whisper_model,
                        device=str(device),
                    )
                    cls._model = whisper.load_model(
                        settings.whisper_model,
                        device=device,
                    )
                    logger.info("Whisper model loaded successfully")
        return cls._model

    @classmethod
    def _get_device(cls, configured_device: str | None) -> str:
        """Determine the best available device."""
        if configured_device:
            return configured_device
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    @classmethod
    def is_loaded(cls) -> bool:
        """Check if the model is currently loaded."""
        return cls._model is not None

    @classmethod
    def unload(cls) -> None:
        """Unload the model to free memory."""
        with cls._lock:
            if cls._model is not None:
                del cls._model
                cls._model = None
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                logger.info("Whisper model unloaded")

    @classmethod
    def transcribe(
        cls,
        audio_path: str | Path,
        language: str | None = None,
        word_timestamps: bool = True,
    ) -> dict:
        """
        Transcribe an audio file.

        Args:
            audio_path: Path to the audio file
            language: Language code (e.g., 'en', 'es'). Auto-detect if None.
            word_timestamps: Whether to include word-level timestamps

        Returns:
            Dictionary containing:
                - text: Full transcription text
                - language: Detected or specified language
                - words: List of Word objects with timing (if word_timestamps=True)
                - segments: Raw Whisper segments
        """
        model = cls.get_model()
        audio_path = str(audio_path)

        logger.info("Starting transcription", audio_path=audio_path, language=language)

        # Transcription options
        options = {
            "word_timestamps": word_timestamps,
            "verbose": False,
        }
        if language:
            options["language"] = language

        try:
            result = model.transcribe(audio_path, **options)
        except Exception as e:
            logger.error("Transcription failed", error=str(e), audio_path=audio_path)
            raise

        # Extract words with timestamps
        words: list[Word] = []
        if word_timestamps and "segments" in result:
            for segment in result["segments"]:
                for word_data in segment.get("words", []):
                    words.append(
                        Word(
                            text=word_data["word"].strip(),
                            start=word_data["start"],
                            end=word_data["end"],
                            confidence=word_data.get("probability"),
                        )
                    )

        logger.info(
            "Transcription completed",
            audio_path=audio_path,
            language=result.get("language"),
            word_count=len(words),
            segment_count=len(result.get("segments", [])),
        )

        return {
            "text": result["text"],
            "language": result.get("language"),
            "words": words,
            "segments": result.get("segments", []),
        }


def transcribe_audio(
    audio_path: str | Path,
    language: str | None = None,
    word_timestamps: bool = True,
) -> dict:
    """Convenience function for transcription."""
    return TranscriptionService.transcribe(
        audio_path=audio_path,
        language=language,
        word_timestamps=word_timestamps,
    )
