"""Side computation and battle report building logic."""

from __future__ import annotations

import logging
from typing import Any

from .config import Config
from .models import BattleReport, SideAnalysis, SideStats, TeamStats
from .parsers import coerce_character_id

logger = logging.getLogger(__name__)


def _side_key_for_entity(entity: dict[str, Any]) -> str:
    """
    Determine the side key for an entity (victim or attacker).

    Prefers alliance_id, then corporation_id, then character_id.
    Encoded as 'a:<id>', 'c:<id>', or 'p:<id>'.
    """
    if (alliance_id := entity.get("alliance_id")) is not None:
        return f"a:{alliance_id}"
    if (corp_id := entity.get("corporation_id")) is not None:
        return f"c:{corp_id}"
    if (char_id := entity.get("character_id")) is not None:
        return f"p:{char_id}"
    return "unknown"


def _build_side_label(side_key: str, names: dict[str, Any]) -> str:
    """Build a human-readable label for a side from the names data."""
    entities = names.get("entities", {}) or {}
    tickers = names.get("tickers", {}) or {}

    _, _, raw = side_key.partition(":")
    try:
        num_id = int(raw)
    except ValueError:
        return "Unknown"

    str_id = str(num_id)
    if ticker := tickers.get(str_id):
        return ticker
    if name := entities.get(str_id):
        return name
    return f"ID {num_id}"


def analyze_killmails(data: dict[str, Any]) -> SideAnalysis:
    """
    Analyze killmails to determine sides and their relationships.

    This processes all killmails in the data to determine:
    - Which sides exist (alliances/corps/characters)
    - Kill/death relationships between sides
    - Assist relationships (who appeared on whose killmails)

    Args:
        data: The WarBeacon API response data.

    Returns:
        A SideAnalysis containing all computed side information.
    """
    killmails = data.get("killmails") or []
    names = data.get("names") or {}

    side_stats: dict[str, SideStats] = {}
    analysis = SideAnalysis(sides=[])

    def ensure_side(key: str) -> SideStats:
        if key not in side_stats:
            side_stats[key] = SideStats(
                key=key,
                label=_build_side_label(key, names),
            )
        return side_stats[key]

    for km in killmails:
        value = float(km.get("total_value", 0.0))

        # Process victim
        victim = km.get("victim") or {}
        victim_key = _side_key_for_entity(victim)
        victim_side = ensure_side(victim_key)
        victim_side.isk_lost += value
        victim_side.ships_lost += 1
        if char_id := coerce_character_id(victim.get("character_id")):
            victim_side.pilots.add(char_id)

        # Process attackers
        attackers = km.get("attackers") or []
        if not attackers:
            continue

        # Aggregate attacker stats by side for this kill
        per_side: dict[str, dict[str, Any]] = {}
        for atk in attackers:
            atk_key = _side_key_for_entity(atk)
            atk_side = ensure_side(atk_key)

            if char_id := coerce_character_id(atk.get("character_id")):
                atk_side.pilots.add(char_id)

            if atk_key not in per_side:
                per_side[atk_key] = {"count": 0, "damage": 0.0, "final_blow": False}

            per_side[atk_key]["count"] += 1
            if isinstance(dmg := atk.get("damage_done"), (int, float)):
                per_side[atk_key]["damage"] += float(dmg)
            if atk.get("final_blow"):
                per_side[atk_key]["final_blow"] = True

        # Record assist relationships
        for atk_key in per_side:
            if atk_key != victim_key:
                analysis.assists_on_side[victim_key][atk_key] += 1
                analysis.assists_by_side[atk_key][victim_key] += 1

        # Determine which side gets credit for the kill
        killing_side_key = _determine_killer(per_side)
        if killing_side_key:
            killer_side = ensure_side(killing_side_key)
            killer_side.isk_destroyed += value
            killer_side.ships_destroyed += 1
            analysis.killers_of_side[victim_key][killing_side_key] += value
            analysis.kills_by_side[killing_side_key][victim_key] += value

    # Sort sides by involvement
    analysis.sides = sorted(
        side_stats.values(),
        key=lambda s: (s.isk_lost, s.isk_destroyed),
        reverse=True,
    )

    return analysis


