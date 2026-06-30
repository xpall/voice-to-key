"""Tests for keyboard_controller.py."""

import time

import pytest

from voice_controller.keyboard_controller import (
    BackendError,
    KeyboardBackend,
    KeyboardController,
    _KEY_MAP,
)
from voice_controller.models import CommandAction
from voice_controller.utils import CooldownTimer as CT


class MockBackend(KeyboardBackend):
    """In-memory backend that records key presses for testing."""

    def __init__(self):
        self.pressed: list[str] = []
        self.hotkeys: list[list[str]] = []

    def press(self, key: str) -> None:
        self.pressed.append(key)

    def hotkey(self, *keys: str) -> None:
        self.hotkeys.append(list(keys))


class TestKeyMap:
    def test_all_keys_have_both_fields(self):
        for name, (pynput_name, evdev_code) in _KEY_MAP.items():
            assert isinstance(pynput_name, str), f"{name}: pynput_name is not str"
            assert isinstance(evdev_code, int), f"{name}: evdev_code is not int"
            assert evdev_code > 0, f"{name}: invalid evdev_code"

    def test_common_keys(self):
        assert "up" in _KEY_MAP
        assert "down" in _KEY_MAP
        assert "left" in _KEY_MAP
        assert "right" in _KEY_MAP
        assert "space" in _KEY_MAP
        assert "ctrl" in _KEY_MAP
        assert "alt" in _KEY_MAP
        assert "shift" in _KEY_MAP


class TestMockBackend:
    def test_press_single_key(self):
        backend = MockBackend()
        backend.press("right")
        assert backend.pressed == ["right"]

    def test_press_multiple_keys(self):
        backend = MockBackend()
        backend.press("a")
        backend.press("b")
        backend.press("space")
        assert backend.pressed == ["a", "b", "space"]

    def test_hotkey(self):
        backend = MockBackend()
        backend.hotkey("ctrl", "t")
        assert backend.hotkeys == [["ctrl", "t"]]

    def test_hotkey_multiple(self):
        backend = MockBackend()
        backend.hotkey("ctrl", "shift", "t")
        backend.hotkey("ctrl", "w")
        assert backend.hotkeys == [["ctrl", "shift", "t"], ["ctrl", "w"]]


class TestKeyboardController:
    @pytest.fixture
    def backend(self):
        return MockBackend()

    @pytest.fixture
    def controller(self, backend):
        return KeyboardController(backend, cooldown_ms=100)

    def test_execute_single_key(self, controller, backend):
        action = CommandAction(key="right")
        assert controller.execute(action) is True
        assert backend.pressed == ["right"]

    def test_execute_hotkey(self, controller, backend):
        action = CommandAction(hotkey=["ctrl", "t"])
        assert controller.execute(action) is True
        assert backend.hotkeys == [["ctrl", "t"]]

    def test_cooldown_prevents_immediate_repeat(self, controller, backend):
        action = CommandAction(key="right")
        assert controller.execute(action) is True
        # Second call within cooldown
        assert controller.execute(action) is False
        assert backend.pressed == ["right"]  # Only one press

    def test_cooldown_allows_after_timeout(self, controller, backend):
        action = CommandAction(key="right")
        assert controller.execute(action) is True
        time.sleep(0.15)
        assert controller.execute(action) is True
        assert backend.pressed == ["right", "right"]


class TestCooldownTimer:
    def test_immediately_ready(self):
        t = CT(cooldown_ms=100)
        assert t.is_ready()

    def test_not_ready_after_trigger(self):
        t = CT(cooldown_ms=200)
        t.trigger()
        assert not t.is_ready()

    def test_ready_after_wait(self):
        t = CT(cooldown_ms=50)
        t.trigger()
        time.sleep(0.1)
        assert t.is_ready()

    def test_time_remaining_decreases(self):
        t = CT(cooldown_ms=500)
        t.trigger()
        remaining = t.time_remaining_ms()
        assert 0 < remaining <= 500
