import logging
import os
import re
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

import aiohttp
import discord
from discord.ext import commands

# =========================
# LOGGING
# =========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# =========================
# CONFIG
# =========================


def _parse_int_set(value: str) -> set[int]:
    """Parse comma-separated integers into a set."""
    if not value:
        return set()
    result = set()
    for item in value.split(","):
        item = item.strip()
        if item:
            try:
                result.add(int(item))
            except ValueError:
                logger.warning("Invalid integer in config: %s", item)
    return result


BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Preferred alliances/corps for "home team" detection
# Comma-separated IDs, e.g., "99010452,99010453"
PREFERRED_ALLIANCES = _parse_int_set(os.getenv("PREFERRED_ALLIANCES", "99010452"))
PREFERRED_CORPS = _parse_int_set(os.getenv("PREFERRED_CORPS", "98648442"))

DEBUG_BR = os.getenv("DEBUG_BR", "false").lower() in ("true", "1", "yes")

# Set debug log level if DEBUG_BR is enabled
if DEBUG_BR:
    logging.getLogger().setLevel(logging.DEBUG)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Match WarBeacon related BR links
WARBEACON_RELATED_RE = re.compile(
    r"(https?://(?:www\.)?warbeacon\.net/br/related/(\d+)/(\d{12})/?)"
)

# Match WarBeacon report BR links (multi-system combined reports)
WARBEACON_REPORT_RE = re.compile(
    r"(https?://(?:www\.)?warbeacon\.net/br/report/([0-9a-fA-F-]+)/?)"
)

# Cache: url -> BR dict
br_cache: Dict[str, Dict[str, Any]] = {}


# =========================
# Basic test command
# =========================


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send("pong")


# =========================
# Formatting helpers
# =========================


def format_isk_short(value: float) -> str:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "N/A"
    if v >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}b"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}m"
    if v >= 1_000:
        return f"{v / 1_000:.1f}k"
    return str(int(v))


def make_ratio_bar(a_isk: float, b_isk: float, length: int = 20) -> str:
    """
    Text bar like `▰▰▰▰▰▱▱▱` based on ISK lost.

    If it's a full wipe (one side 0, other > 0) show all ▱ to signal
    that one side took no losses.
    """
    total = a_isk + b_isk
    if total <= 0:
        return "`" + "▱" * length + "`"
    if (a_isk == 0 and b_isk > 0) or (b_isk == 0 and a_isk > 0):
        return "`" + "▱" * length + "`"
    a_ratio = a_isk / total
    a_blocks = int(round(a_ratio * length))
    a_blocks = max(1, min(length - 1, a_blocks))
    b_blocks = length - a_blocks
    bar = "▰" * a_blocks + "▱" * b_blocks
    return f"`{bar}`"


def related_time_to_iso(related_time: str) -> str:
    """
    Convert WarBeacon relatedTime like '202512030400'
    into ISO8601: '2025-12-03T04:00:00Z'
    """
    year = int(related_time[0:4])
    month = int(related_time[4:6])
    day = int(related_time[6:8])
    hour = int(related_time[8:10])
    minute = int(related_time[10:12])
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00Z"


def parse_killmail_time(value: Any) -> Optional[datetime]:
    """
    Parse a killmail time into a UTC datetime.

    Handles:
    - ISO strings, with or without 'Z'
    - Unix timestamps (int/float, seconds since epoch)
    """
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except Exception:
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
    except Exception:
        return None


# =========================
# Side helpers
# =========================


def _side_key_for_entity(ent: Dict[str, Any]) -> str:
    """
    Prefer alliance_id, then corp_id, then character_id.
    Encoded as "a:<id>", "c:<id>", "p:<id>".
    """
    alliance_id = ent.get("alliance_id")
    corp_id = ent.get("corporation_id")
    char_id = ent.get("character_id")
    if alliance_id is not None:
        return "a:%s" % alliance_id
    if corp_id is not None:
        return "c:%s" % corp_id
    if char_id is not None:
        return "p:%s" % char_id
    return "unknown"


