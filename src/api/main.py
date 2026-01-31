"""FastAPI application factory and configuration."""

from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router
from src.core.config import get_settings
from src.services.diarization import DiarizationService
from src.services.transcription import TranscriptionService
from src.utils.logging import setup_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown events."""
    settings = get_settings()

    # Startup
    setup_logging()
    logger.info("Starting Meet Transcriber API", version="0.1.0")

    # Optionally preload models on startup
    if settings.preload_models:
        logger.info("Preloading models...")
        TranscriptionService.get_model()
        DiarizationService.get_pipeline()
        logger.info("Models preloaded")

    yield

    # Shutdown
    logger.info("Shutting down...")
    TranscriptionService.unload()
    DiarizationService.unload()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Meeting Transcription API",
        description="API for transcribing meetings with speaker diarization \
        using Whisper and pyannote.audio",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(router)

    return app


# Create app instance for uvicorn
app = create_app()


def main():
    """Run the application with uvicorn."""
    settings = get_settings()
    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
