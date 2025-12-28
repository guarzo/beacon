"""Tests for beacon.parsers module."""

from datetime import datetime, timezone

import pytest

from beacon.parsers import coerce_character_id, parse_killmail_time, related_time_to_iso


class TestRelatedTimeToIso:
    """Tests for related_time_to_iso function."""

    def test_converts_valid_time(self):
        result = related_time_to_iso("202512030400")
        assert result == "2025-12-03T04:00:00Z"

    def test_handles_midnight(self):
        result = related_time_to_iso("202501010000")
        assert result == "2025-01-01T00:00:00Z"

    def test_handles_end_of_day(self):
        result = related_time_to_iso("202512312359")
        assert result == "2025-12-31T23:59:00Z"

    def test_raises_on_invalid_format(self):
        with pytest.raises(ValueError):
            related_time_to_iso("invalid")

    def test_raises_on_short_string(self):
        with pytest.raises(ValueError):
            related_time_to_iso("202512")


class TestParseKillmailTime:
    """Tests for parse_killmail_time function."""

    def test_parses_unix_timestamp_int(self):
        timestamp = 1735732800  # 2025-01-01T12:00:00Z
        result = parse_killmail_time(timestamp)
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2025

    def test_parses_unix_timestamp_float(self):
        timestamp = 1735732800.5
        result = parse_killmail_time(timestamp)
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_parses_iso_string_with_z(self):
        result = parse_killmail_time("2025-01-01T12:00:00Z")
        assert result is not None
        assert result == datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def test_parses_iso_string_without_z(self):
        result = parse_killmail_time("2025-01-01T12:00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc
        assert result.year == 2025

    def test_parses_iso_string_with_offset(self):
        result = parse_killmail_time("2025-01-01T12:00:00+00:00")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_returns_none_for_empty_string(self):
        assert parse_killmail_time("") is None
        assert parse_killmail_time("   ") is None

    def test_returns_none_for_invalid_string(self):
        assert parse_killmail_time("not-a-time") is None

    def test_returns_none_for_none(self):
        assert parse_killmail_time(None) is None

    def test_returns_none_for_invalid_type(self):
        assert parse_killmail_time([]) is None
        assert parse_killmail_time({}) is None

    def test_handles_overflow_timestamp(self):
        # Very large timestamp that would overflow
        result = parse_killmail_time(99999999999999999)
        assert result is None


class TestCoerceCharacterId:
    """Tests for coerce_character_id function."""

    def test_returns_int_unchanged(self):
        assert coerce_character_id(12345) == 12345

    def test_converts_string_to_int(self):
        assert coerce_character_id("12345") == 12345

    def test_converts_float_to_int(self):
        assert coerce_character_id(12345.0) == 12345

    def test_returns_none_for_none(self):
        assert coerce_character_id(None) is None

    def test_returns_none_for_invalid_string(self):
        assert coerce_character_id("abc") is None

    def test_returns_none_for_invalid_type(self):
        assert coerce_character_id([]) is None
        assert coerce_character_id({}) is None

    def test_handles_negative_id(self):
        assert coerce_character_id(-123) == -123

    def test_handles_zero(self):
        assert coerce_character_id(0) == 0
