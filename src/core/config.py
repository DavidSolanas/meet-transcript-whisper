"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # HuggingFace (required for pyannote)
    huggingface_access_token: str

    # Whisper settings
    whisper_model: Literal["tiny", "base", "small", "medium", "large", "large-v3"] = "base"
    whisper_device: str | None = None  # Auto-detect if None
    whisper_compute_type: str = "float16"  # float16 for GPU, int8 for CPU

    # Diarization settings
    diarization_model: str = "pyannote/speaker-diarization-3.1"
    min_speakers: int | None = None
    max_speakers: int | None = None

    # Redis settings
    redis_url: str = "redis://localhost:6379/0"

    # Processing limits
    max_audio_duration_seconds: int = 3600  # 1 hour
    max_upload_size_mb: int = 500
    result_ttl_hours: int = 24

    # API settings
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False

    # Feature flags
    preload_models: bool = False  # Load models on startup vs lazy loading

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def result_ttl_seconds(self) -> int:
        return self.result_ttl_hours * 3600


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
