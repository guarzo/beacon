"""Data models for battle report processing."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class SideStats:
    """Statistics for a single side (alliance/corp/character) in a battle."""

    key: str
    label: str
    isk_lost: float = 0.0
    ships_lost: int = 0
    isk_destroyed: float = 0.0
    ships_destroyed: int = 0
    pilots: set[int] = field(default_factory=set)

    @property
    def label_with_count(self) -> str:
        """Return label with pilot count, e.g. 'INIT (15)'."""
        return f"{self.label} ({len(self.pilots)})"

    def merge_from(self, other: SideStats) -> None:
        """Merge another side's stats into this one."""
        self.isk_lost += other.isk_lost
        self.ships_lost += other.ships_lost
        self.isk_destroyed += other.isk_destroyed
        self.ships_destroyed += other.ships_destroyed
        self.pilots.update(other.pilots)

    def copy(self) -> SideStats:
        """Create a copy of this side's stats."""
        return SideStats(
            key=self.key,
            label=self.label,
            isk_lost=self.isk_lost,
            ships_lost=self.ships_lost,
            isk_destroyed=self.isk_destroyed,
            ships_destroyed=self.ships_destroyed,
            pilots=set(self.pilots),
        )


@dataclass
class TeamStats:
    """Statistics for a team (attacker/defender) in a battle report."""

    name: str
    label_with_count: str
    pilot_count: int
    isk_lost: float
    ships_lost: int
    isk_destroyed: float
    ships_destroyed: int

    @classmethod
    def from_side(cls, side: SideStats) -> TeamStats:
        """Create TeamStats from a SideStats object."""
        return cls(
            name=side.label,
            label_with_count=side.label_with_count,
            pilot_count=len(side.pilots),
            isk_lost=side.isk_lost,
            ships_lost=side.ships_lost,
            isk_destroyed=side.isk_destroyed,
            ships_destroyed=side.ships_destroyed,
        )


@dataclass
class BattleReport:
    """A processed battle report ready for display."""

    url: str
    system_name: str
    timestamp: str
    total_isk: float
    total_kills: int
    total_pilots: int
    attackers: TeamStats
    defenders: TeamStats
    winner: str  # "preferred_win", "preferred_loss", "tie", "neutral"
    color: str  # "green", "red", "grey"


@dataclass
class SideAnalysis:
    """
    Result of analyzing killmails to determine sides and their relationships.

    Attributes:
        sides: List of all sides found in the battle.
        killers_of_side: Maps victim_side -> {killer_side -> ISK value killed}.
        kills_by_side: Maps killer_side -> {victim_side -> ISK value killed}.
        assists_on_side: Maps victim_side -> {attacker_side -> kill count}.
        assists_by_side: Maps attacker_side -> {victim_side -> kill count}.
    """

    sides: list[SideStats]
    killers_of_side: defaultdict[str, defaultdict[str, float]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(float))
    )
    kills_by_side: defaultdict[str, defaultdict[str, float]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(float))
    )
    assists_on_side: defaultdict[str, defaultdict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
    assists_by_side: defaultdict[str, defaultdict[str, int]] = field(
        default_factory=lambda: defaultdict(lambda: defaultdict(int))
    )
