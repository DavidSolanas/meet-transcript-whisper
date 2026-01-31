"""Pytest fixtures for testing the Meeting Transcription API."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["HUGGINGFACE_ACCESS_TOKEN"] = "test_token"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use a separate DB for tests


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing without a real Redis connection."""
    mock_client = MagicMock()
    mock_client.ping.return_value = True
    mock_client.get.return_value = None
    mock_client.setex.return_value = True

    with patch("src.worker.tasks.get_redis_client", return_value=mock_client):
        with patch("src.api.routes.get_redis_client", return_value=mock_client):
            yield mock_client


@pytest.fixture
def mock_celery():
    """Mock Celery task to prevent actual task execution."""
    with patch("src.api.routes.process_transcription") as mock_task:
        mock_task.delay.return_value = MagicMock(id="test-task-id")
        yield mock_task


@pytest.fixture
def client(mock_redis, mock_celery):
    """FastAPI test client with mocked dependencies."""
    from src.api.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_audio_path():
    """Create a minimal valid WAV file for testing."""
    import wave

    # Create a temporary WAV file
    temp_dir = Path(tempfile.mkdtemp())
    audio_path = temp_dir / "test_audio.wav"

    # Create a minimal valid WAV file (1 second of silence)
    with wave.open(str(audio_path), "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        # 1 second of silence (16000 samples at 16kHz)
        wav_file.writeframes(b"\x00\x00" * 16000)

    yield audio_path

    # Cleanup
    audio_path.unlink(missing_ok=True)
    temp_dir.rmdir()


@pytest.fixture
def mock_transcription_service():
    """Mock TranscriptionService for testing without loading models."""
    with patch("src.services.transcription.TranscriptionService") as mock_service:
        mock_service.is_loaded.return_value = False
        mock_service.transcribe.return_value = {
            "text": "Hello, this is a test transcription.",
            "language": "en",
            "words": [
                {"text": "Hello,", "start": 0.0, "end": 0.5, "confidence": 0.95},
                {"text": "this", "start": 0.5, "end": 0.7, "confidence": 0.98},
                {"text": "is", "start": 0.7, "end": 0.8, "confidence": 0.99},
                {"text": "a", "start": 0.8, "end": 0.9, "confidence": 0.97},
                {"text": "test", "start": 0.9, "end": 1.2, "confidence": 0.96},
                {"text": "transcription.", "start": 1.2, "end": 1.8, "confidence": 0.94},
            ],
            "segments": [],
        }
        yield mock_service


@pytest.fixture
def mock_diarization_service():
    """Mock DiarizationService for testing without loading models."""
    with patch("src.services.diarization.DiarizationService") as mock_service:
        mock_service.is_loaded.return_value = False
        mock_service.diarize.return_value = [
            MagicMock(speaker="SPEAKER_00", start=0.0, end=1.0),
            MagicMock(speaker="SPEAKER_01", start=1.0, end=2.0),
        ]
        yield mock_service
