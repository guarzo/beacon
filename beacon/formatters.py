"""Formatting utilities for battle reports and Discord embeds."""

from __future__ import annotations

import discord

from .models import BattleReport


def format_isk_short(value: float) -> str:
    """
    Format an ISK value to a short human-readable string.

    Args:
        value: The ISK value to format.

    Returns:
        Formatted string like '1.5b', '250.0m', '50.0k', or the raw integer.
    """
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
    Create a text-based ratio bar showing ISK losses between two sides.

    The bar uses filled (dark) and empty (light) blocks to represent
    the proportion of losses. A full empty bar indicates one side
    took no losses (complete wipe).

    Args:
        a_isk: ISK lost by side A.
        b_isk: ISK lost by side B.
        length: Total length of the bar in characters.

    Returns:
        A formatted bar string wrapped in backticks for Discord.
    """
    total = a_isk + b_isk
    empty_bar = f"`{'_' * length}`"

    if total <= 0 or a_isk == 0 or b_isk == 0:
        return empty_bar

    a_ratio = a_isk / total
    a_blocks = int(round(a_ratio * length))
    a_blocks = max(1, min(length - 1, a_blocks))
    b_blocks = length - a_blocks

    bar = "_" * a_blocks + "_" * b_blocks
    return f"`{bar}`"


COLOR_MAP: dict[str, discord.Color] = {
    "green": discord.Color.green(),
    "red": discord.Color.red(),
    "grey": discord.Color.dark_grey(),
}


def build_embed(br: BattleReport) -> discord.Embed:
    """
    Build a Discord embed from a battle report.

    Args:
        br: The battle report to display.

    Returns:
        A formatted Discord embed.
    """
    color = COLOR_MAP.get(br.color, discord.Color.dark_grey())

    embed = discord.Embed(
        title=f"Battle Report - {br.system_name}",
        url=br.url,
        color=color,
    )

    embed.description = f"{br.timestamp}\n--------------------"

    # ISK Loss Split
    ratio_bar = make_ratio_bar(br.attackers.isk_lost, br.defenders.isk_lost)
    split_text = (
        f"**{br.attackers.label_with_count}** vs **{br.defenders.label_with_count}**\n"
        f"{ratio_bar}\n"
        f"{format_isk_short(br.attackers.isk_lost)} vs "
        f"{format_isk_short(br.defenders.isk_lost)} ISK lost"
    )
    embed.add_field(
        name="ISK Loss Split",
        value=f"{split_text}\n--------------------",
        inline=False,
    )

    # Totals
    totals_text = (
        f"* **ISK lost:** {format_isk_short(br.total_isk)}\n"
        f"* **Ships lost:** {br.total_kills}\n"
        f"* **Pilots:** {br.total_pilots}\n"
    )
    embed.add_field(
        name="Totals",
        value=f"{totals_text}--------------------",
        inline=False,
    )

    # Attackers
    atk = br.attackers
    atk_text = (
        f"* **ISK lost:** {format_isk_short(atk.isk_lost)}\n"
        f"* **Ships lost:** {atk.ships_lost}\n"
        f"* **ISK destroyed:** {format_isk_short(atk.isk_destroyed)}\n"
        f"* **Ships destroyed:** {atk.ships_destroyed}"
    )
    embed.add_field(
        name=f"{atk.label_with_count}",
        value=atk_text,
        inline=True,
    )

    # Defenders
    dfn = br.defenders
    dfn_text = (
        f"* **ISK lost:** {format_isk_short(dfn.isk_lost)}\n"
        f"* **Ships lost:** {dfn.ships_lost}\n"
        f"* **ISK destroyed:** {format_isk_short(dfn.isk_destroyed)}\n"
        f"* **Ships destroyed:** {dfn.ships_destroyed}"
    )
    embed.add_field(
        name=f"{dfn.label_with_count}",
        value=dfn_text,
        inline=True,
    )

    return embed
