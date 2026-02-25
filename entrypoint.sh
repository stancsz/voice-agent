#!/bin/bash
set -e

echo "Starting PulseAudio daemon..."
pulseaudio -D --exit-idle-time=-1

echo "Loading virtual audio sinks..."
# Create a sink for the browser to output audio to.
# The bot will listen to the .monitor of this sink.
pactl load-module module-null-sink sink_name=BrowserOutput sink_properties=device.description="Browser_Output"

# Create a sink for the bot to output audio to.
# The browser will use the .monitor of this sink as its microphone input?
# No, browser uses a source.
# If we want the browser to hear the bot, the bot must write to a sink, and the browser must read from that sink's monitor.
# Or we can create a pipe-source.
# But using a null-sink and its monitor is standard for loopback.
pactl load-module module-null-sink sink_name=BotOutput sink_properties=device.description="Bot_Output"

echo "Configuring default audio devices for Chrome..."
# Set the default sink (speaker) for new applications (Chrome) to be BrowserOutput
pactl set-default-sink BrowserOutput

# Set the default source (microphone) for new applications (Chrome) to be BotOutput.monitor
pactl set-default-source BotOutput.monitor

echo "Starting Bot..."
exec python bot.py
