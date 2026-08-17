"""
load_test.py — Simulate 100 concurrent voice agent sessions with realistic bottlenecks.

Bottlenecks modeled:
  - OpenAI API concurrency limits (semaphores per service)
  - OpenAI rate limit (500 RPM sliding window) → 429 + exponential backoff
  - Silero VAD CPU contention (serialized across 4 cores)
  - Queue wait time tracked separately from API call time

Metrics: stt, llm, tts, vad per stage × (queue_wait + api_time) + e2e + retries.

Usage:
    python load_test.py
    python load_test.py --users 100 --turns 3
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import data as agent_data


# ---------------------------------------------------------------------------
# Latency distributions (milliseconds) — OpenAI API P50 benchmarks
# ---------------------------------------------------------------------------
STT_MU,           STT_SIGMA           = 280,  80
LLM_NO_TOOL_MU,   LLM_NO_TOOL_SIGMA   = 700, 180
LLM_TOOL_EXTRA_MU, LLM_TOOL_EXTRA_SIGMA = 400, 120
TTS_MU,           TTS_SIGMA           = 380,  90
VAD_MU,           VAD_SIGMA           = 60,   20   # Silero inference on CPU

BASE_ERROR_RATE = 0.01   # 1% random API 500/timeout, separate from 429s


def sample_latency(mu: float, sigma: float) -> float:
    return max(random.gauss(mu, sigma), 20.0)


# ---------------------------------------------------------------------------
# Concurrency limits — model real OpenAI Tier 1 constraints
#
#   GPT-4o-mini:  500 RPM → at ~1s/call  → ~8 concurrent
#   Whisper STT:  500 RPM → at ~0.3s/call → ~15 concurrent
#   OpenAI TTS:   500 RPM → at ~0.4s/call → ~12 concurrent
#   Silero VAD:   CPU-bound, 4 logical cores
# ---------------------------------------------------------------------------
_llm_sem = asyncio.Semaphore(8)
_stt_sem = asyncio.Semaphore(15)
_tts_sem = asyncio.Semaphore(12)
_vad_sem = asyncio.Semaphore(4)


# ---------------------------------------------------------------------------
# Sliding-window rate limiter (per-service)
# ---------------------------------------------------------------------------
class RateLimiter:
    """Enforces a requests-per-minute cap with exponential backoff on breach."""

    def __init__(self, rpm: int):
        self.rpm = rpm
        self._times: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> float:
        """Block until under limit. Returns total backoff added (ms)."""
        backoff_total_ms = 0.0
        for attempt in range(4):
            async with self._lock:
                now = time.perf_counter()
                self._times = [t for t in self._times if now - t < 60.0]
                if len(self._times) < self.rpm:
                    self._times.append(now)
                    return backoff_total_ms
            # Rate limited (HTTP 429) — exponential backoff + jitter
            backoff_s = (2 ** attempt) * random.uniform(0.3, 1.0)
            await asyncio.sleep(backoff_s)
            backoff_total_ms += backoff_s * 1000
        raise RuntimeError("HTTP 429 — rate limit exceeded after 4 retries")


_llm_rate = RateLimiter(rpm=500)
_stt_rate = RateLimiter(rpm=500)
_tts_rate = RateLimiter(rpm=500)


# ---------------------------------------------------------------------------
# Mocked pipeline stages (semaphore + rate limit + realistic sleep)
# ---------------------------------------------------------------------------

async def mock_vad() -> tuple[float, float]:
    """Silero VAD — CPU-bound, serialized per core. Returns (queue_ms, api_ms)."""
    q0 = time.perf_counter()
    async with _vad_sem:
        queue_ms = (time.perf_counter() - q0) * 1000
        latency = sample_latency(VAD_MU, VAD_SIGMA)
        await asyncio.sleep(latency / 1000)
    return queue_ms, latency


async def mock_stt() -> tuple[float, float, float]:
    """Whisper STT. Returns (queue_ms, rate_backoff_ms, api_ms)."""
    q0 = time.perf_counter()
    async with _stt_sem:
        queue_ms = (time.perf_counter() - q0) * 1000
        rate_backoff_ms = await _stt_rate.acquire()
        latency = sample_latency(STT_MU, STT_SIGMA)
        await asyncio.sleep(latency / 1000)
    return queue_ms, rate_backoff_ms, latency


async def mock_llm(has_tool_call: bool = False) -> tuple[float, float, float]:
    """GPT-4o-mini LLM. Returns (queue_ms, rate_backoff_ms, api_ms)."""
    q0 = time.perf_counter()
    async with _llm_sem:
        queue_ms = (time.perf_counter() - q0) * 1000
        rate_backoff_ms = await _llm_rate.acquire()
        latency = sample_latency(LLM_NO_TOOL_MU, LLM_NO_TOOL_SIGMA)
        if has_tool_call:
            latency += sample_latency(LLM_TOOL_EXTRA_MU, LLM_TOOL_EXTRA_SIGMA)
        await asyncio.sleep(latency / 1000)
    return queue_ms, rate_backoff_ms, latency


async def mock_tts() -> tuple[float, float, float]:
    """OpenAI TTS. Returns (queue_ms, rate_backoff_ms, api_ms)."""
    q0 = time.perf_counter()
    async with _tts_sem:
        queue_ms = (time.perf_counter() - q0) * 1000
        rate_backoff_ms = await _tts_rate.acquire()
        latency = sample_latency(TTS_MU, TTS_SIGMA)
        await asyncio.sleep(latency / 1000)
    return queue_ms, rate_backoff_ms, latency


# ---------------------------------------------------------------------------
# Real tool functions (no mocking — actual dict lookups)
# ---------------------------------------------------------------------------

async def real_check_peptide_stock(query: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    q = query.lower().strip()
    result = None
    for name, item in agent_data.PEPTIDE_STOCK.items():
        if name.lower() == q:
            status = f"{item['quantity']} {item['unit']}" if item["quantity"] > 0 else "OUT OF STOCK"
            result = f"{name}: {item['description']} | In stock: {status} | ${item['price']} per unit."
            break
    if result is None:
        matched = [n for n, i in agent_data.PEPTIDE_STOCK.items() if any(g in q for g in i["goals"])]
        result = f"Matching: {', '.join(matched)}" if matched else "No match."
    return result, (time.perf_counter() - t0) * 1000


async def real_answer_faq(topic: str) -> tuple[str, float]:
    t0 = time.perf_counter()
    answer = agent_data.FAQS.get(topic, f"No FAQ for '{topic}'.")
    return answer, (time.perf_counter() - t0) * 1000


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TurnMetrics:
    user_id: int
    turn: int
    vad_queue_ms:  float = 0.0
    vad_ms:        float = 0.0
    stt_queue_ms:  float = 0.0
    stt_backoff_ms: float = 0.0
    stt_ms:        float = 0.0
    llm_queue_ms:  float = 0.0
    llm_backoff_ms: float = 0.0
    llm_ms:        float = 0.0
    tool_ms:       float = 0.0
    tts_queue_ms:  float = 0.0
    tts_backoff_ms: float = 0.0
    tts_ms:        float = 0.0
    e2e_ms:        float = 0.0
    error:         bool  = False
    error_msg:     str   = ""


@dataclass
class SessionMetrics:
    user_id: int
    turns: list[TurnMetrics] = field(default_factory=list)
    session_ms: float = 0.0
    error_count: int = 0


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

SCENARIOS = [
    {"name": "greeting",      "has_tool_call": False, "tool_fn": None,                      "tool_arg": None},
    {"name": "peptide_query", "has_tool_call": True,  "tool_fn": real_check_peptide_stock,   "tool_arg": lambda: random.choice(list(agent_data.PEPTIDE_STOCK.keys()))},
    {"name": "faq_query",     "has_tool_call": True,  "tool_fn": real_answer_faq,             "tool_arg": lambda: random.choice(list(agent_data.FAQS.keys()))},
]


# ---------------------------------------------------------------------------
# Session simulator
# ---------------------------------------------------------------------------

async def simulate_session(user_id: int, num_turns: int) -> SessionMetrics:
    session = SessionMetrics(user_id=user_id)
    session_start = time.perf_counter()

    scenarios = list(SCENARIOS[:num_turns])
    while len(scenarios) < num_turns:
        scenarios.append(random.choice(SCENARIOS[1:]))

    for turn_idx, scenario in enumerate(scenarios):
        turn = TurnMetrics(user_id=user_id, turn=turn_idx)
        turn_start = time.perf_counter()

        if random.random() < BASE_ERROR_RATE:
            turn.error = True
            turn.error_msg = "HTTP 500 — internal server error"
            turn.e2e_ms = (time.perf_counter() - turn_start) * 1000
            session.turns.append(turn)
            session.error_count += 1
            continue

        try:
            # VAD (CPU-bound — serialized)
            turn.vad_queue_ms, turn.vad_ms = await mock_vad()

            # STT
            turn.stt_queue_ms, turn.stt_backoff_ms, turn.stt_ms = await mock_stt()

            # Tool call (local — no external API)
            if scenario["has_tool_call"] and scenario["tool_fn"]:
                _, turn.tool_ms = await scenario["tool_fn"](scenario["tool_arg"]())

            # LLM
            turn.llm_queue_ms, turn.llm_backoff_ms, turn.llm_ms = await mock_llm(
                has_tool_call=scenario["has_tool_call"]
            )

            # TTS
            turn.tts_queue_ms, turn.tts_backoff_ms, turn.tts_ms = await mock_tts()

        except Exception as exc:
            turn.error = True
            turn.error_msg = str(exc)
            session.error_count += 1

        turn.e2e_ms = (time.perf_counter() - turn_start) * 1000
        session.turns.append(turn)

    session.session_ms = (time.perf_counter() - session_start) * 1000
    return session


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def percentile(data: list[float], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = (p / 100) * (len(s) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (idx - lo) * (s[hi] - s[lo])


def build_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}
    return {
        "count": len(values),
        "mean":  round(statistics.mean(values), 2),
        "min":   round(min(values), 2),
        "max":   round(max(values), 2),
        "p50":   round(percentile(values, 50), 2),
        "p95":   round(percentile(values, 95), 2),
        "p99":   round(percentile(values, 99), 2),
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def generate_report(sessions: list[SessionMetrics], num_users: int, num_turns: int, wall_time_s: float) -> dict:
    all_turns = [t for s in sessions for t in s.turns]
    ok = [t for t in all_turns if not t.error]

    total   = len(all_turns)
    errors  = sum(1 for t in all_turns if t.error)
    retries = sum(1 for t in ok if t.llm_backoff_ms > 0 or t.stt_backoff_ms > 0 or t.tts_backoff_ms > 0)

    # Total queue wait per turn (all stages combined)
    total_queue = [t.vad_queue_ms + t.stt_queue_ms + t.llm_queue_ms + t.tts_queue_ms for t in ok]
    total_backoff = [t.stt_backoff_ms + t.llm_backoff_ms + t.tts_backoff_ms for t in ok]

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "concurrent_users":    num_users,
            "turns_per_user":      num_turns,
            "llm_concurrency_cap": 8,
            "stt_concurrency_cap": 15,
            "tts_concurrency_cap": 12,
            "vad_concurrency_cap": 4,
            "openai_rpm_limit":    500,
        },
        "summary": {
            "total_sessions":        num_users,
            "total_turns":           total,
            "successful_turns":      len(ok),
            "error_turns":           errors,
            "error_rate_pct":        round(errors / total * 100, 2) if total else 0,
            "turns_with_429_backoff": retries,
            "wall_time_s":           round(wall_time_s, 3),
            "throughput_turns_per_sec": round(total / wall_time_s, 2) if wall_time_s else 0,
        },
        "latency_s": {
            "vad_api":       build_stats([t.vad_ms        for t in ok]),
            "vad_queue":     build_stats([t.vad_queue_ms  for t in ok]),
            "stt_api":       build_stats([t.stt_ms        for t in ok]),
            "stt_queue":     build_stats([t.stt_queue_ms  for t in ok]),
            "llm_api":       build_stats([t.llm_ms        for t in ok]),
            "llm_queue":     build_stats([t.llm_queue_ms  for t in ok]),
            "llm_backoff":   build_stats([t.llm_backoff_ms for t in ok if t.llm_backoff_ms > 0]),
            "tts_api":       build_stats([t.tts_ms        for t in ok]),
            "tts_queue":     build_stats([t.tts_queue_ms  for t in ok]),
            "tool_call":     build_stats([t.tool_ms       for t in ok if t.tool_ms > 0]),
            "queue_total":   build_stats(total_queue),
            "backoff_total": build_stats(total_backoff),
            "e2e_per_turn":  build_stats([t.e2e_ms        for t in ok]),
            "full_session":  build_stats([s.session_ms    for s in sessions]),
        },
    }
    return report


def fmt(v: float) -> str:
    return f"{v/1000:.3f}s"


def print_report(report: dict) -> None:
    cfg = report["config"]
    s   = report["summary"]
    lat = report["latency_s"]

    print("\n" + "=" * 72)
    print("  VOICE AGENT LOAD TEST — REALISTIC BOTTLENECK SIMULATION")
    print("=" * 72)
    print(f"  Timestamp        : {report['timestamp']}")
    print(f"  Concurrent users : {cfg['concurrent_users']}")
    print(f"  Turns per user   : {cfg['turns_per_user']}")
    print(f"  LLM concurrency  : {cfg['llm_concurrency_cap']} slots (OpenAI Tier 1, 500 RPM)")
    print(f"  STT concurrency  : {cfg['stt_concurrency_cap']} slots")
    print(f"  TTS concurrency  : {cfg['tts_concurrency_cap']} slots")
    print(f"  VAD concurrency  : {cfg['vad_concurrency_cap']} CPU cores")
    print()
    print("  SUMMARY")
    print(f"  Sessions         : {s['total_sessions']}")
    print(f"  Total turns      : {s['total_turns']}")
    print(f"  Successful turns : {s['successful_turns']}")
    print(f"  Failed turns     : {s['error_turns']} ({s['error_rate_pct']}%)")
    print(f"  Turns w/ 429     : {s['turns_with_429_backoff']}")
    print(f"  Wall time        : {s['wall_time_s']} s")
    print(f"  Throughput       : {s['throughput_turns_per_sec']} turns/s")
    print()

    W = [20, 7, 9, 9, 9, 9, 9, 9]
    hdr = ["Stage", "count", "mean", "min", "max", "p50", "p95", "p99"]
    row_fmt = "  " + "  ".join(f"{{:<{w}}}" for w in W)
    print(row_fmt.format(*hdr))
    print("  " + "-" * 68)

    rows = [
        ("VAD (api)",        "vad_api"),
        ("VAD (queue wait)", "vad_queue"),
        ("STT (api)",        "stt_api"),
        ("STT (queue wait)", "stt_queue"),
        ("LLM (api)",        "llm_api"),
        ("LLM (queue wait)", "llm_queue"),
        ("LLM (429 backoff)","llm_backoff"),
        ("TTS (api)",        "tts_api"),
        ("TTS (queue wait)", "tts_queue"),
        ("Tool call",        "tool_call"),
        ("--- Queue total",  "queue_total"),
        ("--- Backoff total","backoff_total"),
        ("E2E / turn",       "e2e_per_turn"),
        ("Full session",     "full_session"),
    ]
    for label, key in rows:
        st = lat[key]
        if st["count"] == 0:
            continue
        print(row_fmt.format(
            label, st["count"],
            fmt(st["mean"]), fmt(st["min"]), fmt(st["max"]),
            fmt(st["p50"]),  fmt(st["p95"]), fmt(st["p99"]),
        ))

    print("=" * 72)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def run_load_test(num_users: int, num_turns: int) -> dict:
    print(f"\nStarting load test: {num_users} concurrent users × {num_turns} turns each...")
    print("  Bottlenecks: LLM=8 slots, STT=15, TTS=12, VAD=4 CPU cores, 500 RPM limit\n")

    t0 = time.perf_counter()
    sessions: list[SessionMetrics] = await asyncio.gather(
        *[simulate_session(uid, num_turns) for uid in range(num_users)]
    )
    return generate_report(sessions, num_users, num_turns, time.perf_counter() - t0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--users",  type=int, default=100)
    parser.add_argument("--turns",  type=int, default=3)
    parser.add_argument("--output", default="load_test_report.json")
    args = parser.parse_args()

    report = asyncio.run(run_load_test(args.users, args.turns))
    print_report(report)

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Report saved to: {args.output}\n")


if __name__ == "__main__":
    main()
