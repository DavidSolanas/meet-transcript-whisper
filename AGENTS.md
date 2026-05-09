# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Meeting Transcription API — Python 3.12 FastAPI app using Whisper (ASR), pyannote.audio (diarization), Celery+Redis (task queue). See `README.md` for full architecture.

### Running services

Three services are needed for full end-to-end operation:

| Service | Command | Notes |
|---------|---------|-------|
| Redis | `redis-server --daemonize yes` | Must be running before API/worker start |
| FastAPI API | `uv run uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload` | Serves REST API + web UI at `/` |
| Celery Worker | `uv run celery -A src.worker.celery_app worker --loglevel=INFO` | Requires `HUGGINGFACE_ACCESS_TOKEN` for diarization |

The API and web UI work without the Celery worker (jobs stay in "pending"). The worker requires a valid HuggingFace token and accepted pyannote model terms.

### Lint / Test / Build

- **Lint:** `uv run ruff check .` (2 existing UP042 warnings in `src/core/models.py` — not blockers)
- **Format check:** `uv run ruff format --check .`
- **Tests:** `uv run pytest` (29 tests, all pass; tests mock Redis and ML models)
- **Build:** No separate build step; this is a pure Python application

### Environment setup notes

- A `.env` file must exist (copy from `.env.example`). The `HUGGINGFACE_ACCESS_TOKEN` is required by pydantic-settings validation but tests set it via `os.environ` in `conftest.py`.
- Redis must be running on `localhost:6379` (default). Start with `redis-server --daemonize yes`.
- FFmpeg must be installed (`sudo apt-get install -y ffmpeg`) — needed by pydub for audio processing.
- The virtual environment is at `.venv/` managed by `uv`. Use `uv run <cmd>` or activate with `source .venv/bin/activate`.
- ML model downloads (Whisper, pyannote) happen lazily on first request, not at startup (unless `PRELOAD_MODELS=true`).
