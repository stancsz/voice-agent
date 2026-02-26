FROM python:3.10-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    pulseaudio \
    socat \
    alsa-utils \
    libasound2-dev \
    portaudio19-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory
WORKDIR /app

# Create a non-root user
RUN useradd -m -u 1000 botuser

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY bot.py .
COPY entrypoint.sh .

# Make entrypoint executable and change ownership
RUN chmod +x entrypoint.sh && chown -R botuser:botuser /app

# Switch to non-root user
USER botuser

# Set entrypoint
ENTRYPOINT ["./entrypoint.sh"]
