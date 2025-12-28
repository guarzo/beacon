"""Discord bot setup and event handlers."""

from __future__ import annotations

import logging
from contextlib import suppress

import aiohttp
import discord
from discord.ext import commands

from .config import WARBEACON_RELATED_RE, WARBEACON_REPORT_RE, Config
from .formatters import build_embed
from .warbeacon import fetch_related_br, fetch_report_br

logger = logging.getLogger(__name__)


def create_bot() -> commands.Bot:
    """Create and configure the Discord bot."""
    intents = discord.Intents.default()
    intents.message_content = True
    return commands.Bot(command_prefix="!", intents=intents)


bot = create_bot()


@bot.command()
async def ping(ctx: commands.Context) -> None:
    """Simple ping command for testing."""
    await ctx.send("pong")


@bot.event
async def on_ready() -> None:
    """Log when the bot is ready."""
    if bot.user:
        logger.info(f"Logged in as {bot.user} (id: {bot.user.id})")


@bot.event
async def on_message(message: discord.Message) -> None:
    """Handle incoming messages, looking for WarBeacon links."""
    if message.author.bot:
        return

    content = message.content or ""
    config = Config.from_env()

    # Try matching /related first, then /report
    match_related = WARBEACON_RELATED_RE.search(content)
    match_report = None if match_related else WARBEACON_REPORT_RE.search(content)

    br = None

    if match_related:
        url = match_related.group(1)
        system_id = match_related.group(2)
        related_time = match_related.group(3)

        async with aiohttp.ClientSession() as session:
            br = await fetch_related_br(session, url, system_id, related_time, config)

    elif match_report:
        url = match_report.group(1)
        report_id = match_report.group(2)

        async with aiohttp.ClientSession() as session:
            br = await fetch_report_br(session, url, report_id, config)

    if br:
        embed = build_embed(br)
        await message.channel.send(embed=embed)

        # Try to delete the original message
        with suppress(discord.Forbidden, discord.HTTPException):
            await message.delete()

    await bot.process_commands(message)


def run(token: str) -> None:
    """Run the bot with the given token."""
    bot.run(token)
