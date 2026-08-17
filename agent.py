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

from database import SessionLocal
from tools import (
    answer_faq,
    check_available_slots,
    check_peptide_stock,
    make_book_appointment,
    make_cancel_appointment,
    make_get_appointments,
)

load_dotenv()


SYSTEM_PROMPT = """\
You are Alex, the friendly AI voice specialist for Peptide Wellness Clinic.
Speak naturally and conversationally — this is a phone call, not a text chat.

Your responsibilities:
1. Greet callers warmly and ask how you can help.
2. Help callers find peptides in stock that match their health goals using the check_peptide_stock tool.
3. Answer clinic questions using the answer_faq tool.
4. Book appointments using check_available_slots and book_appointment tools.
5. Cancel appointments using cancel_appointment if the caller requests it.
6. List the caller's appointments using get_appointments.
7. Keep responses concise — callers are listening, not reading.

Appointment booking guidelines:
- Appointment types: initial_consultation ($150, 60 min), follow_up ($75, 30 min), peptide_review ($75, 30 min), lab_review ($100, 45 min).
- New callers should book an initial_consultation. Returning callers use follow_up, peptide_review, or lab_review.
- Always check availability with check_available_slots before booking.
- Collect the caller's full name and phone number before calling book_appointment.
- Read back the confirmed date, time, and booking ID to the caller.
- Mention the 24-hour cancellation policy after booking.

General guidelines:
- When someone describes a health goal or symptom, use check_peptide_stock to find matching options.
- Describe peptides in plain language — avoid jargon unless the caller seems knowledgeable.
- Always mention price and quantity so callers know what's available.
- If a peptide is out of stock or we don't carry it, say so honestly and suggest an alternative if possible.
- If you cannot help, offer to have a human call them back.
- Never make up information not provided by your tools.
"""


class ReceptionistAgent(Agent):
    def __init__(self, user_id: str, db) -> None:
        super().__init__(
            instructions=SYSTEM_PROMPT,
            tools=[
                check_peptide_stock,
                answer_faq,
                check_available_slots,
                make_book_appointment(user_id, db),
                make_cancel_appointment(user_id, db),
                make_get_appointments(user_id, db),
            ],
        )


async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    user_id = participant.identity  # UUID set by FastAPI when issuing LiveKit token

    db = SessionLocal()

    session = AgentSession(
        stt=openai.STT(),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=openai.TTS(voice="alloy"),
        vad=silero.VAD.load(min_silence_duration=0.3),
    )

    await session.start(
        room=ctx.room,
        agent=ReceptionistAgent(user_id=user_id, db=db),
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