def _build_side_label(side_key: str, names: Dict[str, Any]) -> str:
    entities = names.get("entities", {}) or {}
    tickers = names.get("tickers", {}) or {}
    raw = side_key.split(":", 1)[1]
    try:
        num_id = int(raw)
    except ValueError:
        return "Unknown"
    name = entities.get(str(num_id))
    ticker = tickers.get(str(num_id))
    if ticker:
        return ticker
    if name:
        return name
    return "ID %d" % num_id


def _is_preferred_side_key(side_key: str) -> bool:
    kind, _, raw = side_key.partition(":")
    try:
        sid = int(raw)
    except ValueError:
        return False
    if kind == "a" and sid in PREFERRED_ALLIANCES:
        return True
    if kind == "c" and sid in PREFERRED_CORPS:
        return True
    return False


def _coerce_char_id(char_id: Any) -> Optional[int]:
    if char_id is None:
        return None
    try:
        return int(char_id)
    except (TypeError, ValueError):
        return None


def make_label_with_count(side: Dict[str, Any]) -> str:
    count = len(side.get("pilots", []))
    return "%s (%d)" % (side["label"], count)


# =========================
# Compute sides + kill/assist graphs
# =========================


def compute_sides_from_warbeacon_data(
    data: Dict[str, Any],
) -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, float]],
    Dict[str, Dict[str, int]],
    Dict[str, Dict[str, int]],
]:
    """
    Returns:
      sides_list
      killers_of_side[victim_side][killer_side] = ISK
      kills_by_side[killer_side][victim_side] = ISK
      assists_on_side[victim_side][attacker_side] = count (on killmail as attacker)
      assists_by_side[attacker_side][victim_side] = count
    """
    killmails = data.get("killmails") or []
    names = data.get("names") or {}

    side_stats: Dict[str, Dict[str, Any]] = {}
    killers_of_side: Dict[str, Dict[str, float]] = {}
    kills_by_side: Dict[str, Dict[str, float]] = {}
    assists_on_side: Dict[str, Dict[str, int]] = {}
    assists_by_side: Dict[str, Dict[str, int]] = {}

    def ensure_side(key: str) -> Dict[str, Any]:
        if key not in side_stats:
            side_stats[key] = {
                "key": key,
                "label": _build_side_label(key, names),
                "isk_lost": 0.0,
                "ships_lost": 0,
                "isk_destroyed": 0.0,
                "ships_destroyed": 0,
                "pilots": set(),
            }
        return side_stats[key]

    def add_kill_relation(victim_key: str, killer_key: str, value: float) -> None:
        if victim_key not in killers_of_side:
            killers_of_side[victim_key] = {}
        killers_of_side[victim_key][killer_key] = (
            killers_of_side[victim_key].get(killer_key, 0.0) + value
        )
        if killer_key not in kills_by_side:
            kills_by_side[killer_key] = {}
        kills_by_side[killer_key][victim_key] = (
            kills_by_side[killer_key].get(victim_key, 0.0) + value
        )

    def add_assist_relation(victim_key: str, attacker_key: str) -> None:
        # victim_key was killed; attacker_key appeared as attacker (even 0 dmg)
        if victim_key not in assists_on_side:
            assists_on_side[victim_key] = {}
        assists_on_side[victim_key][attacker_key] = (
            assists_on_side[victim_key].get(attacker_key, 0) + 1
        )
        if attacker_key not in assists_by_side:
            assists_by_side[attacker_key] = {}
        assists_by_side[attacker_key][victim_key] = (
            assists_by_side[attacker_key].get(victim_key, 0) + 1
        )

    for km in killmails:
        val = float(km.get("total_value", 0.0))

        # Victim block
        victim = km.get("victim") or {}
        v_key = _side_key_for_entity(victim)
        v_side = ensure_side(v_key)
        v_side["isk_lost"] += val
        v_side["ships_lost"] += 1
        v_char_id = _coerce_char_id(victim.get("character_id"))
        if v_char_id is not None:
            v_side["pilots"].add(v_char_id)

        # Attackers
        attackers = km.get("attackers") or []
        if not attackers:
            continue

        per_side: Dict[str, Dict[str, Any]] = {}
        for atk in attackers:
            a_key = _side_key_for_entity(atk)
            a_side = ensure_side(a_key)

            a_char_id = _coerce_char_id(atk.get("character_id"))
            if a_char_id is not None:
                a_side["pilots"].add(a_char_id)

            if a_key not in per_side:
                per_side[a_key] = {"count": 0, "damage": 0.0, "final_blow": False}
            per_side[a_key]["count"] += 1
            dmg = atk.get("damage_done")
            if isinstance(dmg, (int, float)):
                per_side[a_key]["damage"] += float(dmg)
            if atk.get("final_blow"):
                per_side[a_key]["final_blow"] = True

        # Any attacker side on this kill is "engaged" with the victim side,
        # even if they did 0 damage (ewar, tackle, etc.).
        for a_key in per_side.keys():
            if a_key != v_key:
                add_assist_relation(v_key, a_key)

        # Determine which side actually gets credit for the kill
        killing_side_key: Optional[str] = None
        fb_candidates = [k for k, s in per_side.items() if s["final_blow"]]
        if fb_candidates:
            killing_side_key = fb_candidates[0]
        else:
            max_damage = max((s["damage"] for s in per_side.values()), default=0.0)
            if max_damage > 0:
                for k, s in per_side.items():
                    if s["damage"] == max_damage:
                        killing_side_key = k
                        break
            else:
                max_count = max((s["count"] for s in per_side.values()), default=0)
                for k, s in per_side.items():
                    if s["count"] == max_count:
                        killing_side_key = k
                        break

        if killing_side_key is not None:
            a_side = ensure_side(killing_side_key)
            a_side["isk_destroyed"] += val
            a_side["ships_destroyed"] += 1
            add_kill_relation(v_key, killing_side_key, val)

    sides_list = list(side_stats.values())
    sides_list.sort(
        key=lambda s: (s["isk_lost"], s["isk_destroyed"]),
        reverse=True,
    )

    return sides_list, killers_of_side, kills_by_side, assists_on_side, assists_by_side


