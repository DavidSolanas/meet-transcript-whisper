"""Celery worker module for async task processing."""

from src.worker.celery_app import celery_app
from src.worker.tasks import process_transcription

__all__ = ["celery_app", "process_transcription"]
