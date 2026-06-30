"""YAML configuration loader and validator."""

import os
import warnings
from pathlib import Path
from typing import Any

import yaml

from .models import AppConfig, AppSettings, CommandAction, VoiceCommand

DEFAULT_CONFIG_PATH = Path("config.yaml")

DEFAULT_CONFIG_YAML = """\
settings:
  model: tiny
  language: en
  confidence_threshold: 0.75
  cooldown_ms: 800
  sample_rate: 16000
  vad_threshold: 0.5
  vad_silence_duration_ms: 500

commands:
  - phrases:
      - next
      - next page
      - continue
    action:
      key: right

  - phrases:
      - previous
      - previous page
      - back
    action:
      key: left

  - phrases:
      - zoom in
    action:
      key: "+"

  - phrases:
      - zoom out
    action:
      key: "-"

  - phrases:
      - play
      - pause
    action:
      key: space

  - phrases:
      - new tab
    action:
      hotkey:
        - ctrl
        - t

  - phrases:
      - close tab
    action:
      hotkey:
        - ctrl
        - w
"""


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load and validate configuration from a YAML file.

    If the config file does not exist, a default configuration is generated
    and saved to the given path.
    """
    path = Path(path)

    if not path.exists():
        return _generate_default(path)

    with open(path, "r", encoding="utf-8") as f:
        try:
            raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Failed to parse {path}: {e}") from e

    if raw is None:
        raise ConfigError(f"Configuration file {path} is empty.")

    return _parse_config(raw, path)


def save_default_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Save the default configuration to disk and return the parsed config."""
    path = Path(path)
    return _generate_default(path)


def _generate_default(path: Path) -> AppConfig:
    """Write the default config YAML to disk and return the parsed config."""
    path.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    raw = yaml.safe_load(DEFAULT_CONFIG_YAML)
    config = _parse_config(raw, path)
    return config


def _parse_config(raw: dict[str, Any], path: Path) -> AppConfig:
    """Parse raw YAML dict into a validated AppConfig."""
    settings_raw = raw.get("settings", {})
    if not isinstance(settings_raw, dict):
        raise ConfigError("'settings' section must be a dictionary.")

    settings = _parse_settings(settings_raw)

    commands_raw = raw.get("commands", [])
    if not isinstance(commands_raw, list):
        raise ConfigError("'commands' section must be a list.")

    commands = _parse_commands(commands_raw)

    return AppConfig(settings=settings, commands=commands)


def _parse_settings(raw: dict[str, Any]) -> AppSettings:
    """Parse settings dict into an AppSettings with validation."""
    model = raw.get("model", "tiny")
    if not isinstance(model, str):
        raise ConfigError("settings.model must be a string.")
    if model not in AppSettings.VALID_MODELS:
        warnings.warn(
            f"Model '{model}' is not in the known model list. "
            f"Known models: {sorted(AppSettings.VALID_MODELS)}"
        )

    language = raw.get("language", "en")
    if not isinstance(language, str):
        raise ConfigError("settings.language must be a string.")

    confidence_threshold = raw.get("confidence_threshold", 0.75)
    if not isinstance(confidence_threshold, (int, float)):
        raise ConfigError("settings.confidence_threshold must be a number.")
    if not (0.0 <= confidence_threshold <= 1.0):
        raise ConfigError(
            "settings.confidence_threshold must be between 0.0 and 1.0."
        )

    cooldown_ms = raw.get("cooldown_ms", 800)
    if not isinstance(cooldown_ms, int):
        raise ConfigError("settings.cooldown_ms must be an integer.")
    if cooldown_ms < 0:
        raise ConfigError("settings.cooldown_ms must not be negative.")

    sample_rate = raw.get("sample_rate", 16000)
    if not isinstance(sample_rate, int):
        raise ConfigError("settings.sample_rate must be an integer.")
    if sample_rate not in (8000, 16000):
        raise ConfigError("settings.sample_rate must be 8000 or 16000.")

    vad_threshold = raw.get("vad_threshold", 0.5)
    if not isinstance(vad_threshold, (int, float)):
        raise ConfigError("settings.vad_threshold must be a number.")
    if not (0.0 <= vad_threshold <= 1.0):
        raise ConfigError("settings.vad_threshold must be between 0.0 and 1.0.")

    vad_silence_duration_ms = raw.get("vad_silence_duration_ms", 500)
    if not isinstance(vad_silence_duration_ms, int):
        raise ConfigError("settings.vad_silence_duration_ms must be an integer.")
    if vad_silence_duration_ms < 100:
        raise ConfigError(
            "settings.vad_silence_duration_ms must be at least 100."
        )

    input_device = raw.get("input_device")
    if input_device is not None and not isinstance(input_device, int):
        raise ConfigError("settings.input_device must be an integer or null.")

    return AppSettings(
        model=model,
        language=language,
        confidence_threshold=confidence_threshold,
        cooldown_ms=cooldown_ms,
        sample_rate=sample_rate,
        vad_threshold=vad_threshold,
        vad_silence_duration_ms=vad_silence_duration_ms,
        input_device=input_device,
    )


def _parse_commands(raw: list[dict[str, Any]]) -> list[VoiceCommand]:
    """Parse a list of command dicts into VoiceCommand objects."""
    commands: list[VoiceCommand] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ConfigError(f"Command at index {i} must be a dictionary.")

        phrases = item.get("phrases", [])
        if not isinstance(phrases, list) or not phrases:
            raise ConfigError(
                f"Command at index {i} must have a non-empty 'phrases' list."
            )
        for j, phrase in enumerate(phrases):
            if not isinstance(phrase, str) or not phrase.strip():
                raise ConfigError(
                    f"Phrase {j} in command {i} must be a non-empty string."
                )

        action_raw = item.get("action")
        if not isinstance(action_raw, dict):
            raise ConfigError(f"Command at index {i} must have an 'action' dict.")

        try:
            action = CommandAction(
                key=action_raw.get("key"),
                hotkey=action_raw.get("hotkey"),
            )
        except ValueError as e:
            raise ConfigError(
                f"Command at index {i} has invalid action: {e}"
            ) from e

        commands.append(VoiceCommand(phrases=phrases, action=action))
    return commands


class ConfigError(Exception):
    """Raised when configuration validation fails."""