# =========================
# Shared BR builder from sides
# =========================


def build_br_from_sides(
    wb_url: str,
    system_name: str,
    timestamp_str: str,
    sides: List[Dict[str, Any]],
    killers_of_side: Dict[str, Dict[str, float]],
    kills_by_side: Dict[str, Dict[str, float]],
    assists_on_side: Dict[str, Dict[str, int]],
    assists_by_side: Dict[str, Dict[str, int]],
) -> Optional[Dict[str, Any]]:
    if not sides:
        logger.warning("No sides computed from WarBeacon data")
        return None

    if DEBUG_BR:
        logger.debug("=== RAW SIDES FROM WARBEACON ===")
        for s in sides:
            logger.debug(
                " side_key=%-10s label=%-10s pilots=%2d isk_lost=%.1f isk_destroyed=%.1f",
                s["key"],
                s["label"],
                len(s.get("pilots", [])),
                s["isk_lost"],
                s["isk_destroyed"],
            )
        logger.debug("================================")

    total_isk_lost_raw = sum(s["isk_lost"] for s in sides)
    total_ships_lost_raw = sum(s["ships_lost"] for s in sides)

    # =========================
    # Preferred side present (Zoo)
    # =========================

    preferred_sides = [s for s in sides if _is_preferred_side_key(s["key"])]

    if preferred_sides:
        preferred_keys = {s["key"] for s in preferred_sides}

        pref_pilots = set()
        pref_isk_lost = 0.0
        pref_ships_lost = 0
        pref_isk_destroyed = 0.0
        pref_ships_destroyed = 0

        for s in preferred_sides:
            pref_isk_lost += s["isk_lost"]
            pref_ships_lost += s["ships_lost"]
            pref_isk_destroyed += s["isk_destroyed"]
            pref_ships_destroyed += s["ships_destroyed"]
            pref_pilots.update(s.get("pilots", set()))

        preferred_team = {
            "key": "preferred",
            "label": preferred_sides[0]["label"],
            "isk_lost": pref_isk_lost,
            "ships_lost": pref_ships_lost,
            "isk_destroyed": pref_isk_destroyed,
            "ships_destroyed": pref_ships_destroyed,
            "pilots": pref_pilots,
        }

        enemy_candidates = [s for s in sides if s["key"] not in preferred_keys]

        enemy_seed: Optional[Dict[str, Any]] = None
        best_engagement_with_pref = -1.0

        # Pick the enemy seed as the side most engaged with preferred side (kills + assists)
        for s in enemy_candidates:
            s_key = s["key"]
            killers = killers_of_side.get(s_key, {})
            kills_map = kills_by_side.get(s_key, {})
            assists_on = assists_on_side.get(s_key, {})
            assists_by = assists_by_side.get(s_key, {})

            killed_by_pref = sum(killers.get(pk, 0.0) for pk in preferred_keys)
            kills_pref = sum(kills_map.get(pk, 0.0) for pk in preferred_keys)

            assist_with_pref = 0
            for pk in preferred_keys:
                assist_with_pref += assists_on.get(pk, 0)
                assist_with_pref += assists_by.get(pk, 0)

            engage_with_pref = killed_by_pref + kills_pref + assist_with_pref

            if engage_with_pref > best_engagement_with_pref:
                best_engagement_with_pref = engage_with_pref
                enemy_seed = s

        if enemy_seed is None and enemy_candidates:
            enemy_seed = max(
                enemy_candidates,
                key=lambda s: (s["isk_lost"] + s["isk_destroyed"]),
            )

        if enemy_seed is not None:
            enemy_key = enemy_seed["key"]

            enemy_team = {
                "key": enemy_key,
                "label": enemy_seed["label"],
                "isk_lost": enemy_seed["isk_lost"],
                "ships_lost": enemy_seed["ships_lost"],
                "isk_destroyed": enemy_seed["isk_destroyed"],
                "ships_destroyed": enemy_seed["ships_destroyed"],
                "pilots": set(enemy_seed.get("pilots", set())),
            }

            # Merge third parties based on engagement with preferred vs enemy
            for s in enemy_candidates:
                if s["key"] == enemy_key:
                    continue

                s_key = s["key"]
                killers = killers_of_side.get(s_key, {})
                kills_map = kills_by_side.get(s_key, {})
                assists_on = assists_on_side.get(s_key, {})
                assists_by = assists_by_side.get(s_key, {})

                killed_by_pref = sum(killers.get(pk, 0.0) for pk in preferred_keys)
                kills_pref = sum(kills_map.get(pk, 0.0) for pk in preferred_keys)

                killed_by_enemy = killers.get(enemy_key, 0.0)
                kills_enemy = kills_map.get(enemy_key, 0.0)

                assist_vs_pref = 0
                for pk in preferred_keys:
                    assist_vs_pref += assists_on.get(pk, 0)
                    assist_vs_pref += assists_by.get(pk, 0)

                assist_vs_enemy = assists_on.get(enemy_key, 0) + assists_by.get(
                    enemy_key, 0
                )

                engage_with_pref = killed_by_pref + kills_pref + assist_vs_pref
                engage_with_enemy = killed_by_enemy + kills_enemy + assist_vs_enemy

                # If this side ONLY engages enemy -> ally of preferred
                if engage_with_enemy > 0 and engage_with_pref == 0:
                    preferred_team["isk_lost"] += s["isk_lost"]
                    preferred_team["ships_lost"] += s["ships_lost"]
                    preferred_team["isk_destroyed"] += s["isk_destroyed"]
                    preferred_team["ships_destroyed"] += s["ships_destroyed"]
                    preferred_team["pilots"].update(s.get("pilots", set()))
                # If this side ONLY engages preferred -> ally of enemy
                elif engage_with_pref > 0 and engage_with_enemy == 0:
                    enemy_team["isk_lost"] += s["isk_lost"]
                    enemy_team["ships_lost"] += s["ships_lost"]
                    enemy_team["isk_destroyed"] += s["isk_destroyed"]
                    enemy_team["ships_destroyed"] += s["ships_destroyed"]
                    enemy_team["pilots"].update(s.get("pilots", set()))
                # Otherwise, 3rd party

        else:
            enemy_team = {
                "key": "none",
                "label": "No Opponent",
                "isk_lost": 0.0,
                "ships_lost": 0,
                "isk_destroyed": 0.0,
                "ships_destroyed": 0,
                "pilots": set(),
            }

        attackers_side = preferred_team
        defenders_side = enemy_team

        if attackers_side["isk_lost"] < defenders_side["isk_lost"]:
            winner = "preferred_win"
            color_tag = "green"
        elif attackers_side["isk_lost"] > defenders_side["isk_lost"]:
            winner = "preferred_loss"
            color_tag = "red"
        else:
            winner = "tie"
            color_tag = "grey"

    else:
        # =========================
        # Neutral BR
        # =========================

        sorted_by_involvement = sorted(
            sides,
            key=lambda s: (s["isk_lost"] + s["isk_destroyed"]),
            reverse=True,
        )

        side1 = sorted_by_involvement[0]
        if len(sorted_by_involvement) > 1:
            side2 = sorted_by_involvement[1]
        else:
            side2 = {
                "key": "none",
                "label": "No Opponent",
                "isk_lost": 0.0,
                "ships_lost": 0,
                "isk_destroyed": 0.0,
                "ships_destroyed": 0,
                "pilots": set(),
            }

        side1_key = side1["key"]
        side2_key = side2["key"]

        teamA = {
            "key": side1_key,
            "label": side1["label"],
            "isk_lost": side1["isk_lost"],
            "ships_lost": side1["ships_lost"],
            "isk_destroyed": side1["isk_destroyed"],
            "ships_destroyed": side1["ships_destroyed"],
            "pilots": set(side1.get("pilots", set())),
        }
        teamB = {
            "key": side2_key,
            "label": side2["label"],
            "isk_lost": side2["isk_lost"],
            "ships_lost": side2["ships_lost"],
            "isk_destroyed": side2["isk_destroyed"],
            "ships_destroyed": side2["ships_destroyed"],
            "pilots": set(side2.get("pilots", set())),
        }

        # Merge other sides based on engagement with side1 vs side2
        for s in sides:
            s_key = s["key"]
            if s_key in (side1_key, side2_key):
                continue

            killers = killers_of_side.get(s_key, {})
            kills_map = kills_by_side.get(s_key, {})
            assists_on = assists_on_side.get(s_key, {})
            assists_by = assists_by_side.get(s_key, {})

            killed_by_1 = killers.get(side1_key, 0.0)
            killed_by_2 = killers.get(side2_key, 0.0)

            kills_1 = kills_map.get(side1_key, 0.0)
            kills_2 = kills_map.get(side2_key, 0.0)

            assist_vs_1 = assists_on.get(side1_key, 0) + assists_by.get(side1_key, 0)
            assist_vs_2 = assists_on.get(side2_key, 0) + assists_by.get(side2_key, 0)

            engage_with_1 = killed_by_1 + kills_1 + assist_vs_1
            engage_with_2 = killed_by_2 + kills_2 + assist_vs_2

            if engage_with_1 > 0 and engage_with_2 == 0:
                teamB["isk_lost"] += s["isk_lost"]
                teamB["ships_lost"] += s["ships_lost"]
                teamB["isk_destroyed"] += s["isk_destroyed"]
                teamB["ships_destroyed"] += s["ships_destroyed"]
                teamB["pilots"].update(s.get("pilots", set()))
            elif engage_with_2 > 0 and engage_with_1 == 0:
                teamA["isk_lost"] += s["isk_lost"]
                teamA["ships_lost"] += s["ships_lost"]
                teamA["isk_destroyed"] += s["isk_destroyed"]
                teamA["ships_destroyed"] += s["ships_destroyed"]
                teamA["pilots"].update(s.get("pilots", set()))
            # else: 3rd party

        if teamA["isk_lost"] <= teamB["isk_lost"]:
            attackers_side = teamA
            defenders_side = teamB
        else:
            attackers_side = teamB
            defenders_side = teamA

        winner = "neutral"
        color_tag = (
            "green"
            if attackers_side["isk_lost"] != defenders_side["isk_lost"]
            else "grey"
        )

    # =========================
    # Final pilot sets, BR object
    # =========================

    atk_pilots_set = set(attackers_side.get("pilots", set()))
    dfn_pilots_set = set(defenders_side.get("pilots", set()))
    total_pilot_ids = atk_pilots_set | dfn_pilots_set

    if DEBUG_BR:
        logger.debug("=== FINAL TEAMS ===")
        logger.debug(
            " Attackers: %-10s pilots=%2d ids=%s",
            attackers_side["label"],
            len(atk_pilots_set),
            sorted(list(atk_pilots_set)),
        )
        logger.debug(
            " Defenders: %-10s pilots=%2d ids=%s",
            defenders_side["label"],
            len(dfn_pilots_set),
            sorted(list(dfn_pilots_set)),
        )
        logger.debug(" Total unique pilots counted: %d", len(total_pilot_ids))
        logger.debug("====================")

    attackers = {
        "name": attackers_side["label"],
        "label_with_count": make_label_with_count(attackers_side),
        "pilot_count": len(atk_pilots_set),
        "isk_lost": attackers_side["isk_lost"],
        "ships_lost": attackers_side["ships_lost"],
        "isk_destroyed": attackers_side["isk_destroyed"],
        "ships_destroyed": attackers_side["ships_destroyed"],
    }
    defenders = {
        "name": defenders_side["label"],
        "label_with_count": make_label_with_count(defenders_side),
        "pilot_count": len(dfn_pilots_set),
        "isk_lost": defenders_side["isk_lost"],
        "ships_lost": defenders_side["ships_lost"],
        "isk_destroyed": defenders_side["isk_destroyed"],
        "ships_destroyed": defenders_side["ships_destroyed"],
    }

    br = {
        "url": wb_url,
        "system_name": system_name,
        "timestamp": timestamp_str,
        "total_isk": float(total_isk_lost_raw),
        "total_kills": int(total_ships_lost_raw),
        "total_pilots": len(total_pilot_ids),
        "attackers": attackers,
        "defenders": defenders,
        "winner": winner,
        "color": color_tag,
    }
    return br


