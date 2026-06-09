"""LiveKit voice agent (TRD §8) — livekit-agents 1.x API.

Run as a separate process (supervisord; see deploy/supervisord.conf).
The worker subscribes to LiveKit rooms, streams audio to Deepgram,
runs Qwen-Plus via the OpenAI-compatible adapter (DashScope), and
streams TTS back via ElevenLabs Flash. We pre-warm Silero VAD in
`prewarm` so the first turn doesn't pay the model-load latency.

Ported from the legacy 0.x `VoicePipelineAgent` / `ChatContext.append`
API to the 1.x `AgentSession` + `Agent` pattern. See
https://docs.livekit.io/agents/start/voice-ai/ and
https://github.com/livekit/agents/blob/main/examples/voice_agents/basic_agent.py
"""

from __future__ import annotations

import logging
import os

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    WorkerOptions,
    cli,
)
from livekit.plugins import deepgram, elevenlabs, openai, silero

from app.config import get_settings

log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are HealthDesk, a friendly clinic front-desk assistant. "
    "Be concise, warm, and never give medical advice."
)
GREETING_INSTRUCTIONS = (
    "Greet the caller with: "
    "\"Hi — you've reached the front desk. How can I help today?\""
)


class HealthDeskAgent(Agent):
    """Front-desk persona; greeting is fired on session enter."""

    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)

    async def on_enter(self) -> None:
        # session.generate_reply replaces the old `agent.say(...)` —
        # it runs the greeting through the configured LLM+TTS pipeline
        # and respects interruptions by default.
        self.session.generate_reply(instructions=GREETING_INSTRUCTIONS)


def _qwen_llm() -> openai.LLM:
    """Qwen-Plus via DashScope's OpenAI-compatible endpoint.

    The livekit-plugins-openai LLM class accepts `base_url` directly
    (verified in livekit-plugins-openai 1.5.x source), so we can point
    it straight at https://dashscope.aliyuncs.com/compatible-mode/v1
    without needing a dedicated `with_qwen()` classmethod.
    """
    s = get_settings()
    return openai.LLM(
        model=s.qwen_model_plus,
        api_key=s.qwen_api_key,
        base_url=s.qwen_api_base,
        temperature=0.3,
    )


def prewarm(proc: JobProcess) -> None:
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext) -> None:
    s = get_settings()
    if not s.healthdesk_voice:
        log.info("HEALTHDESK_VOICE=false; voice worker exiting without joining room")
        return

    # ctx.connect() still exists in 1.x; AutoSubscribe has been replaced
    # by simply not passing audio_output / configuring room_io. Default
    # connect() is fine for an audio-only voice agent.
    await ctx.connect()

    session = AgentSession(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(api_key=s.deepgram_api_key, model="nova-3"),
        llm=_qwen_llm(),
        tts=elevenlabs.TTS(api_key=s.elevenlabs_api_key, model="eleven_flash_v2_5"),
    )

    await session.start(agent=HealthDeskAgent(), room=ctx.room)
    log.info("voice session started room=%s", ctx.room.name)


if __name__ == "__main__":
    os.environ.setdefault("LIVEKIT_URL", get_settings().livekit_url)
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
