import os
import sys
import asyncio
import re
import pyaudio
from dotenv import load_dotenv
from playwright.async_api import async_playwright

from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.frames.frames import LLMMessagesUpdateFrame, EndFrame
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
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
ANNOUNCE_ON_JOIN = os.getenv("ANNOUNCE_ON_JOIN", "false").lower() == "true"

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
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    chromium_executable = os.getenv("CHROMIUM_EXECUTABLE_PATH")
    browser = await playwright.chromium.launch(
        executable_path=chromium_executable,
        env={
            **os.environ,
            # Route Chrome audio to the virtual devices for the meeting
            "PULSE_SINK": "BrowserOutput",
            "PULSE_SOURCE": "BotOutput.monitor",
        },
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
        await page.wait_for_load_state("domcontentloaded")

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

        # Click join button (poll and wait for host admit flow)
        join_clicked = False
        try:
            join_regex = re.compile(r"(ask to join|join now|join meeting|join|request to join)", re.IGNORECASE)
            poll_deadline_secs = float(os.getenv("JOIN_WAIT_SECS", "180"))
            poll_interval_secs = float(os.getenv("JOIN_POLL_INTERVAL_SECS", "2"))
            start_time = asyncio.get_event_loop().time()

            while (asyncio.get_event_loop().time() - start_time) < poll_deadline_secs:
                buttons = page.get_by_role("button")
                try:
                    await buttons.first.wait_for(state="attached", timeout=5000)
                except Exception:
                    await asyncio.sleep(poll_interval_secs)
                    continue

                count = await buttons.count()
                for i in range(count):
                    btn = buttons.nth(i)
                    try:
                        if not await btn.is_visible():
                            continue
                        name = await btn.text_content() or ""
                        if join_regex.search(name):
                            print(f"Clicking join button: {name.strip()!r}...")
                            await btn.click()
                            join_clicked = True
                            break
                    except Exception:
                        continue

                if join_clicked:
                    break

                await asyncio.sleep(poll_interval_secs)

        except Exception as e:
            print(f"Error while waiting for join button: {e}")

        if not join_clicked:
             # Dump visible button text to aid debugging
             try:
                 print("Current page URL:", page.url)
                 print("Page title:", await page.title())
                 buttons = page.get_by_role("button")
                 count = await buttons.count()
                 texts = []
                 for i in range(count):
                     btn = buttons.nth(i)
                     if await btn.is_visible():
                         texts.append((await btn.text_content() or "").strip())
                 print("Visible buttons:", [t for t in texts if t])
                 await page.screenshot(path="/app/meet_join_failure.png", full_page=True)
                 print("Saved failure screenshot to /app/meet_join_failure.png")
             except Exception as e:
                 print(f"Failed to capture debug info: {e}")
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

    # Route bot audio via PulseAudio virtual devices (separate from Chrome defaults)
    os.environ["PULSE_SOURCE"] = "BrowserOutput.monitor"
    os.environ["PULSE_SINK"] = "BotOutput"

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
        params=PipelineParams(
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
            await task.queue_frame(LLMMessagesUpdateFrame(messages, run_llm=False))
            if ANNOUNCE_ON_JOIN:
                await task.queue_frame(
                    LLMMessagesUpdateFrame(
                        [
                            {"role": "user", "content": "Please introduce yourself briefly to the meeting."}
                        ],
                        run_llm=True,
                    )
                )
            await runner.run(task)
        except KeyboardInterrupt:
            print("Exiting...")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
