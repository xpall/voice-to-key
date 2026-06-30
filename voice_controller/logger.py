"""Logging configuration with emoji prefixes for the voice controller."""

import logging
import sys

try:
    import colorama
    colorama.init(autoreset=True)
    _COLORAMA = True
except ImportError:
    _COLORAMA = False


class _EmojiFormatter(logging.Formatter):
    """Custom formatter that prepends emoji based on log level and message type."""

    # ANSI color codes
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    CYAN = "\033[36m"
    MAGENTA = "\033[35m"
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        prefix = getattr(record, "emoji_prefix", None)
        if prefix:
            colour = getattr(record, "colour", "")
            if colour:
                prefix = f"{colour}{prefix}{self.RESET}"
            message = f"{prefix}\n{record.getMessage()}"
        else:
            message = record.getMessage()

        if record.levelno == logging.WARNING:
            message = f"{self.YELLOW}⚠ {self.RESET}{message}"
        elif record.levelno >= logging.ERROR:
            message = f"{self.RED}🔥 {self.RESET}{message}"

        return message


_logger = logging.getLogger("voice_controller")


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging and return the module logger."""
    level = logging.DEBUG if verbose else logging.INFO
    _logger.setLevel(level)

    if not _logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        handler.setFormatter(_EmojiFormatter())
        _logger.addHandler(handler)

    return _logger


def get_logger() -> logging.Logger:
    """Return the voice controller logger."""
    return _logger


def log_heard(text: str) -> None:
    """Log transcribed speech."""
    _logger.info(
        text,
        extra={"emoji_prefix": "\U0001F3A4 Heard:", "colour": _EmojiFormatter.CYAN},
    )


def log_matched(phrase: str) -> None:
    """Log a matched command phrase."""
    _logger.info(
        phrase,
        extra={"emoji_prefix": "\N{check mark} Matched:", "colour": _EmojiFormatter.GREEN},
    )


def log_executed(action: str) -> None:
    """Log an executed keyboard action."""
    _logger.info(
        action,
        extra={"emoji_prefix": "\N{keyboard} Executed:", "colour": _EmojiFormatter.GREEN},
    )


def log_no_match() -> None:
    """Log that no command matched the heard speech."""
    _logger.info(
        "No command matched.",
        extra={"emoji_prefix": "\N{cross mark} ", "colour": _EmojiFormatter.RED if _COLORAMA else ""},
    )


def log_cooldown() -> None:
    """Log that execution was skipped due to cooldown."""
    _logger.info(
        "On cooldown, skipping.",
        extra={"emoji_prefix": "\N{hourglass} Cooldown:", "colour": _EmojiFormatter.YELLOW},
    )
