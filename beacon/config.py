"""Configuration management for the Beacon bot."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def _parse_int_set(value: str) -> set[int]:
    """Parse comma-separated integers into a set, logging invalid values."""
    if not value:
        return set()
    result = set()
    for item in value.split(","):
        if stripped := item.strip():
            try:
                result.add(int(stripped))
            except ValueError:
                logger.warning(f"Invalid integer in config: {stripped}")
    return result


@dataclass(frozen=True)
class Config:
    """Bot configuration loaded from environment variables."""

    bot_token: str
    preferred_alliances: frozenset[int]
    preferred_corps: frozenset[int]
    debug_br: bool

    @classmethod
    def from_env(cls) -> Config:
        """Load configuration from environment variables."""
        return cls(
            bot_token=os.getenv("DISCORD_BOT_TOKEN", ""),
            preferred_alliances=frozenset(
                _parse_int_set(os.getenv("PREFERRED_ALLIANCES", "99010452"))
            ),
            preferred_corps=frozenset(
                _parse_int_set(os.getenv("PREFERRED_CORPS", "98648442"))
            ),
            debug_br=os.getenv("DEBUG_BR", "false").lower() in ("true", "1", "yes"),
        )

    def is_preferred_side_key(self, side_key: str) -> bool:
        """Check if a side key represents a preferred alliance or corp."""
        kind, _, raw = side_key.partition(":")
        try:
            sid = int(raw)
        except ValueError:
            return False
        if kind == "a" and sid in self.preferred_alliances:
            return True
        if kind == "c" and sid in self.preferred_corps:
            return True
        return False


# Match WarBeacon related BR links: /br/related/<system_id>/<timestamp>/
WARBEACON_RELATED_RE = re.compile(
    r"(https?://(?:www\.)?warbeacon\.net/br/related/(\d+)/(\d{12})/?)"
)

# Match WarBeacon report BR links: /br/report/<uuid>/
WARBEACON_REPORT_RE = re.compile(
    r"(https?://(?:www\.)?warbeacon\.net/br/report/([0-9a-fA-F-]+)/?)"
)
