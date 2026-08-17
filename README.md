# Peptide Wellness Clinic — AI Voice Receptionist

Python voice AI agent using LiveKit Agents SDK v1.x. Callers join a LiveKit room, speak naturally, and the agent listens, reasons, and replies with synthesised speech.

---

## Files

| File | Purpose |
|---|---|
| `agent.py` | Main entry point. Defines `ReceptionistAgent` (with tools) and the LiveKit job entrypoint. |
| `data.py` | In-memory appointment slots and FAQ store. Swap for a real DB in production. |
| `requirements.txt` | Python dependencies. |
| `.env` | API keys (copy from `.env.example`, never commit). |

## Audio pipeline

```
Microphone → Silero VAD → Whisper STT → GPT-4o (+tools) → OpenAI TTS → Speaker
```

---

## Setup

### 1. Prerequisites

- Python 3.11+
- [LiveKit Cloud](https://cloud.livekit.io) account (free tier works)
- [OpenAI](https://platform.openai.com) account with API access

### 2. Install

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure keys

```bash
cp .env.example .env
# Open .env and fill in all four values
```

### 4. Run the agent

```bash
python agent.py dev
```

`dev` mode connects to your LiveKit server and streams logs to the terminal.
The agent waits for someone to join a room, then starts the session.

---

## Joining a session (as the caller)

### Option A — LiveKit Playground (easiest, browser)

1. Go to [https://cloud.livekit.io](https://cloud.livekit.io) → your project → **Join Room**
2. Enter any room name (e.g. `demo`)
3. Enable microphone → talk to Alex

### Option B — LiveKit CLI

```bash
# Install
brew install livekit-cli        # macOS
# or: go install github.com/livekit/livekit-cli/...@latest

lk room join \
  --url "$LIVEKIT_URL" \
  --api-key "$LIVEKIT_API_KEY" \
  --api-secret "$LIVEKIT_API_SECRET" \
  --room demo \
  --identity caller1
```

---

## Agent capabilities

| What caller says | Tool invoked |
|---|---|
| "What times are available?" | `check_available_appointments()` |
| "Book me Tuesday at 10" | `book_appointment(slot, name)` |
| "What are your hours?" | `answer_faq("hours")` |
| "Do you take insurance?" | `answer_faq("insurance")` |

FAQ topics: `hours` · `location` · `services` · `pricing` · `insurance` · `cancellation` · `new_patient`

---

## Customisation

- **Voice** — change `voice="alloy"` in `agent.py` to `echo`, `fable`, `onyx`, `nova`, or `shimmer`
- **LLM** — swap `gpt-4o` → `gpt-4o-mini` to cut cost during testing
- **Appointments** — replace `data.py` dicts with real DB calls
- **Persona / clinic name** — edit `SYSTEM_PROMPT` in `agent.py`