# =========================
# WarBeacon BR fetchers
# =========================


async def fetch_warbeacon_br(
    session: aiohttp.ClientSession,
    wb_url: str,
    system_id: str,
    related_time: str,
) -> Dict[str, Any] | None:
    """
    For /br/related/<system>/<time> links.
    """
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
                "User-Agent": "BeaconDiscordBRBot/1.0",
                "Referer": wb_url,
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status != 200:
                logger.warning("WarBeacon API HTTP %d", resp.status)
                return None
            payload = await resp.json(content_type=None)
    except Exception as e:
        logger.error("Error calling WarBeacon API: %r", e)
        return None

    if not isinstance(payload, dict) or not payload.get("success"):
        logger.warning("WarBeacon API returned unexpected payload")
        return None

    data = payload.get("data") or {}
    locations = data.get("locations") or []
    system_name = "Unknown System"

    if locations:
        loc = locations[0]
        system_name = loc.get("name") or system_name

    (
        sides,
        killers_of_side,
        kills_by_side,
        assists_on_side,
        assists_by_side,
    ) = compute_sides_from_warbeacon_data(data)

    # Build timestamp label from the middle time we used
    mid_dt = parse_killmail_time(middle_time_iso)
    if mid_dt:
        mid_dt = mid_dt.astimezone(timezone.utc)
        date_str = "%02d/%02d/%04d" % (mid_dt.month, mid_dt.day, mid_dt.year)
    else:
        date_str = "Unknown Date"

    timestamp_str = date_str

    return build_br_from_sides(
        wb_url,
        system_name,
        timestamp_str,
        sides,
        killers_of_side,
        kills_by_side,
        assists_on_side,
        assists_by_side,
    )


