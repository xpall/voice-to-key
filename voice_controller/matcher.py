"""Phrase matching engine for voice commands.

Supports case-insensitive exact matching with punctuation and whitespace
normalization. Structured to allow adding fuzzy matching in the future.
"""

from typing import Optional

from .models import VoiceCommand
from .utils import normalize_text


class PhraseMatcher:
    """Match transcribed speech text against configured voice commands."""

    def __init__(self, commands: list[VoiceCommand]) -> None:
        self._commands = commands

    def match(self, text: str) -> Optional[VoiceCommand]:
        """Return the VoiceCommand that matches the given text, or None.

        The text is normalized (lowercased, punctuation removed, whitespace
        collapsed) and compared against all configured phrases.
        """
        normalized = normalize_text(text)
        if not normalized:
            return None

        for command in self._commands:
            for phrase in command.phrases:
                if normalize_text(phrase) == normalized:
                    return command

        return None
