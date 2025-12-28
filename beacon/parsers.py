"""Time and data parsing utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def related_time_to_iso(related_time: str) -> str:
    """
    Convert WarBeacon relatedTime like '202512030400' into ISO8601.

    Args:
        related_time: A 12-digit string in format YYYYMMDDHHMM.

    Returns:
        ISO8601 formatted string like '2025-12-03T04:00:00Z'.
    """
    dt = datetime.strptime(related_time, "%Y%m%d%H%M")
    return dt.strftime("%Y-%m-%dT%H:%M:00Z")


def parse_killmail_time(value: Any) -> datetime | None:
    """
    Parse a killmail time into a UTC datetime.

    Handles:
        - ISO strings, with or without 'Z' suffix.
        - Unix timestamps (int/float, seconds since epoch).

    Args:
        value: The time value to parse.

    Returns:
        A timezone-aware UTC datetime, or None if parsing fails.
    """
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None

    if not isinstance(value, str):
        return None

    s = value.strip()
    if not s:
        return None

    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except ValueError:
        return None


def coerce_character_id(char_id: Any) -> int | None:
    """
    Coerce a character ID to an integer.

    Args:
        char_id: The character ID to convert.

    Returns:
        The integer character ID, or None if conversion fails.
    """
    if char_id is None:
        return None
    try:
        return int(char_id)
    except (TypeError, ValueError):
        return None