def _determine_killer(per_side: dict[str, dict[str, Any]]) -> str | None:
    """Determine which side gets credit for a kill."""
    # Prefer final blow
    for key, stats in per_side.items():
        if stats["final_blow"]:
            return key

    # Fall back to most damage
    max_damage = max((s["damage"] for s in per_side.values()), default=0.0)
    if max_damage > 0:
        for key, stats in per_side.items():
            if stats["damage"] == max_damage:
                return key

    # Fall back to most attackers
    max_count = max((s["count"] for s in per_side.values()), default=0)
    for key, stats in per_side.items():
        if stats["count"] == max_count:
            return key

    return None


def _calculate_engagement(
    side_key: str,
    target_keys: set[str],
    analysis: SideAnalysis,
) -> float:
    """Calculate how engaged a side is with a set of target sides."""
    killers = analysis.killers_of_side.get(side_key, {})
    kills = analysis.kills_by_side.get(side_key, {})
    assists_on = analysis.assists_on_side.get(side_key, {})
    assists_by = analysis.assists_by_side.get(side_key, {})

    engagement = 0.0
    for target_key in target_keys:
        engagement += killers.get(target_key, 0.0)
        engagement += kills.get(target_key, 0.0)
        engagement += assists_on.get(target_key, 0)
        engagement += assists_by.get(target_key, 0)

    return engagement


def build_battle_report(
    url: str,
    system_name: str,
    timestamp_str: str,
    analysis: SideAnalysis,
    config: Config,
) -> BattleReport | None:
    """
    Build a battle report from analyzed side data.

    This determines which sides are attackers/defenders based on:
    - Preferred alliance/corp configuration (if present)
    - Engagement relationships between sides

    Args:
        url: The original WarBeacon URL.
        system_name: The solar system name.
        timestamp_str: Human-readable timestamp.
        analysis: The analyzed side data.
        config: Bot configuration for preferred sides.

    Returns:
        A BattleReport, or None if no sides were found.
    """
    sides = analysis.sides
    if not sides:
        logger.warning("No sides computed from WarBeacon data")
        return None

    if config.debug_br:
        _log_raw_sides(sides)

    total_isk = sum(s.isk_lost for s in sides)
    total_ships = sum(s.ships_lost for s in sides)

    # Check for preferred sides
    preferred_sides = [s for s in sides if config.is_preferred_side_key(s.key)]

    if preferred_sides:
        attackers, defenders, winner, color = _build_preferred_teams(
            sides, preferred_sides, analysis, config
        )
    else:
        attackers, defenders, winner, color = _build_neutral_teams(sides, analysis)

    # Calculate total unique pilots
    all_pilots = attackers.pilots | defenders.pilots

    if config.debug_br:
        _log_final_teams(attackers, defenders, all_pilots)

    return BattleReport(
        url=url,
        system_name=system_name,
        timestamp=timestamp_str,
        total_isk=total_isk,
        total_kills=total_ships,
        total_pilots=len(all_pilots),
        attackers=TeamStats.from_side(attackers),
        defenders=TeamStats.from_side(defenders),
        winner=winner,
        color=color,
    )


