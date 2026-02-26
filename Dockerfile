# syntax=docker/dockerfile:1.5
FROM python:3.11-slim-bookworm

# Install system dependencies
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y \
    pulseaudio \
    socat \
    alsa-utils \
    chromium \
    libasound2-dev \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 botuser

# Unbuffered logs for easier debugging
ENV PYTHONUNBUFFERED=1

# Install uv
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install uv

# Install Python dependencies
COPY requirements.lock .
ENV UV_CACHE_DIR=/root/.cache/uv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system -r requirements.lock

# Skip Playwright browser downloads and use system Chromium
ENV PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
ENV CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Copy application code
COPY bot.py .
COPY entrypoint.sh .

# Make entrypoint executable and change ownership
RUN chmod +x entrypoint.sh && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Set entrypoint
ENTRYPOINT ["./entrypoint.sh"]
