"""Celery application configuration."""

from celery import Celery

from src.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "meet-transcriber",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.worker.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time (heavy tasks)
    # Result backend settings
    result_expires=settings.result_ttl_seconds,
    # Task time limits
    task_soft_time_limit=3600,  # 1 hour soft limit
    task_time_limit=3900,  # 1 hour 5 min hard limit
    # Retry settings
    task_default_retry_delay=60,  # 1 minute
    task_max_retries=3,
)
