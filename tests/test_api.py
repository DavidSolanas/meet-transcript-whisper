"""Tests for API endpoints."""

import datetime

from src.core.models import JobData, JobStatus


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check_returns_healthy(self, client):
        """Health check should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"
        assert "models_loaded" in data
        assert "redis_connected" in data

    def test_health_check_shows_model_status(self, client):
        """Health check should show model loading status."""
        response = client.get("/health")
        data = response.json()

        assert "whisper" in data["models_loaded"]
        assert "diarization" in data["models_loaded"]


class TestTranscriptionEndpoints:
    """Tests for transcription endpoints."""

    def test_create_transcription_success(self, client, sample_audio_path):
        """Successfully create a transcription job."""
        with open(sample_audio_path, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"file": ("test.wav", f, "audio/wav")},
            )

        assert response.status_code == 200
        data = response.json()

        assert "job_id" in data
        assert data["status"] == "pending"
        assert data["message"] == "Transcription job queued"

    def test_create_transcription_with_options(self, client, sample_audio_path):
        """Create transcription with custom options."""
        with open(sample_audio_path, "rb") as f:
            response = client.post(
                "/transcribe",
                files={"file": ("test.wav", f, "audio/wav")},
                params={
                    "language": "en",
                    "min_speakers": 2,
                    "max_speakers": 4,
                    "enable_diarization": True,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pending"

    def test_create_transcription_unsupported_format(self, client):
        """Reject unsupported file formats."""
        response = client.post(
            "/transcribe",
            files={"file": ("test.txt", b"not audio", "text/plain")},
        )

        assert response.status_code == 400
        assert "Unsupported file format" in response.json()["detail"]

    def test_get_transcription_not_found(self, client):
        """Return 404 for non-existent job."""
        response = client.get("/transcribe/non-existent-job-id")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_get_transcription_pending(self, client, mock_redis):
        """Get status of pending job."""
        job = JobData(
            job_id="test-job-123",
            status=JobStatus.PENDING,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        mock_redis.get.return_value = job.model_dump_json()

        response = client.get("/transcribe/test-job-123")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == "test-job-123"
        assert data["status"] == "pending"

    def test_get_transcription_completed(self, client, mock_redis):
        """Get completed transcription with results."""
        job = JobData(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            created_at=datetime.datetime.now(datetime.UTC),
            completed_at=datetime.datetime.now(datetime.UTC),
            result={
                "duration_seconds": 10.5,
                "language": "en",
                "speakers": ["SPEAKER_00", "SPEAKER_01"],
                "segments": [
                    {
                        "speaker": "SPEAKER_00",
                        "start": 0.0,
                        "end": 5.0,
                        "text": "Hello, how are you?",
                    }
                ],
            },
        )
        mock_redis.get.return_value = job.model_dump_json()

        response = client.get("/transcribe/test-job-123")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["duration_seconds"] == 10.5
        assert len(data["segments"]) == 1

    def test_download_transcription_srt(self, client, mock_redis):
        """Download transcription as SRT."""
        job = JobData(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            created_at=datetime.datetime.now(datetime.UTC),
            completed_at=datetime.datetime.now(datetime.UTC),
            result={
                "duration_seconds": 10.5,
                "language": "en",
                "speakers": ["SPEAKER_00"],
                "segments": [
                    {
                        "speaker": "SPEAKER_00",
                        "start": 0.0,
                        "end": 5.0,
                        "text": "Hello world",
                    }
                ],
            },
        )
        mock_redis.get.return_value = job.model_dump_json()

        response = client.get("/transcribe/test-job-123/download?format=srt")

        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "[SPEAKER_00] Hello world" in response.text

    def test_download_transcription_vtt(self, client, mock_redis):
        """Download transcription as VTT."""
        job = JobData(
            job_id="test-job-123",
            status=JobStatus.COMPLETED,
            created_at=datetime.datetime.now(datetime.UTC),
            completed_at=datetime.datetime.now(datetime.UTC),
            result={
                "duration_seconds": 10.5,
                "language": "en",
                "speakers": ["SPEAKER_00"],
                "segments": [
                    {
                        "speaker": "SPEAKER_00",
                        "start": 0.0,
                        "end": 5.0,
                        "text": "Hello world",
                    }
                ],
            },
        )
        mock_redis.get.return_value = job.model_dump_json()

        response = client.get("/transcribe/test-job-123/download?format=vtt")

        assert response.status_code == 200
        assert response.text.startswith("WEBVTT")

    def test_download_transcription_not_completed(self, client, mock_redis):
        """Cannot download if job not completed."""
        job = JobData(
            job_id="test-job-123",
            status=JobStatus.PROCESSING,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        mock_redis.get.return_value = job.model_dump_json()

        response = client.get("/transcribe/test-job-123/download?format=srt")

        assert response.status_code == 400
        assert "not completed" in response.json()["detail"]
