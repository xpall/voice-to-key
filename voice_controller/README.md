# Voice Command Keyboard Controller

Control your computer hands-free with voice commands. Continuously listens to
your microphone, transcribes speech locally using Whisper, and simulates
keyboard presses.

**Primary target:** Linux (X11 and Wayland). macOS and Windows supported
via `pynput`.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e /path/to/voice_controller
```

No `apt`, `dnf`, `brew`, or other system package managers required for the
Python dependencies — everything comes from `pip`.

### System Requirements

| Requirement | Needed For | How to Install (one-time) |
|---|---|---|
| `libportaudio2` | Microphone capture via `sounddevice` | `sudo apt install libportaudio2` (Ubuntu/Debian) or `sudo dnf install portaudio` (Fedora) |
| `/dev/uinput` access | Keyboard injection on Wayland (no X11) | See [Wayland Setup](#wayland-linux) below |

`libportaudio2` is already installed on most desktop Linux distributions
(it is a dependency of PulseAudio/PipeWire). If your microphone works in
other applications, you likely already have it.

### Wayland (Linux)

If you run a pure Wayland session without Xwayland, `pynput` cannot inject
keystrokes. The application falls back to `python-evdev` which writes to
`/dev/uinput`. You need write access:

```bash
# Create a udev rule (one-time setup)
echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo usermod -aG input $USER
sudo udevadm control --reload-rules
sudo udevadm trigger
# Log out and back in
```

This is **not required** if you run X11 or Xwayland — `pynput` handles those
without root.

## Quick Start

```bash
# Generate a default config file (config.yaml) if one doesn't exist
voice-controller

# List available microphones
voice-controller --list-devices

# Use a custom config
voice-controller -c my-commands.yaml

# Verbose output
voice-controller -v
```

## Configuration

Commands are defined in `config.yaml`:

```yaml
settings:
  model: tiny              # tiny, tiny.en, base, base.en, small, small.en
  language: en
  confidence_threshold: 0.75
  cooldown_ms: 800         # Minimum gap between executed commands
  sample_rate: 16000
  vad_threshold: 0.5       # Voice activity detection sensitivity
  vad_silence_duration_ms: 500

commands:
  - phrases:
      - next
      - next page
      - continue
    action:
      key: right

  - phrases:
      - zoom in
    action:
      key: "+"

  - phrases:
      - new tab
    action:
      hotkey:
        - ctrl
        - t
```

Each command can have:

- **`key`** — a single key press (`right`, `space`, `tab`, `f1`, `+`, `a`, etc.)
- **`hotkey`** — a key combination (`ctrl+t`, `ctrl+shift+esc`)

### Supported Key Names

`up`, `down`, `left`, `right`, `space`, `enter`, `tab`, `escape`, `backspace`,
`delete`, `home`, `end`, `page_up`, `page_down`, `insert`, `f1`–`f12`,
`ctrl`, `alt`, `shift`, `cmd`/`win`/`super`, `+`, `-`, `=`, and single
characters (`a`–`z`, `0`–`9`).

## How It Works

```
Microphone → AudioCapture → VoiceActivityDetector (Silero VAD)
                                    │
                          ┌─ silence ─┤── speech ─┐
                          ▼                      ▼
                     (skip)            SpeechRecognizer (Whisper)
                                              │
                                              ▼
                                         PhraseMatcher
                                              │
                                    ┌─ match? ─┤─ no match ─┐
                                    ▼                      ▼
                            KeyboardController       log "No match"
                            (with cooldown)
                                    │
                                    ▼
                             KeyboardBackend
                         (pynput or evdev UInput)
```

- **AudioCapture** streams 16kHz mono audio from your default microphone.
- **VoiceActivityDetector** (Silero VAD) detects speech with <200µs per
  32ms chunk.
- **SpeechRecognizer** (faster-whisper, tiny model by default) transcribes
  completed speech segments offline.
- **PhraseMatcher** normalizes text (lowercase, no punctuation, collapsed
  whitespace) and matches against configured phrases.
- **KeyboardController** simulates key presses with a configurable cooldown
  to prevent repeated triggers.

## Running Tests

```bash
python -m pytest voice_controller/tests/ -v
```

## Architecture

```
voice_controller/
├── main.py                 # Entry point, CLI, signal handling
├── config.py               # YAML config load/validate/save
├── models.py               # Dataclasses (AppConfig, VoiceCommand, etc.)
├── speech.py               # AudioCapture, VAD, SpeechRecognizer, ContinuousListener
├── matcher.py              # Phrase normalization and matching
├── keyboard_controller.py  # Abstract backend + PynputBackend + EvdevBackend + cooldown
├── utils.py                # Text normalization, CooldownTimer
├── logger.py               # Emoji-prefixed logging
├── config.yaml             # Default configuration
└── tests/
    ├── test_models.py
    ├── test_config.py
    ├── test_matcher.py
    └── test_keyboard.py
```

Each module has a single responsibility. The keyboard abstraction allows
swapping backends without changing the rest of the code.

## Limitations

- **libportaudio2** — Required for microphone access. Pre-installed on most
  Linux desktops. If missing: `sudo apt install libportaudio2` (one-time).
- **Wayland keyboard injection** — Needs `/dev/uinput` write access. See
  Setup section above.
- **First run** — Downloads the Whisper model (~75 MB for `tiny`) from
  Hugging Face Hub. Subsequent runs use the cached model.
- **PyTorch dependency** — `silero-vad` depends on `torch` (~700 MB
  installed). This is the largest dependency.
