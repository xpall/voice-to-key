"""Voice Command Keyboard Controller — entry point.

Continuously listens to the microphone, detects spoken commands, and
simulates keyboard presses.
"""

import argparse
import os
import signal
import sys
import textwrap
import threading
from pathlib import Path
from typing import Optional

from .config import load_config, ConfigError
from .keyboard_controller import (
    BackendError,
    EvdevBackend,
    KeyboardBackend,
    KeyboardController,
    PynputBackend,
)
from .logger import (
    get_logger,
    log_cooldown,
    log_executed,
    log_heard,
    log_matched,
    log_no_match,
    setup_logging,
)
from .matcher import PhraseMatcher
from .models import AppConfig, CommandAction, VoiceCommand
from .speech import (
    AudioCapture,
    AudioError,
    ContinuousListener,
    RecognitionError,
    SpeechRecognizer,
    VoiceActivityDetector,
)

log = get_logger()


def _select_backend(prefer: Optional[str] = None) -> KeyboardBackend:
    """Select the best available keyboard backend for the current platform.

    Strategy:
    - If a specific backend is requested, try that first.
    - Otherwise, try pynput (needs X11 on Linux).
    - Fall back to evdev (needs /dev/uinput on Linux).
    """
    prefer = (prefer or "").lower().strip()

    # -- Explicit request --
    if prefer == "pynput":
        return PynputBackend()
    if prefer == "evdev":
        return EvdevBackend()

    # -- Linux autodetect --
    if sys.platform.startswith("linux"):
        # Prefer pynput if DISPLAY is set (X11/Xwayland available)
        if os.environ.get("DISPLAY"):
            try:
                return PynputBackend()
            except BackendError:
                log.warning("Pynput failed, trying evdev backend...")
        # Fall back to evdev (Wayland native)
        try:
            return EvdevBackend()
        except BackendError as e:
            log.error(str(e))
            raise

    # -- macOS / Windows --
    return PynputBackend()


def _describe_action(action: CommandAction) -> str:
    """Return a human-readable description of a key action."""
    if action.key:
        return f"{action.key} key"
    if action.hotkey:
        return " + ".join(action.hotkey)
    return "unknown action"


def _run(config_path: str, verbose: bool, backend_prefer: Optional[str] = None) -> int:
    """Load config, set up listeners, and run the main loop.

    Returns 0 on clean exit, non-zero on error.
    """
    setup_logging(verbose=verbose)

    # ---- Load configuration ----
    try:
        cfg = load_config(config_path)
    except ConfigError as e:
        log.error("Configuration error: %s", e)
        return 1
    except FileNotFoundError as e:
        log.error("File not found: %s", e)
        return 1

    s = cfg.settings

    # ---- Keyboard backend ----
    try:
        backend = _select_backend(prefer=backend_prefer)
    except BackendError as e:
        log.error("Keyboard backend error: %s", e)
        return 1

    keyboard = KeyboardController(backend, cooldown_ms=s.cooldown_ms)
    matcher = PhraseMatcher(cfg.commands)

    log.info(
        "Model: %s | Language: %s | Cooldown: %d ms | Threshold: %.2f",
        s.model,
        s.language,
        s.cooldown_ms,
        s.confidence_threshold,
    )
    log.info("Commands loaded: %d", len(cfg.commands))
    log.info("Keyboard backend: %s", type(backend).__name__)
    log.info("Listening... (Ctrl+C to stop)")

    # ---- Speech pipeline ----
    capture = AudioCapture(
        sample_rate=s.sample_rate,
        device=s.input_device,
    )

    vad = VoiceActivityDetector(
        threshold=s.vad_threshold,
        sample_rate=s.sample_rate,
    )
    try:
        vad.load()
    except Exception as e:
        log.error("Failed to load VAD model: %s", e)
        return 1

    recognizer = SpeechRecognizer(
        model_size=s.model,
        language=s.language,
    )
    try:
        recognizer.load()
    except RecognitionError as e:
        log.error("%s", e)
        return 1
    except Exception as e:
        log.error("Failed to load Whisper model: %s", e)
        return 1

    listener = ContinuousListener(
        audio_capture=capture,
        vad=vad,
        recognizer=recognizer,
        silence_chunks=max(1, s.vad_silence_duration_ms // 32),
    )

    # ---- Callback: receives transcribed text ----
    def on_text(text: str) -> None:
        log_heard(text)

        command = matcher.match(text)

        if command is None:
            log_no_match()
            return

        log_matched(text)

        if not keyboard.execute(command.action):
            log_cooldown()
            return

        log_executed(_describe_action(command.action))

    # ---- Signal handling for clean shutdown ----
    shutdown_event = threading.Event()

    def _signal_handler(signum, frame):
        if not shutdown_event.is_set():
            shutdown_event.set()
            listener.stop()
            log.info("Shutting down...")

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # ---- Run ----
    try:
        listener.start(on_text)
    except AudioError as e:
        log.error("%s", e)
        return 1
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("Unexpected error")
        return 1
    finally:
        listener.stop()
        if hasattr(backend, "close"):
            backend.close()

    log.info("Goodbye!")
    return 0


def _list_devices() -> None:
    """Print available audio input devices and exit."""
    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice is not installed. Run: pip install sounddevice")
        return

    print("\nAvailable audio devices:\n")
    devices = sd.query_devices()
    default_input = sd.default.device[0]
    for d in devices:
        marker = " <-- default" if d["index"] == default_input else ""
        io = []
        if d["max_input_channels"] > 0:
            io.append(f"in:{int(d['max_input_channels'])}ch")
        if d["max_output_channels"] > 0:
            io.append(f"out:{int(d['max_output_channels'])}ch")
        io_str = ", ".join(io) if io else "no channels"
        print(
            f"  [{d['index']:>2d}] {d['name']} ({io_str}, "
            f"{int(d['default_samplerate'])} Hz){marker}"
        )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="voice-controller",
        description="Voice-controlled keyboard simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              voice-controller                      # run with config.yaml
              voice-controller -c my-config.yaml    # custom config path
              voice-controller --list-devices       # show microphones
              voice-controller -v                   # verbose logging
        """),
    )
    parser.add_argument(
        "-c", "--config",
        default="config.yaml",
        help="Path to YAML configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug-level logging",
    )
    parser.add_argument(
        "--list-devices",
        action="store_true",
        help="List available audio input devices and exit",
    )
    parser.add_argument(
        "-b", "--backend",
        choices=["pynput", "evdev"],
        default=None,
        help="Force a specific keyboard backend (default: auto-detect)",
    )

    args = parser.parse_args()

    if args.list_devices:
        _list_devices()
        return

    # Change to the directory containing the config file so the config
    # path works regardless of where the user runs the command from.
    config_path = Path(args.config)
    if not config_path.is_absolute():
        # If the file exists relative to cwd, use that; otherwise
        # resolve relative to the voice-controller package directory.
        if config_path.exists():
            config_path = config_path.resolve()
        else:
            pkg_dir = Path(__file__).resolve().parent
            config_path = (pkg_dir / config_path).resolve()

    sys.exit(_run(str(config_path), args.verbose, args.backend))


if __name__ == "__main__":
    main()
