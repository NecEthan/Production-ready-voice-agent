"""
Per-session token and cost tracker.

Subscribes to session_usage_updated events and logs a summary when the
session ends. Usage data comes from livekit-agents' AgentSessionUsage,
which aggregates across LLM, STT, and TTS calls.

Pricing constants reflect GPT-4o-mini as of 2025 — update if you
switch models or pricing changes.
"""

import logging
from dataclasses import dataclass, field

from livekit.agents.metrics.usage import LLMModelUsage, ModelUsage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pricing (USD per token — update when model or pricing changes)
# ---------------------------------------------------------------------------

# GPT-4o-mini
_LLM_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000   # $0.15 / 1M tokens
_LLM_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000  # $0.60 / 1M tokens


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


@dataclass
class SessionCostTracker:
    user_id: str
    llm_input_tokens: int = field(default=0)
    llm_output_tokens: int = field(default=0)

    @property
    def total_llm_tokens(self) -> int:
        return self.llm_input_tokens + self.llm_output_tokens

    @property
    def estimated_cost_usd(self) -> float:
        return (
            self.llm_input_tokens * _LLM_INPUT_COST_PER_TOKEN
            + self.llm_output_tokens * _LLM_OUTPUT_COST_PER_TOKEN
        )

    def update(self, model_usage: list[ModelUsage]) -> None:
        """
        Called on every session_usage_updated event.
        AgentSessionUsage reports cumulative totals, so we overwrite rather
        than accumulate.
        """
        for usage in model_usage:
            if isinstance(usage, LLMModelUsage):
                self.llm_input_tokens = usage.input_tokens
                self.llm_output_tokens = usage.output_tokens

    def log_summary(self) -> None:
        logger.info(
            "Session closed — user=%s | LLM tokens: %d in / %d out (total %d) "
            "| Estimated cost: $%.6f",
            self.user_id,
            self.llm_input_tokens,
            self.llm_output_tokens,
            self.total_llm_tokens,
            self.estimated_cost_usd,
        )
