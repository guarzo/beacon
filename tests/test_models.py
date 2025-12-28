"""Tests for beacon.models module."""

from beacon.models import BattleReport, SideAnalysis, SideStats, TeamStats


class TestSideStats:
    """Tests for SideStats dataclass."""

    def test_creates_with_defaults(self):
        side = SideStats(key="a:12345", label="TEST")
        assert side.key == "a:12345"
        assert side.label == "TEST"
        assert side.isk_lost == 0.0
        assert side.ships_lost == 0
        assert side.isk_destroyed == 0.0
        assert side.ships_destroyed == 0
        assert side.pilots == set()

    def test_label_with_count_zero_pilots(self):
        side = SideStats(key="a:12345", label="TEST")
        assert side.label_with_count == "TEST (0)"

    def test_label_with_count_with_pilots(self):
        side = SideStats(key="a:12345", label="TEST", pilots={1, 2, 3})
        assert side.label_with_count == "TEST (3)"

    def test_merge_from(self):
        side1 = SideStats(
            key="a:1",
            label="Side1",
            isk_lost=100,
            ships_lost=1,
            isk_destroyed=200,
            ships_destroyed=2,
            pilots={1, 2},
        )
        side2 = SideStats(
            key="a:2",
            label="Side2",
            isk_lost=50,
            ships_lost=1,
            isk_destroyed=100,
            ships_destroyed=1,
            pilots={3, 4},
        )

        side1.merge_from(side2)

        assert side1.isk_lost == 150
        assert side1.ships_lost == 2
        assert side1.isk_destroyed == 300
        assert side1.ships_destroyed == 3
        assert side1.pilots == {1, 2, 3, 4}
        # Key and label should remain unchanged
        assert side1.key == "a:1"
        assert side1.label == "Side1"

    def test_copy(self):
        original = SideStats(
            key="a:1",
            label="Test",
            isk_lost=100,
            ships_lost=5,
            isk_destroyed=200,
            ships_destroyed=10,
            pilots={1, 2, 3},
        )

        copied = original.copy()

        # Should have same values
        assert copied.key == original.key
        assert copied.label == original.label
        assert copied.isk_lost == original.isk_lost
        assert copied.ships_lost == original.ships_lost
        assert copied.isk_destroyed == original.isk_destroyed
        assert copied.ships_destroyed == original.ships_destroyed
        assert copied.pilots == original.pilots

        # But pilots should be a different set
        original.pilots.add(999)
        assert 999 not in copied.pilots


class TestTeamStats:
    """Tests for TeamStats dataclass."""

    def test_from_side(self):
        side = SideStats(
            key="a:1",
            label="TEST",
            isk_lost=100,
            ships_lost=5,
            isk_destroyed=200,
            ships_destroyed=10,
            pilots={1, 2, 3},
        )

        team = TeamStats.from_side(side)

        assert team.name == "TEST"
        assert team.label_with_count == "TEST (3)"
        assert team.pilot_count == 3
        assert team.isk_lost == 100
        assert team.ships_lost == 5
        assert team.isk_destroyed == 200
        assert team.ships_destroyed == 10


class TestBattleReport:
    """Tests for BattleReport dataclass."""

    def test_creates_with_all_fields(self):
        attackers = TeamStats(
            name="Attackers",
            label_with_count="Attackers (5)",
            pilot_count=5,
            isk_lost=100,
            ships_lost=2,
            isk_destroyed=500,
            ships_destroyed=10,
        )
        defenders = TeamStats(
            name="Defenders",
            label_with_count="Defenders (10)",
            pilot_count=10,
            isk_lost=500,
            ships_lost=10,
            isk_destroyed=100,
            ships_destroyed=2,
        )

        report = BattleReport(
            url="https://warbeacon.net/br/report/123",
            system_name="Jita",
            timestamp="2025-01-01 12:00",
            total_isk=600,
            total_kills=12,
            total_pilots=15,
            attackers=attackers,
            defenders=defenders,
            winner="preferred_win",
            color="green",
        )

        assert report.url == "https://warbeacon.net/br/report/123"
        assert report.system_name == "Jita"
        assert report.winner == "preferred_win"
        assert report.color == "green"


class TestSideAnalysis:
    """Tests for SideAnalysis dataclass."""

    def test_creates_with_empty_defaults(self):
        analysis = SideAnalysis(sides=[])
        assert analysis.sides == []
        assert len(analysis.killers_of_side) == 0
        assert len(analysis.kills_by_side) == 0
        assert len(analysis.assists_on_side) == 0
        assert len(analysis.assists_by_side) == 0

    def test_defaultdict_behavior(self):
        analysis = SideAnalysis(sides=[])

        # Should create nested defaultdict on access
        analysis.killers_of_side["victim"]["killer"] += 100
        assert analysis.killers_of_side["victim"]["killer"] == 100

        analysis.kills_by_side["killer"]["victim"] += 50
        assert analysis.kills_by_side["killer"]["victim"] == 50

        analysis.assists_on_side["victim"]["attacker"] += 1
        assert analysis.assists_on_side["victim"]["attacker"] == 1
