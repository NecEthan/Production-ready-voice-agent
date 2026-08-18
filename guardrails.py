"""
Guardrail utilities for the ReceptionistAgent.

Checks run before the LLM sees user input, keeping the agent on-scope
and preventing prompt injection.

Production hardening applied:
- NFKC unicode normalization (defeats homoglyph / fullwidth substitution)
- Zero-width and control character stripping (defeats invisible character insertion)
- Collapsed-spacing normalisation (defeats "i g n o r e" and "i-g-n-o-r-e" spacing tricks)
- Patterns tuned to minimise false positives on legitimate clinic speech
- Match logging records which pattern triggered (security audit trail)
"""

import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Text normalisation (applied before pattern matching)
# ---------------------------------------------------------------------------

# Zero-width / invisible Unicode categories to strip
_ZERO_WIDTH_RE = re.compile(
    r"[\u00ad\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff]"
)

# Runs of whitespace or common separator punctuation collapsed to a single space
# Catches: "i g n o r e", "i-g-n-o-r-e", "i.g.n.o.r.e", "i/g/n/o/r/e"
_SEPARATOR_RE = re.compile(r"[\s\-_./|\\,;:!?'\"(){}\[\]]+")


def _normalize(text: str) -> str:
    """Normalise text to defeat common evasion techniques before regex matching."""
    # 1. NFKC: fullwidth latin → ASCII, homoglyphs → canonical form
    text = unicodedata.normalize("NFKC", text)
    # 2. Strip zero-width / invisible characters
    text = _ZERO_WIDTH_RE.sub("", text)
    # 3. Collapse separator runs so spaced-out words become detectable
    text = _SEPARATOR_RE.sub(" ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Prompt injection patterns
# Ordered roughly by likelihood; all matched against normalised text.
# Each tuple is (label, compiled_regex) for audit logging.
# ---------------------------------------------------------------------------

_RAW_PATTERNS: list[tuple[str, str]] = [
    # Core instruction-override phrases
    (
        "ignore_instructions",
        r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|prompt|rules?|directions?)",
    ),
    (
        "forget_instructions",
        r"forget\s+(your|all|the)\s+(instructions?|prompt|rules?|guidelines?|training)",
    ),
    (
        "disregard_instructions",
        r"disregard\s+(your\s+)?(instructions?|rules?|guidelines?|previous)",
    ),
    (
        "override_instructions",
        r"override\s+(your\s+)?(instructions?|rules?|guidelines?|safety)",
    ),
    # Identity hijack
    (
        "you_are_now",
        r"you\s+are\s+now\s+(a|an|the)\s+\w",  # "you are now a pirate"
    ),
    (
        "act_as_different_entity",
        r"act\s+as\s+(a|an)\s+(?!clinic|receptionist|specialist|assistant)\w",
    ),
    (
        "pretend_to_be",
        r"pretend\s+(you\s+are|to\s+be)\s+(?!helpful|polite|friendly)\w",
    ),
    (
        "your_true_self",
        r"your\s+true\s+(self|purpose|nature|instructions?|personality)",
    ),
    (
        "from_now_on",
        r"from\s+now\s+on\s+you\s+(will|should|must|are)",
    ),
    # New prompt injection
    (
        "new_system_prompt",
        r"new\s+(system\s+)?prompt\s*[:=\[]",
    ),
    (
        "system_prompt_injection",
        r"\[?\s*(system|assistant|user)\s*\]\s*:",  # "[system]:" style injection
    ),
    # Mode / privilege escalation
    (
        "developer_mode",
        r"(developer|dev|debug|admin|sudo|god|unrestricted|unsafe|raw)\s+mode",
    ),
    # Known jailbreak terms
    (
        "jailbreak_keyword",
        r"\bjailbreak\b",
    ),
    (
        "dan_keyword",
        r"\bDAN\b",  # "Do Anything Now"
    ),
    (
        "token_manipulation",
        r"\b(</?\s*(s|system|SYS|INST|HUMAN|AI|assistant)\s*>|\[INST\]|\[/?SYS\])",
    ),
]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (label, re.compile(pattern, re.IGNORECASE))
    for label, pattern in _RAW_PATTERNS
]


def has_prompt_injection(text: str) -> tuple[bool, str | None]:
    """
    Check normalised text for prompt injection patterns.

    Returns (detected: bool, matched_label: str | None).
    matched_label is None when no injection is found.
    """
    normalised = _normalize(text)
    for label, pattern in _PATTERNS:
        if pattern.search(normalised):
            return True, label
    return False, None


# ---------------------------------------------------------------------------
# Input length guard
# ---------------------------------------------------------------------------

# Anything beyond this is likely token-stuffing; truncate before LLM sees it.
MAX_USER_INPUT_CHARS = 500

# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

INJECTION_REPLY = (
    "I'm only able to help with Peptide Wellness Clinic services — "
    "appointments, peptide information, and clinic questions. "
    "How can I help you today?"
)

TRUNCATION_NOTICE = (
    " [Please keep your message brief so I can help you more effectively.]"
)
