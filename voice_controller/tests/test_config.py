"""Tests for config.py."""

import tempfile
from pathlib import Path

import pytest
import yaml

from voice_controller.config import (
    ConfigError,
    load_config,
    save_default_config,
)
from voice_controller.models import AppConfig, AppSettings, CommandAction, VoiceCommand


VALID_CONFIG_YAML = """\
settings:
  model: base
  language: en
  confidence_threshold: 0.9
  cooldown_ms: 1000
  sample_rate: 16000
  vad_threshold: 0.6
  vad_silence_duration_ms: 600
  input_device: 3

commands:
  - phrases:
      - next
      - next page
    action:
      key: right

  - phrases:
      - close
    action:
      hotkey:
        - ctrl
        - w
"""

MINIMAL_CONFIG_YAML = """\
commands:
  - phrases:
      - test
    action:
      key: space
"""


def _write_temp(data: str) -> Path:
    """Write YAML to a temporary file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    )
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


class TestLoadConfig:
    def test_load_valid(self):
        path = _write_temp(VALID_CONFIG_YAML)
        try:
            cfg = load_config(path)
            assert isinstance(cfg, AppConfig)
            assert cfg.settings.model == "base"
            assert cfg.settings.language == "en"
            assert cfg.settings.confidence_threshold == 0.9
            assert cfg.settings.cooldown_ms == 1000
            assert cfg.settings.vad_threshold == 0.6
            assert cfg.settings.vad_silence_duration_ms == 600
            assert cfg.settings.input_device == 3
            assert len(cfg.commands) == 2
        finally:
            path.unlink()

    def test_load_minimal(self):
        path = _write_temp(MINIMAL_CONFIG_YAML)
        try:
            cfg = load_config(path)
            assert isinstance(cfg, AppConfig)
            # Defaults applied
            assert cfg.settings.model == "tiny"
            assert cfg.settings.cooldown_ms == 800
            assert len(cfg.commands) == 1
        finally:
            path.unlink()

    def test_missing_file_generates_default(self):
        path = Path(tempfile.gettempdir()) / "nonexistent_config.yaml"
        try:
            cfg = load_config(path)
            assert isinstance(cfg, AppConfig)
            assert cfg.settings.model == "tiny"
            assert path.exists()
        finally:
            path.unlink(missing_ok=True)

    def test_empty_file_raises(self):
        path = _write_temp("")
        try:
            with pytest.raises(ConfigError, match="empty"):
                load_config(path)
        finally:
            path.unlink()

    def test_settings_only_is_valid(self):
        path = _write_temp("settings:\n  model: base\n")
        try:
            cfg = load_config(path)
            assert isinstance(cfg, AppConfig)
            assert cfg.settings.model == "base"
            assert cfg.commands == []
        finally:
            path.unlink()

    def test_bad_yaml_raises(self):
        path = _write_temp("{ this is not valid yaml [[[")
        try:
            with pytest.raises(ConfigError):
                load_config(path)
        finally:
            path.unlink()


class TestConfigValidation:
    def test_invalid_model_warns(self):
        data = {
            "settings": {"model": "huge"},
            "commands": [{"phrases": ["test"], "action": {"key": "space"}}],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.warns(UserWarning, match="not in the known model list"):
                cfg = load_config(path)
            assert cfg.settings.model == "huge"
        finally:
            path.unlink()

    def test_confidence_out_of_range(self):
        for val in (-0.1, 1.5):
            data = {
                "settings": {"confidence_threshold": val},
                "commands": [{"phrases": ["x"], "action": {"key": "space"}}],
            }
            path = _write_temp(yaml.dump(data))
            try:
                with pytest.raises(ConfigError, match="between 0.0 and 1.0"):
                    load_config(path)
            finally:
                path.unlink()

    def test_negative_cooldown(self):
        data = {
            "settings": {"cooldown_ms": -100},
            "commands": [{"phrases": ["x"], "action": {"key": "space"}}],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.raises(ConfigError, match="not be negative"):
                load_config(path)
        finally:
            path.unlink()

    def test_invalid_sample_rate(self):
        data = {
            "settings": {"sample_rate": 44100},
            "commands": [{"phrases": ["x"], "action": {"key": "space"}}],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.raises(ConfigError, match="8000 or 16000"):
                load_config(path)
        finally:
            path.unlink()

    def test_empty_phrases_raises(self):
        data = {
            "commands": [
                {"phrases": [], "action": {"key": "space"}},
            ],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.raises(ConfigError, match="non-empty"):
                load_config(path)
        finally:
            path.unlink()

    def test_no_action_raises(self):
        data = {
            "commands": [
                {"phrases": ["test"]},
            ],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.raises(ConfigError, match="action"):
                load_config(path)
        finally:
            path.unlink()

    def test_invalid_action_raises(self):
        data = {
            "commands": [
                {"phrases": ["test"], "action": {"key": "right", "hotkey": ["ctrl"]}},
            ],
        }
        path = _write_temp(yaml.dump(data))
        try:
            with pytest.raises(ConfigError, match="both"):
                load_config(path)
        finally:
            path.unlink()


class TestSaveDefaultConfig:
    def test_saves_file(self):
        path = Path(tempfile.gettempdir()) / "test_default_config.yaml"
        try:
            cfg = save_default_config(path)
            assert path.exists()
            assert isinstance(cfg, AppConfig)
        finally:
            path.unlink(missing_ok=True)
