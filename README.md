# Google Meet Voice Agent

This project is a containerized voice agent that can join Google Meet meetings, listen to the conversation, and interact with participants using OpenAI's Realtime API.

## Features

- **Automated Joining**: Uses Playwright to navigate Google Meet and join meetings automatically.
- **Audio Loopback**: Configures PulseAudio inside a Docker container to route audio between the browser and the bot.
- **Real-time Voice**: Utilizes `pipecat-ai` and OpenAI Realtime API for low-latency speech-to-speech interaction.
- **Headless Operation**: Runs entirely within a Docker container, suitable for server deployments.

## Prerequisites

- Docker and Docker Compose installed on your machine.
- An OpenAI API Key with access to the Realtime API.

## Configuration

The bot is configured via environment variables. You can set these in `docker-compose.yml` or a `.env` file.

- `OPENAI_API_KEY`: Your OpenAI API key.
- `MEETING_URL`: The full URL of the Google Meet meeting (e.g., `https://meet.google.com/abc-defg-hij`).

## Usage

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd <repository-directory>
   ```

2. **Set your environment variables:**

   Create a `.env` file or export the variables:
   ```bash
   export OPENAI_API_KEY="sk-..."
   export MEETING_URL="https://meet.google.com/..."
   ```

3. **Build and Run with Docker Compose:**
   ```bash
   docker-compose up --build
   ```

   The container will:
   - Start PulseAudio.
   - Launch a headless Chromium browser.
   - Join the specified Google Meet.
   - Listen for speech and respond when addressed.

## Troubleshooting

- **Audio Issues**: If the bot cannot hear or speak, ensure the Docker container has access to the host network (`network_mode: host`) or that PulseAudio is correctly configured. The current setup uses internal virtual sinks, so it doesn't require host audio devices.
- **Join Failures**: If the bot gets stuck on the "Ask to join" screen, manual intervention might be needed if the meeting requires host approval. The bot attempts to click "Ask to join" or "Join now".
- **Permissions**: The browser is launched with flags to fake media stream permissions (`--use-fake-ui-for-media-stream`), so it shouldn't ask for microphone/camera access.

## Architecture

- **Dockerfile**: Sets up a Python environment with PulseAudio and Playwright.
- **bot.py**: The main Python script that handles browser automation and the Pipecat pipeline.
- **entrypoint.sh**: A shell script that initializes PulseAudio virtual sinks before starting the bot.
