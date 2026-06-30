"""Utility functions for text normalization and timing."""

import re
import time


_PUNCTUATION_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize transcribed text for matching.

    - Lowercase
    - Strip surrounding whitespace
    - Remove punctuation
    - Collapse multiple spaces into one
    """
    text = text.lower().strip()
    text = _PUNCTUATION_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text


class CooldownTimer:
    """A cooldown timer that tracks elapsed time since last trigger."""

    def __init__(self, cooldown_ms: int):
        self._cooldown_s = cooldown_ms / 1000.0
        self._last_trigger: float = 0.0

    def is_ready(self) -> bool:
        """Return True if the cooldown period has elapsed since last trigger."""
        return time.monotonic() - self._last_trigger >= self._cooldown_s

    def trigger(self) -> None:
        """Mark the timer as triggered (reset cooldown)."""
        self._last_trigger = time.monotonic()

    def time_remaining_ms(self) -> int:
        """Return approximate milliseconds remaining in the cooldown."""
        elapsed = time.monotonic() - self._last_trigger
        remaining = self._cooldown_s - elapsed
        return max(0, int(remaining * 1000))
