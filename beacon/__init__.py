"""Beacon - A Discord bot for EVE Online WarBeacon battle reports."""

from .bot import bot, run
from .config import Config
from .models import BattleReport, SideAnalysis, SideStats, TeamStats

__all__ = [
    "BattleReport",
    "Config",
    "SideAnalysis",
    "SideStats",
    "TeamStats",
    "bot",
    "run",
]

__version__ = "1.0.0"
