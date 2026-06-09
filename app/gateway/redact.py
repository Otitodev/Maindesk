"""Outbound secret redaction (TRD §6.3).

Every PatientReply must pass through `redact()` before it leaves the
gateway. The patterns here are deliberately broad — false positives
are cheap (a masked string in a reply); false negatives leak secrets.
"""

from __future__ import annotations

import re
from typing import Final

# Order matters: longer/more-specific patterns first so shorter ones
# don't carve up a match before the specific one fires.
REDACT_PATTERNS: Final[list[tuple[re.Pattern[str], str]]] = [
    # Bearer tokens and similar `Authorization` payloads.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]+"), "[REDACTED:TOKEN]"),
    # API-key-ish blobs: long runs with sk_/pk_/api_/key_ prefixes.
    # Allow internal `_` / `-` so segmented keys like `sk_live_ABCD…` match.
    (
        re.compile(r"\b(?:sk|pk|api|key)[_-][A-Za-z0-9][A-Za-z0-9_-]{15,}\b"),
        "[REDACTED:KEY]",
    ),
    # 13–19 digit card numbers, optionally space/dash separated.
    (
        re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
        "[REDACTED:CARD]",
    ),
    # US-style SSN.
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED:SSN]"),
    # JWT-shaped tokens.
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
        "[REDACTED:JWT]",
    ),
]


def redact(text: str) -> str:
    """Apply all REDACT_PATTERNS to `text`. Idempotent and pure."""
    if not text:
        return text
    out = text
    for pattern, placeholder in REDACT_PATTERNS:
        out = pattern.sub(placeholder, out)
    return out