async def fetch_warbeacon_br_report(
    session: aiohttp.ClientSession,
    wb_url: str,
    report_id: str,
) -> Dict[str, Any] | None:
    """
    For /br/report/<uuid> links (combined multi-system reports).
    Assumes WarBeacon exposes a matching report API endpoint that
    returns the same 'data' structure as /api/br/auto.
    """
    api_url = f"https://warbeacon.net/api/br/report/{report_id}"

    try:
        async with session.get(
            api_url,
            headers={
                "User-Agent": "BeaconDiscordBRBot/1.0",
                "Referer": wb_url,
                "Accept": "application/json",
            },
        ) as resp:
            if resp.status != 200:
                logger.warning("WarBeacon Report API HTTP %d", resp.status)
                return None
            payload = await resp.json(content_type=None)
    except Exception as e:
        logger.error("Error calling WarBeacon Report API: %r", e)
        return None

    if not isinstance(payload, dict) or not payload.get("success"):
        logger.warning("WarBeacon Report API returned unexpected payload")
        return None

    data = payload.get("data") or {}
    locations = data.get("locations") or []
    system_name = "Unknown System"

    # For combined reports, there may be multiple systems.
    # We don't need to count them; just name it sensibly.
    if locations:
        if len(locations) == 1:
            loc = locations[0]
            system_name = loc.get("name") or system_name
        else:
            system_name = "Multiple Systems"

    (
        sides,
        killers_of_side,
        kills_by_side,
        assists_on_side,
        assists_by_side,
    ) = compute_sides_from_warbeacon_data(data)

    # No single "middle time" here; just label it as a combined report.
    timestamp_str = "Combined Report"

    return build_br_from_sides(
        wb_url,
        system_name,
        timestamp_str,
        sides,
        killers_of_side,
        kills_by_side,
        assists_on_side,
        assists_by_side,
    )


