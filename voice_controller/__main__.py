"""Configuration for the voice-controller package.

Exposes a console script entry point.
"""


def main_entry():
    """Entry point for the `voice-controller` console script."""
    from .main import main
    main()
