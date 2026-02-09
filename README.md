# Meeting Transcription API

A production-ready REST API for transcribing audio recordings with automatic speaker diarization. Built with FastAPI, OpenAI Whisper, and pyannote.audio.

## Features

- **Automatic Speech Recognition** — Powered by OpenAI Whisper for high-accuracy transcription
- **Speaker Diarization** — Identifies and labels different speakers using pyannote.audio
- **Word-Level Timestamps** — Precise timing for each word in the transcript
- **Multiple Output Formats** — JSON, SRT, and WebVTT support
- **Web UI** — Modern, responsive interface for easy file uploads and transcription viewing
- **Async Processing** — Celery + Redis for handling long-running transcription jobs
- **GPU Acceleration** — CUDA support for faster processing
- **Production Ready** — Docker deployment, structured logging, health checks

## Architecture

```
POST /transcribe → Celery Task Queue → Processing Pipeline
                                              ↓
                        ┌─────────────────────┴─────────────────────┐
                        │                                           │
                   Diarization                               Transcription
                  (pyannote.audio)                            (Whisper)
                        │                                           │
                        └─────────────────────┬─────────────────────┘
                                              ↓
                                         Alignment
                                              ↓
GET /transcribe/{job_id} ← Redis ← JSON/SRT/VTT Output
```

## Quick Start

### Prerequisites

- Python 3.12+
- Redis (for task queue)
- FFmpeg (for audio processing)
- NVIDIA GPU (optional, for acceleration)
- [HuggingFace account](https://huggingface.co/join) with access token

> **Note:** You must accept the pyannote model terms at [huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) before using the API.

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/meet-transcript-whisper.git
   cd meet-transcript-whisper
   ```

2. **Install dependencies**
   ```bash
   # Using uv (recommended)
   uv sync

   # Or using pip
   pip install -e .
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set your HuggingFace token:
   ```env
   HUGGINGFACE_ACCESS_TOKEN=hf_your_token_here
   ```

### Running with Docker (Recommended)

```bash
# Start all services (API, Worker, Redis)
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Running Locally

```bash
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start the API server
uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 3: Start the Celery worker
celery -A src.worker.celery_app worker --loglevel=INFO
```

## Web Interface

The application includes a modern web UI accessible at `http://localhost:8000/` after starting the server.

### Features

- **Drag & Drop Upload** — Simply drag audio files into the browser
- **Real-time Progress** — Watch transcription progress as it processes
- **Speaker Colors** — Each speaker is highlighted with a distinct color
- **Dark/Light Mode** — Toggle between themes based on preference
- **Export Options** — Download transcripts as SRT or VTT subtitles
- **Responsive Design** — Works on desktop, tablet, and mobile devices

### Configuration Options

The UI provides options to:
- Select target language or use auto-detection
- Enable/disable speaker diarization
- Set minimum and maximum expected speakers

## API Reference

### Health Check

```http
GET /health
```

Returns the API health status and model loading state.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "models_loaded": {
    "whisper": false,
    "diarization": false
  },
  "redis_connected": true
}
```

### Submit Transcription Job

```http
POST /transcribe
Content-Type: multipart/form-data
```

**Parameters:**

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `file` | file | Yes | Audio file (WAV, MP3, M4A, FLAC, etc.) |
| `language` | string | No | Language code (e.g., `en`, `es`). Auto-detected if not specified. |
| `min_speakers` | integer | No | Minimum number of speakers (1-20) |
| `max_speakers` | integer | No | Maximum number of speakers (1-20) |
| `enable_diarization` | boolean | No | Enable speaker identification (default: `true`) |
| `word_timestamps` | boolean | No | Include word-level timestamps (default: `true`) |

**Example:**
```bash
curl -X POST "http://localhost:8000/transcribe" \
  -F "file=@meeting.wav" \
  -F "language=en" \
  -F "min_speakers=2" \
  -F "max_speakers=4"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Transcription job queued",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### Get Transcription Status/Results

```http
GET /transcribe/{job_id}
```

