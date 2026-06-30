"""Keyboard simulation with pluggable backends and cooldown support.

Provides:
- Abstract KeyboardBackend interface
- PynputBackend: cross-platform via pynput (X11, macOS, Windows)
- EvdevBackend: Linux kernel-level via /dev/uinput (Wayland)
- KeyboardController: cooldown manager wrapping a backend
"""

import logging
from abc import ABC, abstractmethod

from .models import CommandAction
from .utils import CooldownTimer

log = logging.getLogger(__name__)

# Mapping from user-friendly key names to pynput Key enum names and evdev codes
_KEY_MAP: dict[str, tuple[str, int]] = {
    "up": ("up", 103),
    "down": ("down", 108),
    "left": ("left", 105),
    "right": ("right", 106),
    "space": ("space", 57),
    "enter": ("enter", 28),
    "return": ("enter", 28),
    "tab": ("tab", 15),
    "escape": ("esc", 1),
    "esc": ("esc", 1),
    "backspace": ("backspace", 14),
    "delete": ("delete", 111),
    "home": ("home", 102),
    "end": ("end", 107),
    "page_up": ("page_up", 104),
    "page_down": ("page_down", 109),
    "insert": ("insert", 110),
    "f1": ("f1", 59),
    "f2": ("f2", 60),
    "f3": ("f3", 61),
    "f4": ("f4", 62),
    "f5": ("f5", 63),
    "f6": ("f6", 64),
    "f7": ("f7", 65),
    "f8": ("f8", 66),
    "f9": ("f9", 67),
    "f10": ("f10", 68),
    "f11": ("f11", 87),
    "f12": ("f12", 88),
    "ctrl": ("ctrl_l", 29),
    "alt": ("alt_l", 56),
    "shift": ("shift_l", 42),
    "cmd": ("cmd_l", 125),
    "win": ("cmd_l", 125),
    "super": ("cmd_l", 125),
    "+": ("+", 13),
    "-": ("-", 12),
    "=": ("=", 13),
    "minus": ("-", 12),
    "plus": ("+", 13),
    "up_arrow": ("up", 103),
    "down_arrow": ("down", 108),
    "left_arrow": ("left", 105),
    "right_arrow": ("right", 106),
}


class KeyboardBackend(ABC):
    """Abstract interface for keyboard simulation backends."""

    @abstractmethod
    def press(self, key: str) -> None:
        """Press and release a single key."""

    @abstractmethod
    def hotkey(self, *keys: str) -> None:
        """Hold multiple keys simultaneously, then release in reverse order."""


class PynputBackend(KeyboardBackend):
    """Keyboard backend using pynput (cross-platform, X11 on Linux)."""

    def __init__(self) -> None:
        try:
            from pynput.keyboard import Controller, Key
        except ImportError as e:
            raise BackendError(
                "pynput is not installed. Run: pip install pynput"
            ) from e

        self._controller = Controller()
        self._Key = Key

    def press(self, key: str) -> None:
        resolved = self._resolve_key(key)
        self._controller.press(resolved)
        self._controller.release(resolved)

    def hotkey(self, *keys: str) -> None:
        resolved = [self._resolve_key(k) for k in keys]
        with self._controller.pressed(*resolved):
            pass

    def _resolve_key(self, key: str) -> object:
        """Resolve a string key name to a pynput Key or character."""
        key_lower = key.lower().strip()

        if key_lower in _KEY_MAP:
            pynput_name = _KEY_MAP[key_lower][0]
            try:
                return getattr(self._Key, pynput_name)
            except AttributeError:
                pass

        # Single character keys
        if len(key) == 1:
            return key

        # Multi-character fallback: try as a Key enum name
        try:
            return getattr(self._Key, key_lower)
        except AttributeError:
            raise BackendError(f"Unknown key: {key!r}")

    def __repr__(self) -> str:
        return "PynputBackend()"


