import asyncio

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.plugins import openai, silero

from tools import answer_faq, check_peptide_stock

load_dotenv()


SYSTEM_PROMPT = """\
You are Alex, the friendly AI voice specialist for Peptide Wellness Clinic.
Speak naturally and conversationally — this is a phone call, not a text chat.

Your responsibilities:
1. Greet callers warmly and ask how you can help.
2. Help callers find peptides in stock that match their health goals using the check_peptide_stock tool.
3. Answer clinic questions using the answer_faq tool.
4. Keep responses concise — callers are listening, not reading.

Guidelines:
- When someone describes a health goal or symptom, use check_peptide_stock to find matching options.
- Describe peptides in plain language — avoid jargon unless the caller seems knowledgeable.
- Always mention price and quantity so callers know what's available.
- If a peptide is out of stock or we don't carry it, say so honestly and suggest an alternative if possible.
- If you cannot help, offer to have a human call them back.
- Never make up information not provided by your tools.
"""


class ReceptionistAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT, tools=[check_peptide_stock, answer_faq])


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    await ctx.wait_for_participant()

    session = AgentSession(
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(voice="alloy"),
        vad=silero.VAD.load(min_silence_duration=0.3),
    )

    await session.start(
        room=ctx.room,
        agent=ReceptionistAgent(),
    )

    await asyncio.sleep(1)

    await session.generate_reply(
        instructions=(
            "Greet the caller warmly, introduce yourself as Alex from "
            "Peptide Wellness Clinic, and ask how you can help them today."
        )
    )


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