**Response (completed):**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "progress": 100.0,
  "created_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:32:15Z",
  "duration_seconds": 125.4,
  "language": "en",
  "speakers": ["SPEAKER_00", "SPEAKER_01"],
  "segments": [
    {
      "speaker": "SPEAKER_00",
      "start": 0.0,
      "end": 3.5,
      "text": "Hello everyone, welcome to today's meeting.",
      "words": [
        {"text": "Hello", "start": 0.0, "end": 0.4, "confidence": 0.98},
        {"text": "everyone,", "start": 0.4, "end": 0.9, "confidence": 0.96}
      ]
    },
    {
      "speaker": "SPEAKER_01",
      "start": 4.0,
      "end": 6.2,
      "text": "Thanks for having me."
    }
  ]
}
```

### Download Transcript

```http
GET /transcribe/{job_id}/download?format={format}
```

**Parameters:**

| Name | Type | Options | Description |
|------|------|---------|-------------|
| `format` | string | `srt`, `vtt` | Output format |

**Example:**
```bash
# Download as SRT
curl "http://localhost:8000/transcribe/{job_id}/download?format=srt" -o transcript.srt

# Download as WebVTT
curl "http://localhost:8000/transcribe/{job_id}/download?format=vtt" -o transcript.vtt
```

## Configuration

All configuration is done via environment variables. See `.env.example` for the complete list.

| Variable | Default | Description |
|----------|---------|-------------|
| `HUGGINGFACE_ACCESS_TOKEN` | *required* | HuggingFace API token for pyannote models |
| `WHISPER_MODEL` | `base` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large`, `large-v3` |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `MAX_AUDIO_DURATION_SECONDS` | `3600` | Maximum audio length (1 hour) |
| `MAX_UPLOAD_SIZE_MB` | `500` | Maximum upload file size |
| `RESULT_TTL_HOURS` | `24` | How long to keep results in Redis |
| `LOG_LEVEL` | `INFO` | Logging level |
| `PRELOAD_MODELS` | `false` | Load models on startup (uses more memory) |

## Project Structure

```
meet-transcript-whisper/
├── src/
│   ├── api/                 # FastAPI application
│   │   ├── main.py          # App factory and lifespan
│   │   └── routes.py        # API endpoints
│   ├── core/                # Core components
│   │   ├── config.py        # Pydantic settings
│   │   └── models.py        # Data models
│   ├── frontend/            # Web UI
│   │   ├── index.html       # Main page
│   │   ├── styles.css       # Styling
│   │   └── app.js           # JavaScript logic
│   ├── services/            # Business logic
│   │   ├── transcription.py # Whisper ASR service
│   │   ├── diarization.py   # Speaker diarization service
│   │   └── pipeline.py      # Processing pipeline
│   ├── utils/               # Utilities
│   │   ├── audio.py         # Audio preprocessing
│   │   ├── formatters.py    # Output formatters
│   │   └── logging.py       # Structured logging
│   └── worker/              # Async processing
│       ├── celery_app.py    # Celery configuration
│       └── tasks.py         # Background tasks
├── tests/                   # Test suite
├── Dockerfile               # Container image
├── docker-compose.yml       # Multi-container setup
└── pyproject.toml           # Project dependencies
```

## Development

### Running Tests

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

# Run specific test file
uv run pytest tests/test_api.py -v
```

### Code Quality

```bash
# Format code
uv run ruff format .

# Lint code
uv run ruff check .

# Run pre-commit hooks
uv run pre-commit run --all-files
```

## Performance Considerations

### Model Selection

| Model | Size | Speed | Accuracy | VRAM Required |
|-------|------|-------|----------|---------------|
| `tiny` | 39M | Fastest | Lower | ~1 GB |
| `base` | 74M | Fast | Good | ~1 GB |
| `small` | 244M | Medium | Better | ~2 GB |
| `medium` | 769M | Slow | High | ~5 GB |
| `large-v3` | 1.5G | Slowest | Best | ~10 GB |

### Resource Requirements

- **CPU Mode:** Works but significantly slower. Recommended for development only.
- **GPU Mode:** NVIDIA GPU with CUDA support recommended for production.
- **Memory:** At least 8GB RAM. 16GB+ recommended when loading both models.

## Supported Audio Formats

- WAV
- MP3
- M4A / MP4
- FLAC
- OGG
- WebM
- WMA
- AAC

## Cloud Deployment

For production deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md), which covers:

- AWS (EC2, ECS, EKS)
- Google Cloud Platform (Compute Engine, Cloud Run, GKE)
- Azure (VMs, Container Instances, AKS)
- Kubernetes manifests
- Monitoring and scaling
- Cost optimization

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

- [OpenAI Whisper](https://github.com/openai/whisper) — Speech recognition model
- [pyannote.audio](https://github.com/pyannote/pyannote-audio) — Speaker diarization
- [FastAPI](https://fastapi.tiangolo.com/) — Web framework
- [Celery](https://docs.celeryq.dev/) — Task queue
