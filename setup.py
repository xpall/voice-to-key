from setuptools import setup, find_packages

setup(
    name="voice-controller",
    version="0.1.0",
    description="Voice-controlled keyboard simulation",
    packages=find_packages(exclude=["tests", "tests.*"]),
    python_requires=">=3.9",
    install_requires=[
        "faster-whisper>=1.0.0",
        "sounddevice>=0.4.0",
        "numpy>=1.24.0",
        "silero-vad>=5.0.0",
        "pynput>=1.7.0",
        "evdev>=1.6.0",
        "pyyaml>=6.0",
        "colorama>=0.4.0",
        "tqdm>=4.0.0",
    ],
    entry_points={
        "console_scripts": [
            "voice-controller=voice_controller.main:main",
        ],
    },
)
