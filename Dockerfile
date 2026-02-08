# Multi-stage build for Meeting Transcription API
# Using NVIDIA CUDA base for GPU support

# Stage 1: Build stage (using Ubuntu to match Runtime stage)
FROM nvidia/cuda:12.1.0-devel-ubuntu22.04 AS builder
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

WORKDIR /app

# Install Python 3.12 and build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common build-essential git \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3.12-venv python3.12-dev python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml ./

# Create virtual environment and install dependencies
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -e .

# Stage 2: Runtime stage
FROM nvidia/cuda:12.1.0-runtime-ubuntu22.04 AS runtime
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Etc/UTC

# Install Python 3.12 and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    ffmpeg \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

WORKDIR /app

# Copy virtual environment from builder 
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code [cite: 3]
COPY src/ ./src/
COPY pyproject.toml ./

# Create non-root user [cite: 3]
RUN useradd -m -u 1000 appuser && \
    mkdir -p /tmp/meet-transcriber && \
    chown -R appuser:appuser /app /tmp/meet-transcriber

USER appuser

# Environment variables [cite: 3]
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Expose API port [cite: 3]
EXPOSE 8000

# Default command [cite: 3]
CMD ["python", "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]