# =========================
# Embed builder
# =========================


def build_br_embed(br: Dict[str, Any]) -> discord.Embed:
    url = br["url"]
    system = br.get("system_name", "Unknown System")
    timestamp = br.get("timestamp", "Unknown Time")

    total_isk = br.get("total_isk", 0.0)
    total_kills = br.get("total_kills", 0)
    total_pilots = br.get("total_pilots", None)

    atk = br.get("attackers")
    dfn = br.get("defenders")

    # ----- Color selection -----
    color_tag = br.get("color", "grey")
    if color_tag == "green":
        color = discord.Color.green()
    elif color_tag == "red":
        color = discord.Color.red()
    else:
        color = discord.Color.dark_grey()

    # ----- Embed -----
    embed = discord.Embed(
        title=f"🛰️  Battle Report — {system}",
        url=url,
        color=color,
    )

    # ===== Description Block =====
    desc = []
    desc.append(f"{timestamp}")
    desc.append("━━━━━━━━━━━━━━━━━━")

    embed.description = "\n".join(desc)

    # ===== ISK Loss Split =====
    if atk and dfn:
        ratio_bar = make_ratio_bar(atk["isk_lost"], dfn["isk_lost"])

        split_text = (
            "**{atk}** vs **{dfn}**\n{bar}\n{atk_isk} vs {dfn_isk} ISK lost"
        ).format(
            atk=atk["label_with_count"],
            dfn=dfn["label_with_count"],
            bar=ratio_bar,
            atk_isk=format_isk_short(atk["isk_lost"]),
            dfn_isk=format_isk_short(dfn["isk_lost"]),
        )

        embed.add_field(
            name="ISK Loss Split",
            value=split_text + "\n--------------------",
            inline=False,
        )

    # ===== Totals =====
    totals_text = (
        f"• **ISK lost:** {format_isk_short(total_isk)}\n"
        f"• **Ships lost:** {total_kills}\n"
    )

    if total_pilots is not None:
        totals_text += f"• **Pilots:** {total_pilots}\n"

    embed.add_field(
        name="📊 Totals",
        value=totals_text + "━━━━━━━━━━━━━━━━━━",
        inline=False,
    )

    # ===== Attackers (Left Side) =====
    if atk:
        atk_text = (
            f"• **ISK lost:** {format_isk_short(atk['isk_lost'])}\n"
            f"• **Ships lost:** {atk['ships_lost']}\n"
            f"• **ISK destroyed:** {format_isk_short(atk['isk_destroyed'])}\n"
            f"• **Ships destroyed:** {atk['ships_destroyed']}"
        )
        embed.add_field(
            name=f"🟪 {atk['label_with_count']}",
            value=atk_text,
            inline=True,
        )

    # ===== Defenders (Right Side) =====
    if dfn:
        dfn_text = (
            f"• **ISK lost:** {format_isk_short(dfn['isk_lost'])}\n"
            f"• **Ships lost:** {dfn['ships_lost']}\n"
            f"• **ISK destroyed:** {format_isk_short(dfn['isk_destroyed'])}\n"
            f"• **Ships destroyed:** {dfn['ships_destroyed']}"
        )
        embed.add_field(
            name=f"🟥 {dfn['label_with_count']}",
            value=dfn_text,
            inline=True,
        )

    return embed


