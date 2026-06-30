"""Tests for matcher.py."""

import pytest

from voice_controller.matcher import PhraseMatcher
from voice_controller.models import CommandAction, VoiceCommand


def make_cmd(phrases: list[str], key: str = "space") -> VoiceCommand:
    return VoiceCommand(phrases=phrases, action=CommandAction(key=key))


COMMANDS = [
    make_cmd(["next", "next page", "continue"], key="right"),
    make_cmd(["previous", "previous page", "back"], key="left"),
    make_cmd(["zoom in"], key="+"),
    make_cmd(["zoom out"], key="-"),
    make_cmd(["play", "pause"], key="space"),
    make_cmd(["new tab"], key="ctrl"),
]


class TestPhraseMatcher:
    @pytest.fixture
    def matcher(self):
        return PhraseMatcher(COMMANDS)

    def test_exact_match(self, matcher):
        result = matcher.match("next")
        assert result is not None
        assert result.action.key == "right"

    def test_case_insensitive(self, matcher):
        result = matcher.match("NEXT PAGE")
        assert result is not None
        assert result.action.key == "right"

    def test_punctuation_ignored(self, matcher):
        result = matcher.match("next page.")
        assert result is not None
        assert result.action.key == "right"

    def test_extra_whitespace(self, matcher):
        result = matcher.match("next    page")
        assert result is not None
        assert result.action.key == "right"

    def test_alias_match(self, matcher):
        result = matcher.match("continue")
        assert result is not None
        assert result.action.key == "right"

    def test_no_match(self, matcher):
        result = matcher.match("good morning")
        assert result is None

    def test_empty_text(self, matcher):
        result = matcher.match("")
        assert result is None

    def test_only_punctuation(self, matcher):
        result = matcher.match("!@#$%")
        assert result is None

    def test_whitespace_only(self, matcher):
        result = matcher.match("   ")
        assert result is None

    def test_leading_trailing_spaces(self, matcher):
        result = matcher.match("  zoom in  ")
        assert result is not None
        assert result.action.key == "+"

    def test_multiple_matches_returns_first(self):
        # Two commands share some words, first one should win
        cmds = [
            make_cmd(["open door"], key="a"),
            make_cmd(["close door"], key="b"),
        ]
        m = PhraseMatcher(cmds)
        result = m.match("open door")
        assert result is not None
        assert result.action.key == "a"