def _build_preferred_teams(
    sides: list[SideStats],
    preferred_sides: list[SideStats],
    analysis: SideAnalysis,
    config: Config,
) -> tuple[SideStats, SideStats, str, str]:
    """Build teams when preferred sides are present."""
    preferred_keys = {s.key for s in preferred_sides}

    # Merge preferred sides into one team
    preferred_team = preferred_sides[0].copy()
    for side in preferred_sides[1:]:
        preferred_team.merge_from(side)

    # Find enemy candidates
    enemy_candidates = [s for s in sides if s.key not in preferred_keys]

    # Find the enemy most engaged with preferred sides
    enemy_seed = _find_most_engaged_enemy(enemy_candidates, preferred_keys, analysis)

    if enemy_seed is None:
        enemy_team = SideStats(key="none", label="No Opponent")
    else:
        enemy_team = enemy_seed.copy()
        enemy_key = enemy_seed.key

        # Merge third parties based on engagement
        for side in enemy_candidates:
            if side.key == enemy_key:
                continue

            engage_pref = _calculate_engagement(side.key, preferred_keys, analysis)
            engage_enemy = _calculate_engagement(side.key, {enemy_key}, analysis)

            if engage_enemy > 0 and engage_pref == 0:
                preferred_team.merge_from(side)
            elif engage_pref > 0 and engage_enemy == 0:
                enemy_team.merge_from(side)

    # Determine winner
    if preferred_team.isk_lost < enemy_team.isk_lost:
        winner, color = "preferred_win", "green"
    elif preferred_team.isk_lost > enemy_team.isk_lost:
        winner, color = "preferred_loss", "red"
    else:
        winner, color = "tie", "grey"

    return preferred_team, enemy_team, winner, color


def _build_neutral_teams(
    sides: list[SideStats],
    analysis: SideAnalysis,
) -> tuple[SideStats, SideStats, str, str]:
    """Build teams for neutral battles (no preferred sides)."""
    sorted_sides = sorted(
        sides,
        key=lambda s: s.isk_lost + s.isk_destroyed,
        reverse=True,
    )

    side1 = sorted_sides[0]
    side2 = sorted_sides[1] if len(sorted_sides) > 1 else None

    team_a = side1.copy()
    team_b = side2.copy() if side2 else SideStats(key="none", label="No Opponent")

    if side2:
        side1_key, side2_key = side1.key, side2.key

        # Merge other sides based on engagement
        for side in sides:
            if side.key in (side1_key, side2_key):
                continue

            engage_1 = _calculate_engagement(side.key, {side1_key}, analysis)
            engage_2 = _calculate_engagement(side.key, {side2_key}, analysis)

            if engage_1 > 0 and engage_2 == 0:
                team_b.merge_from(side)
            elif engage_2 > 0 and engage_1 == 0:
                team_a.merge_from(side)

    # Put the side with less ISK lost as attackers (winners on left)
    if team_a.isk_lost <= team_b.isk_lost:
        attackers, defenders = team_a, team_b
    else:
        attackers, defenders = team_b, team_a

    color = "green" if attackers.isk_lost != defenders.isk_lost else "grey"
    return attackers, defenders, "neutral", color


def _find_most_engaged_enemy(
    candidates: list[SideStats],
    preferred_keys: set[str],
    analysis: SideAnalysis,
) -> SideStats | None:
    """Find the enemy side most engaged with preferred sides."""
    if not candidates:
        return None

    best_engagement = -1.0
    best_candidate = None

    for side in candidates:
        engagement = _calculate_engagement(side.key, preferred_keys, analysis)
        if engagement > best_engagement:
            best_engagement = engagement
            best_candidate = side

    if best_candidate is None:
        return max(candidates, key=lambda s: s.isk_lost + s.isk_destroyed)

    return best_candidate


def _log_raw_sides(sides: list[SideStats]) -> None:
    """Log raw side data for debugging."""
    logger.debug("=== RAW SIDES FROM WARBEACON ===")
    for s in sides:
        logger.debug(
            " side_key=%-10s label=%-10s pilots=%2d isk_lost=%.1f isk_destroyed=%.1f",
            s.key,
            s.label,
            len(s.pilots),
            s.isk_lost,
            s.isk_destroyed,
        )
    logger.debug("================================")


def _log_final_teams(
    attackers: SideStats,
    defenders: SideStats,
    all_pilots: set[int],
) -> None:
    """Log final team composition for debugging."""
    logger.debug("=== FINAL TEAMS ===")
    logger.debug(
        " Attackers: %-10s pilots=%2d ids=%s",
        attackers.label,
        len(attackers.pilots),
        sorted(attackers.pilots),
    )
    logger.debug(
        " Defenders: %-10s pilots=%2d ids=%s",
        defenders.label,
        len(defenders.pilots),
        sorted(defenders.pilots),
    )
    logger.debug(" Total unique pilots counted: %d", len(all_pilots))
    logger.debug("====================")