# =========================
# Bot events
# =========================


@bot.event
async def on_ready():
    logger.info("Logged in as %s (id: %d)", bot.user, bot.user.id)


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content or ""

    # Try matching /related first
    match_related = WARBEACON_RELATED_RE.search(content)
    match_report = None if match_related else WARBEACON_REPORT_RE.search(content)

    br = None
    wb_url = None

    if match_related:
        wb_url, system_id, related_time = (
            match_related.group(1),
            match_related.group(2),
            match_related.group(3),
        )

        if wb_url in br_cache:
            br = br_cache[wb_url]
        else:
            async with aiohttp.ClientSession() as session:
                br = await fetch_warbeacon_br(session, wb_url, system_id, related_time)
            if br is not None:
                br_cache[wb_url] = br

    elif match_report:
        wb_url, report_id = match_report.group(1), match_report.group(2)

        if wb_url in br_cache:
            br = br_cache[wb_url]
        else:
            async with aiohttp.ClientSession() as session:
                br = await fetch_warbeacon_br_report(session, wb_url, report_id)
            if br is not None:
                br_cache[wb_url] = br

    sent_embed = False

    if br is not None:
        embed = build_br_embed(br)
        await message.channel.send(embed=embed)
        sent_embed = True

    # Try to delete the original message if we posted an embed
    if sent_embed:
        try:
            await message.delete()
        except discord.Forbidden:
            logger.warning("Missing permissions to delete message")
        except discord.HTTPException as e:
            logger.warning("Failed to delete message: %s", e)

    await bot.process_commands(message)


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise RuntimeError(
            "DISCORD_BOT_TOKEN environment variable is required. "
            "Set it in your .env file or environment."
        )
    bot.run(BOT_TOKEN)