class EvdevBackend(KeyboardBackend):
    """Keyboard backend using python-evdev UInput (Linux kernel-level).

    Works on both X11 and Wayland. Requires write access to /dev/uinput.
    """

    def __init__(self) -> None:
        try:
            from evdev import UInput, ecodes
        except ImportError as e:
            raise BackendError(
                "evdev is not installed. Run: pip install evdev"
            ) from e

        self._ecodes = ecodes

        # Gather all unique keycodes we might need
        keycodes: set[int] = set()
        for _pynput_name, code in _KEY_MAP.values():
            keycodes.add(code)

        try:
            self._uinput = UInput(
                # evdev requires at least one capability to be non-empty.
                # We supply both KEY and REL (relative axes) because some
                # kernels reject a device with REL present but empty key
                # capabilities, and vice versa.  Using only keys avoids
                # creating an unwanted virtual mouse.
                events={ecodes.EV_KEY: list(keycodes)},
                name="Voice Controller Virtual Keyboard",
            )
        except PermissionError:
            raise BackendError(
                "Cannot open /dev/uinput for writing.\n\n"
                "To fix, add a udev rule (one-time setup):\n"
                '  echo \'KERNEL=="uinput", MODE="0660", GROUP="input"\''
                " | sudo tee /etc/udev/rules.d/99-uinput.rules\n"
                "  sudo usermod -aG input $USER\n"
                "  sudo udevadm control --reload-rules\n"
                "  sudo udevadm trigger\n"
                "Then log out and back in."
            ) from None
        except OSError as e:
            raise BackendError(
                f"Failed to create UInput device: {e}"
            ) from e

    def press(self, key: str) -> None:
        code = self._resolve_code(key)
        self._uinput.write(self._ecodes.EV_KEY, code, 1)  # press
        self._uinput.write(self._ecodes.EV_KEY, code, 0)  # release
        self._uinput.syn()

    def hotkey(self, *keys: str) -> None:
        codes = [self._resolve_code(k) for k in keys]
        # Press all
        for code in codes:
            self._uinput.write(self._ecodes.EV_KEY, code, 1)
            self._uinput.syn()
        # Release in reverse
        for code in reversed(codes):
            self._uinput.write(self._ecodes.EV_KEY, code, 0)
            self._uinput.syn()

    def _resolve_code(self, key: str) -> int:
        """Resolve a string key name to an evdev keycode."""
        key_lower = key.lower().strip()

        if key_lower in _KEY_MAP:
            return _KEY_MAP[key_lower][1]

        # Single character: use KEY_ prefix lookup
        if len(key) == 1:
            keycode_name = f"KEY_{key.upper()}"
            code = getattr(self._ecodes, keycode_name, None)
            if code is not None:
                return code

        raise BackendError(f"Unknown key: {key!r}")

    def close(self) -> None:
        """Release the UInput device."""
        if self._uinput:
            self._uinput.close()

    def __repr__(self) -> str:
        return "EvdevBackend()"


class KeyboardController:
    """High-level keyboard controller with cooldown support.

    Wraps a KeyboardBackend and enforces a cooldown between executions.
    """

    def __init__(self, backend: KeyboardBackend, cooldown_ms: int = 800) -> None:
        self._backend = backend
        self._cooldown = CooldownTimer(cooldown_ms)

    def execute(self, action: CommandAction) -> bool:
        """Execute a CommandAction, respecting the cooldown.

        Returns True if the action was executed, False if it was skipped
        due to cooldown.
        """
        if not self._cooldown.is_ready():
            return False

        try:
            if action.key is not None:
                self._backend.press(action.key)
            elif action.hotkey is not None:
                self._backend.hotkey(*action.hotkey)
        except BackendError:
            raise
        except Exception as e:
            raise BackendError(
                f"Failed to execute action {action}: {e}"
            ) from e

        self._cooldown.trigger()
        return True

    def __repr__(self) -> str:
        return f"KeyboardController(backend={self._backend!r})"


class BackendError(Exception):
    """Raised when a keyboard backend encounters an error."""
