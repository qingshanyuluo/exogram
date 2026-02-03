"""Tests for exogram.utils module."""
from __future__ import annotations

import pytest

from exogram.utils import get_logger, normalize_text, safe_preview_value


class TestNormalizeText:
    """Tests for normalize_text function."""

    def test_strips_whitespace(self):
        assert normalize_text("  hello  ") == "hello"

    def test_collapses_multiple_spaces(self):
        assert normalize_text("hello   world") == "hello world"

    def test_handles_newlines_and_tabs(self):
        assert normalize_text("hello\n\tworld") == "hello world"

    def test_empty_string(self):
        assert normalize_text("") == ""

    def test_already_normalized(self):
        assert normalize_text("hello world") == "hello world"


class TestSafePreviewValue:
    """Tests for safe_preview_value function."""

    def test_returns_none_for_none(self):
        assert safe_preview_value(None) is None

    def test_short_value_unchanged(self):
        assert safe_preview_value("short text") == "short text"

    def test_truncates_long_value(self):
        long_text = "x" * 100
        result = safe_preview_value(long_text, limit=50)
        assert len(result) == 51  # 50 chars + ellipsis
        assert result.endswith("…")

    def test_custom_limit(self):
        text = "hello world"
        result = safe_preview_value(text, limit=5)
        assert result == "hello…"

    def test_normalizes_whitespace(self):
        result = safe_preview_value("  hello   world  ")
        assert result == "hello world"


class TestGetLogger:
    """Tests for get_logger function."""

    def test_returns_logger(self):
        logger = get_logger("test")
        assert logger is not None
        assert logger.name == "test"

    def test_same_name_returns_same_logger(self):
        logger1 = get_logger("same_name")
        logger2 = get_logger("same_name")
        assert logger1 is logger2

    def test_different_names_return_different_loggers(self):
        logger1 = get_logger("name1")
        logger2 = get_logger("name2")
        assert logger1 is not logger2
