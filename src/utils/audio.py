"""Audio preprocessing and validation utilities."""

import tempfile
from pathlib import Path

import structlog
from pydub import AudioSegment

from src.core.config import get_settings

logger = structlog.get_logger(__name__)

# Supported audio formats
SUPPORTED_FORMATS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".mp4",
    ".flac",
    ".ogg",
    ".webm",
    ".wma",
    ".aac",
}

# Target format for processing
TARGET_SAMPLE_RATE = 16000  # Whisper expects 16kHz
TARGET_CHANNELS = 1  # Mono


class AudioValidationError(Exception):
    """Raised when audio validation fails."""

    pass


def validate_audio_file(file_path: str | Path) -> tuple[bool, str | None]:
    """
    Validate an audio file for processing.

    Args:
        file_path: Path to the audio file

    Returns:
        Tuple of (is_valid, error_message)
    """
    file_path = Path(file_path)
    settings = get_settings()

    # Check file exists
    if not file_path.exists():
        return False, "File does not exist"

    # Check file extension
    if file_path.suffix.lower() not in SUPPORTED_FORMATS:
        return False, f"Unsupported format. Supported: {', '.join(SUPPORTED_FORMATS)}"

    # Check file size
    file_size = file_path.stat().st_size
    if file_size > settings.max_upload_size_bytes:
        return False, f"File too large. Maximum: {settings.max_upload_size_mb}MB"

    # Try to load and check duration
    try:
        audio = AudioSegment.from_file(str(file_path))
        duration_seconds = len(audio) / 1000.0

        if duration_seconds > settings.max_audio_duration_seconds:
            return (
                False,
                f"Audio too long. Maximum: {settings.max_audio_duration_seconds / 3600:.1f} hours",
            )

        if duration_seconds < 0.5:
            return False, "Audio too short. Minimum: 0.5 seconds"

    except Exception as e:
        return False, f"Could not read audio file: {str(e)}"

    return True, None


def get_audio_info(file_path: str | Path) -> dict:
    """
    Get information about an audio file.

    Returns:
        Dictionary with duration, sample_rate, channels, format
    """
    file_path = Path(file_path)
    audio = AudioSegment.from_file(str(file_path))

    return {
        "duration_seconds": len(audio) / 1000.0,
        "sample_rate": audio.frame_rate,
        "channels": audio.channels,
        "format": file_path.suffix.lower().lstrip("."),
        "file_size_bytes": file_path.stat().st_size,
    }


def preprocess_audio(
    file_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    Preprocess audio file for optimal transcription.

    Converts to WAV format with:
    - 16kHz sample rate (Whisper's expected rate)
    - Mono channel
    - 16-bit PCM

    Args:
        file_path: Input audio file path
        output_path: Optional output path. If None, creates a temp file.

    Returns:
        Path to the preprocessed audio file
    """
    file_path = Path(file_path)

    logger.info("Preprocessing audio", input_path=str(file_path))

    # Load audio
    audio = AudioSegment.from_file(str(file_path))

    # Convert to mono if stereo
    if audio.channels > 1:
        audio = audio.set_channels(TARGET_CHANNELS)
        logger.debug("Converted to mono")

    # Resample if needed
    if audio.frame_rate != TARGET_SAMPLE_RATE:
        audio = audio.set_frame_rate(TARGET_SAMPLE_RATE)
        logger.debug("Resampled to 16kHz", original_rate=audio.frame_rate)

    # Determine output path
    if output_path is None:
        # Create temp file that persists
        temp_dir = Path(tempfile.gettempdir()) / "meet-transcriber"
        temp_dir.mkdir(exist_ok=True)
        output_path = temp_dir / f"{file_path.stem}_processed.wav"
    else:
        output_path = Path(output_path)

    # Export as WAV (16-bit PCM)
    audio.export(
        str(output_path),
        format="wav",
        parameters=["-acodec", "pcm_s16le"],
    )

    logger.info(
        "Audio preprocessed",
        input_path=str(file_path),
        output_path=str(output_path),
        duration_seconds=len(audio) / 1000.0,
    )

    return output_path


def cleanup_temp_files(file_paths: list[Path]) -> None:
    """Remove temporary audio files."""
    for path in file_paths:
        try:
            if path.exists():
                path.unlink()
                logger.debug("Removed temp file", path=str(path))
        except Exception as e:
            logger.warning("Failed to remove temp file", path=str(path), error=str(e))
