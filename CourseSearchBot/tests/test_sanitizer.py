"""
tests/test_sanitizer.py
Basic sanity tests for the security layer.
Run with: pytest tests/
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from security.sanitizer import InputSanitizer, SanitizationError


def test_clean_query_passes():
    assert InputSanitizer.sanitize_query("what is photosynthesis") == "what is photosynthesis"


def test_control_chars_stripped():
    result = InputSanitizer.sanitize_query("hello\x00world\x1f")
    assert "\x00" not in result
    assert "\x1f" not in result


def test_whitespace_normalized():
    result = InputSanitizer.sanitize_query("  too   many   spaces  ")
    assert result == "too many spaces"


def test_empty_query_raises():
    with pytest.raises(SanitizationError):
        InputSanitizer.sanitize_query("   ")


def test_too_long_query_raises():
    with pytest.raises(SanitizationError):
        InputSanitizer.sanitize_query("a" * 501)


def test_non_string_raises():
    with pytest.raises(SanitizationError):
        InputSanitizer.sanitize_query(12345)
