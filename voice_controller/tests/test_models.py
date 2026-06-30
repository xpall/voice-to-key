"""Tests for models.py dataclasses."""

import pytest

from voice_controller.models import AppConfig, AppSettings, CommandAction, VoiceCommand


class TestCommandAction:
    def test_key_only(self):
        action = CommandAction(key="right")
        assert action.key == "right"
        assert action.hotkey is None

    def test_hotkey_only(self):
        action = CommandAction(hotkey=["ctrl", "t"])
        assert action.key is None
        assert action.hotkey == ["ctrl", "t"]

    def test_neither_raises(self):
        with pytest.raises(ValueError, match="must have either"):
            CommandAction()

    def test_both_raises(self):
        with pytest.raises(ValueError, match="cannot have both"):
            CommandAction(key="right", hotkey=["ctrl"])


class TestVoiceCommand:
    def test_construction(self):
        action = CommandAction(key="space")
        cmd = VoiceCommand(phrases=["play", "pause"], action=action)
        assert cmd.phrases == ["play", "pause"]
        assert cmd.action.key == "space"

    def test_single_phrase(self):
        action = CommandAction(hotkey=["ctrl", "w"])
        cmd = VoiceCommand(phrases=["close"], action=action)
        assert len(cmd.phrases) == 1


class TestAppSettings:
    def test_defaults(self):
        s = AppSettings()
        assert s.model == "tiny"
        assert s.language == "en"
        assert s.confidence_threshold == 0.75
        assert s.cooldown_ms == 800
        assert s.sample_rate == 16000
        assert s.vad_threshold == 0.5
        assert s.vad_silence_duration_ms == 500
        assert s.input_device is None

    def test_valid_models(self):
        assert "tiny" in AppSettings.VALID_MODELS
        assert "base" in AppSettings.VALID_MODELS
        assert "small" in AppSettings.VALID_MODELS
        assert "medium" in AppSettings.VALID_MODELS

    def test_custom_values(self):
        s = AppSettings(
            model="base",
            language="fr",
            cooldown_ms=1000,
            input_device=2,
        )
        assert s.model == "base"
        assert s.language == "fr"
        assert s.cooldown_ms == 1000
        assert s.input_device == 2


class TestAppConfig:
    def test_empty_commands(self):
        cfg = AppConfig(settings=AppSettings())
        assert cfg.commands == []

    def test_with_commands(self):
        action = CommandAction(key="right")
        cmd = VoiceCommand(phrases=["next"], action=action)
        cfg = AppConfig(settings=AppSettings(), commands=[cmd])
        assert len(cfg.commands) == 1
        assert cfg.commands[0].phrases[0] == "next"
