"""WarBeacon API client with caching."""

from __future__ import annotations

import logging
from datetime import timezone

import aiohttp
from cachetools import TTLCache

from .config import Config
from .models import BattleReport
from .parsers import parse_killmail_time, related_time_to_iso
from .sides import analyze_killmails, build_battle_report

logger = logging.getLogger(__name__)

# Cache battle reports for 1 hour, max 1000 entries
_br_cache: TTLCache[str, BattleReport] = TTLCache(maxsize=1000, ttl=3600)

USER_AGENT = "BeaconDiscordBRBot/1.0"


async def fetch_related_br(
    session: aiohttp.ClientSession,
    url: str,
    system_id: str,
    related_time: str,
    config: Config,
) -> BattleReport | None:
    """
    Fetch a battle report for a /br/related/<system>/<time> link.

    Args:
        session: The aiohttp client session.
        url: The original WarBeacon URL.
        system_id: The solar system ID.
        related_time: The related time string (YYYYMMDDHHMM).
        config: Bot configuration.

    Returns:
        A BattleReport, or None if fetching/parsing failed.
    """
    if cached := _br_cache.get(url):
        return cached

    api_url = "https://warbeacon.net/api/br/auto"
    middle_time_iso = related_time_to_iso(related_time)

    try:
        async with session.post(
            api_url,
            json={
                "locations": [
                    {
                        "id": int(system_id),
                        "middleTime": middle_time_iso,
                    }
                ]
            },
            headers={
                "User-Agent": USER_AGENT,
                "Referer": url,
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status != 200:
                logger.warning(f"WarBeacon API HTTP {resp.status}")
                return None
            payload = await resp.json(content_type=None)
    except aiohttp.ClientError as e:
        logger.error(f"Network error calling WarBeacon API: {e!r}")
        return None
    except ValueError as e:
        logger.error(f"JSON parsing error from WarBeacon API: {e!r}")
        return None

    if not isinstance(payload, dict) or not payload.get("success"):
        logger.warning("WarBeacon API returned unexpected payload")
        return None

    data = payload.get("data") or {}
    locations = data.get("locations") or []
    system_name = (
        locations[0].get("name", "Unknown System") if locations else "Unknown System"
    )

    analysis = analyze_killmails(data)

    # Build timestamp from middle time
    mid_dt = parse_killmail_time(middle_time_iso)
    if mid_dt:
        mid_dt = mid_dt.astimezone(timezone.utc)
        timestamp_str = f"{mid_dt.month:02d}/{mid_dt.day:02d}/{mid_dt.year:04d}"
    else:
        timestamp_str = "Unknown Date"

    br = build_battle_report(url, system_name, timestamp_str, analysis, config)
    if br:
        _br_cache[url] = br
    return br


async def fetch_report_br(
    session: aiohttp.ClientSession,
    url: str,
    report_id: str,
    config: Config,
) -> BattleReport | None:
    """
    Fetch a battle report for a /br/report/<uuid> link.

    These are combined multi-system reports.

    Args:
        session: The aiohttp client session.
        url: The original WarBeacon URL.
        report_id: The report UUID.
        config: Bot configuration.

    Returns:
        A BattleReport, or None if fetching/parsing failed.
    """
    if cached := _br_cache.get(url):
        return cached

    api_url = f"https://warbeacon.net/api/br/report/{report_id}"

    try:
        async with session.get(
            api_url,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": url,
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status != 200:
                logger.warning(f"WarBeacon Report API HTTP {resp.status}")
                return None
            payload = await resp.json(content_type=None)
    except aiohttp.ClientError as e:
        logger.error(f"Network error calling WarBeacon Report API: {e!r}")
        return None
    except ValueError as e:
        logger.error(f"JSON parsing error from WarBeacon Report API: {e!r}")
        return None

    if not isinstance(payload, dict) or not payload.get("success"):
        logger.warning("WarBeacon Report API returned unexpected payload")
        return None

    data = payload.get("data") or {}
    locations = data.get("locations") or []

    if not locations:
        system_name = "Unknown System"
    elif len(locations) == 1:
        system_name = locations[0].get("name", "Unknown System")
    else:
        system_name = "Multiple Systems"

    analysis = analyze_killmails(data)
    timestamp_str = "Combined Report"

    br = build_battle_report(url, system_name, timestamp_str, analysis, config)
    if br:
        _br_cache[url] = br
    return br
