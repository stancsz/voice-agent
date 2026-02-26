import os
import sys
import asyncio
import pyaudio
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask
from pipecat.frames.frames import LLMMessagesFrame, EndFrame
from pipecat.services.openai import OpenAIRealtimeLLMService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams

# Load environment variables
load_dotenv()

MEETING_URL = os.getenv("MEETING_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AGENT_NAME = os.getenv("AGENT_NAME", "AI Assistant")
AGENT_IMAGE = os.getenv("AGENT_IMAGE")
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT")

# Voice Activity Detection (VAD) parameters
VAD_START_SECS = float(os.getenv("VAD_START_SECS", "0.2"))
VAD_STOP_SECS = float(os.getenv("VAD_STOP_SECS", "0.2"))
VAD_CONFIDENCE = float(os.getenv("VAD_CONFIDENCE", "0.7"))

# Pipeline configuration
ALLOW_INTERRUPTIONS = os.getenv("ALLOW_INTERRUPTIONS", "true").lower() == "true"

if not MEETING_URL:
    print("Warning: MEETING_URL is not set.")
if not OPENAI_API_KEY:
    print("Warning: OPENAI_API_KEY is not set.")

def find_audio_devices():
    """Finds the indices of the virtual audio devices."""
    p = pyaudio.PyAudio()
    browser_input_index = None
    bot_output_index = None

    print("Available Audio Devices:")
    count = p.get_device_count()
    for i in range(count):
        try:
            dev = p.get_device_info_by_index(i)
            name = dev.get('name')
            print(f"{i}: {name}")

            # Browser output goes to 'BrowserOutput' sink. We want the monitor of that sink.
            if name and "BrowserOutput.monitor" in name:
                browser_input_index = i

            # Bot output goes to 'BotOutput' sink. We want to write to it.
            if name and "BotOutput" in name and dev.get('maxOutputChannels') > 0:
                bot_output_index = i
        except Exception as e:
            print(f"Error checking device {i}: {e}")

    p.terminate()
    return browser_input_index, bot_output_index

async def join_meeting(playwright, url):
    """Joins a Google Meet meeting."""
    print(f"Joining meeting: {url}")
    browser = await playwright.chromium.launch(
        args=[
            "--use-fake-ui-for-media-stream",
            "--headless=new",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized"
        ]
    )
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        permissions=["microphone", "camera"],
        viewport={"width": 1280, "height": 720}
    )
    page = await context.new_page()

    try:
        await page.goto(url)

        # Handle "Got it" popup
        try:
            got_it = page.get_by_text("Got it")
            if await got_it.is_visible(timeout=5000):
                await got_it.click()
        except:
            pass

        # Handle name input
        try:
            name_input = page.get_by_placeholder("Your name")
            if await name_input.is_visible(timeout=5000):
                 await name_input.fill(AGENT_NAME)
        except:
            pass

        if AGENT_IMAGE:
             print(f"Note: AGENT_IMAGE is set to {AGENT_IMAGE}, but guest join typically doesn't support setting a profile picture.")

        # Click join button
        join_clicked = False
        # Wait for any of the join buttons to appear
        try:
            # We look for any of these buttons. We'll wait up to 10 seconds.
            # Using a locator that matches any of the text options.
            join_btn_locator = page.get_by_role("button", name="Ask to join").or_(
                page.get_by_role("button", name="Join now")
            ).or_(
                page.get_by_role("button", name="Join")
            )

            await join_btn_locator.first.wait_for(state="visible", timeout=10000)

            # Click the one that is visible
            if await page.get_by_role("button", name="Ask to join").is_visible():
                print("Clicking 'Ask to join'...")
                await page.get_by_role("button", name="Ask to join").click()
                join_clicked = True
            elif await page.get_by_role("button", name="Join now").is_visible():
                print("Clicking 'Join now'...")
                await page.get_by_role("button", name="Join now").click()
                join_clicked = True
            elif await page.get_by_role("button", name="Join").is_visible():
                print("Clicking 'Join'...")
                await page.get_by_role("button", name="Join").click()
                join_clicked = True

        except Exception as e:
            print(f"Timeout waiting for join button: {e}")

        if not join_clicked:
             print("Could not find or click join button. Aborting.")
             await browser.close()
             return None, None

        return browser, page

    except Exception as e:
        print(f"Error joining meeting: {e}")
        await browser.close()
        return None, None

async def main():
    if not MEETING_URL or not OPENAI_API_KEY:
        print("Please set MEETING_URL and OPENAI_API_KEY.")
        return

    # 1. Setup Audio
    browser_input_index, bot_output_index = find_audio_devices()

    if browser_input_index is None:
        print("Warning: BrowserOutput.monitor not found. Using default input device.")

    if bot_output_index is None:
        print("Warning: BotOutput not found. Using default output device.")

    transport = LocalAudioTransport(
        LocalAudioTransportParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            camera_out_enabled=False,
            vad_enabled=True,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    start_secs=VAD_START_SECS,
                    stop_secs=VAD_STOP_SECS,
                    confidence=VAD_CONFIDENCE
                )
            ),
            vad_audio_passthrough=True,
            # If indices are None, PyAudio uses default
            audio_in_index=browser_input_index,
            audio_out_index=bot_output_index
        )
    )

    # 2. Setup LLM Service
    llm = OpenAIRealtimeLLMService(
        api_key=OPENAI_API_KEY,
        model="gpt-realtime-mini",
        start_audio_paused=False
    )

    if SYSTEM_PROMPT:
        messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT
            }
        ]
    else:
        messages = [
            {
                "role": "system",
                "content": f"You are a helpful AI assistant named {AGENT_NAME} in a Google Meet meeting. Listen to the conversation and participate when addressed or when you have relevant information. Keep your responses concise."
            }
        ]

    # 3. Setup Pipeline
    # Input -> LLM -> Output
    pipeline = Pipeline(
        [
            transport.input(),   # Microphone input (Browser Output)
            llm,                 # OpenAI Realtime API
            transport.output()   # Speaker output (Bot Output -> Browser Input)
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineTask.Params(
            allow_interruptions=ALLOW_INTERRUPTIONS,
            enable_metrics=True
        )
    )

    runner = PipelineRunner()

    # 4. Join Meeting
    async with async_playwright() as p:
        browser, page = await join_meeting(p, MEETING_URL)
        if not browser:
            print("Failed to join meeting. Exiting.")
            return

        print("Starting voice agent...")

        try:
            await task.queue_frame(LLMMessagesFrame(messages))
            await runner.run(task)
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
