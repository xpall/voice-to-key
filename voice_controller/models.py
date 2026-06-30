"""Data models for the voice command keyboard controller."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AppSettings:
    """Application-level settings loaded from config.yaml."""

    model: str = "tiny"
    language: str = "en"
    confidence_threshold: float = 0.75
    cooldown_ms: int = 800
    sample_rate: int = 16000
    vad_threshold: float = 0.5
    vad_silence_duration_ms: int = 500
    input_device: Optional[int] = None


# Class-level constant, set after dataclass definition so it is not treated
# as a field.
AppSettings.VALID_MODELS: set[str] = {
    "tiny", "tiny.en",
    "base", "base.en",
    "small", "small.en",
    "medium", "medium.en",
}


@dataclass
class CommandAction:
    """The keyboard action to perform when a command is matched."""

    key: Optional[str] = None
    hotkey: Optional[list[str]] = None

    def __post_init__(self):
        if self.key is None and self.hotkey is None:
            raise ValueError("CommandAction must have either 'key' or 'hotkey'")
        if self.key is not None and self.hotkey is not None:
            raise ValueError(
                "CommandAction cannot have both 'key' and 'hotkey'"
            )


@dataclass
class VoiceCommand:
    """A voice command with its phrase aliases and keyboard action."""

    phrases: list[str]
    action: CommandAction


@dataclass
class AppConfig:
    """Root configuration object."""

    settings: AppSettings
    commands: list[VoiceCommand] = field(default_factory=list)
