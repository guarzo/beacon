"""Tests for beacon.sides module."""

from beacon.config import Config
from beacon.models import SideAnalysis, SideStats
from beacon.sides import (
    _calculate_engagement,
    _determine_killer,
    _side_key_for_entity,
    analyze_killmails,
    build_battle_report,
)


class TestSideKeyForEntity:
    """Tests for _side_key_for_entity function."""

    def test_prefers_alliance_id(self):
        entity = {
            "alliance_id": 12345,
            "corporation_id": 67890,
            "character_id": 11111,
        }
        assert _side_key_for_entity(entity) == "a:12345"

    def test_falls_back_to_corp_id(self):
        entity = {
            "corporation_id": 67890,
            "character_id": 11111,
        }
        assert _side_key_for_entity(entity) == "c:67890"

    def test_falls_back_to_character_id(self):
        entity = {"character_id": 11111}
        assert _side_key_for_entity(entity) == "p:11111"

    def test_returns_unknown_for_empty(self):
        assert _side_key_for_entity({}) == "unknown"

    def test_handles_zero_alliance_id(self):
        # 0 is a valid alliance_id since the code checks `is not None`
        entity = {"alliance_id": 0}
        assert _side_key_for_entity(entity) == "a:0"

    def test_handles_none_values(self):
        entity = {"alliance_id": None, "corporation_id": 12345}
        assert _side_key_for_entity(entity) == "c:12345"


class TestDetermineKiller:
    """Tests for _determine_killer function."""

    def test_prefers_final_blow(self):
        per_side = {
            "a:1": {"count": 5, "damage": 1000.0, "final_blow": False},
            "a:2": {"count": 1, "damage": 100.0, "final_blow": True},
        }
        assert _determine_killer(per_side) == "a:2"

    def test_falls_back_to_most_damage(self):
        per_side = {
            "a:1": {"count": 1, "damage": 1000.0, "final_blow": False},
            "a:2": {"count": 5, "damage": 100.0, "final_blow": False},
        }
        assert _determine_killer(per_side) == "a:1"

    def test_falls_back_to_most_attackers(self):
        per_side = {
            "a:1": {"count": 1, "damage": 0.0, "final_blow": False},
            "a:2": {"count": 5, "damage": 0.0, "final_blow": False},
        }
        assert _determine_killer(per_side) == "a:2"

    def test_returns_none_for_empty(self):
        assert _determine_killer({}) is None


class TestAnalyzeKillmails:
    """Tests for analyze_killmails function."""

    def test_processes_single_killmail(self):
        data = {
            "killmails": [
                {
                    "total_value": 1000.0,
                    "victim": {
                        "alliance_id": 100,
                        "character_id": 1001,
                    },
                    "attackers": [
                        {
                            "alliance_id": 200,
                            "character_id": 2001,
                            "damage_done": 500,
                            "final_blow": True,
                        }
                    ],
                }
            ],
            "names": {
                "entities": {"100": "Victim Alliance", "200": "Attacker Alliance"},
                "tickers": {"100": "VICT", "200": "ATTK"},
            },
        }

        analysis = analyze_killmails(data)

        assert len(analysis.sides) == 2

        # Find victim and attacker sides
        victim_side = next(s for s in analysis.sides if s.key == "a:100")
        attacker_side = next(s for s in analysis.sides if s.key == "a:200")

        assert victim_side.isk_lost == 1000.0
        assert victim_side.ships_lost == 1
        assert 1001 in victim_side.pilots

        assert attacker_side.isk_destroyed == 1000.0
        assert attacker_side.ships_destroyed == 1
        assert 2001 in attacker_side.pilots

    def test_handles_empty_killmails(self):
        data = {"killmails": [], "names": {}}
        analysis = analyze_killmails(data)
        assert analysis.sides == []

    def test_handles_missing_killmails(self):
        data = {"names": {}}
        analysis = analyze_killmails(data)
        assert analysis.sides == []

    def test_tracks_assist_relationships(self):
        data = {
            "killmails": [
                {
                    "total_value": 1000.0,
                    "victim": {"alliance_id": 100, "character_id": 1001},
                    "attackers": [
                        {
                            "alliance_id": 200,
                            "character_id": 2001,
                            "damage_done": 500,
                            "final_blow": True,
                        },
                        {
                            "alliance_id": 300,
                            "character_id": 3001,
                            "damage_done": 300,
                            "final_blow": False,
                        },
                    ],
                }
            ],
            "names": {},
        }

        analysis = analyze_killmails(data)

        # Both 200 and 300 should have assist relationships with 100
        assert analysis.assists_on_side["a:100"]["a:200"] == 1
        assert analysis.assists_on_side["a:100"]["a:300"] == 1

    def test_sides_sorted_by_involvement(self):
        data = {
            "killmails": [
                {
                    "total_value": 1000.0,
                    "victim": {"alliance_id": 100},
                    "attackers": [{"alliance_id": 200, "final_blow": True}],
                },
                {
                    "total_value": 5000.0,
                    "victim": {"alliance_id": 300},
                    "attackers": [{"alliance_id": 200, "final_blow": True}],
                },
            ],
            "names": {},
        }

        analysis = analyze_killmails(data)

        # Sorted by (isk_lost, isk_destroyed) descending
        # a:300 has 5000 ISK lost, a:200 has 6000 destroyed but 0 lost
        assert analysis.sides[0].key == "a:300"  # 5000 ISK lost
        assert analysis.sides[1].key == "a:100"  # 1000 ISK lost
        assert analysis.sides[2].key == "a:200"  # 0 ISK lost, 6000 destroyed


class TestCalculateEngagement:
    """Tests for _calculate_engagement function."""

    def test_sums_all_engagement_types(self):
        analysis = SideAnalysis(sides=[])
        analysis.killers_of_side["a:1"]["a:2"] = 100.0
        analysis.kills_by_side["a:1"]["a:2"] = 50.0
        analysis.assists_on_side["a:1"]["a:2"] = 3
        analysis.assists_by_side["a:1"]["a:2"] = 2

        engagement = _calculate_engagement("a:1", {"a:2"}, analysis)
        assert engagement == 155.0  # 100 + 50 + 3 + 2

    def test_returns_zero_for_no_engagement(self):
        analysis = SideAnalysis(sides=[])
        engagement = _calculate_engagement("a:1", {"a:2"}, analysis)
        assert engagement == 0.0

    def test_handles_multiple_targets(self):
        analysis = SideAnalysis(sides=[])
        analysis.kills_by_side["a:1"]["a:2"] = 100.0
        analysis.kills_by_side["a:1"]["a:3"] = 50.0

        engagement = _calculate_engagement("a:1", {"a:2", "a:3"}, analysis)
        assert engagement == 150.0


class TestBuildBattleReport:
    """Tests for build_battle_report function."""

    def test_returns_none_for_no_sides(self):
        analysis = SideAnalysis(sides=[])
        config = Config(
            bot_token="",
            preferred_alliances=frozenset(),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        result = build_battle_report(
            url="https://test.com",
            system_name="Jita",
            timestamp_str="2025-01-01",
            analysis=analysis,
            config=config,
        )

        assert result is None

    def test_builds_report_with_preferred_sides(self):
        side1 = SideStats(
            key="a:12345",
            label="Preferred",
            isk_lost=100,
            ships_lost=1,
            isk_destroyed=500,
            ships_destroyed=5,
            pilots={1, 2},
        )
        side2 = SideStats(
            key="a:67890",
            label="Enemy",
            isk_lost=500,
            ships_lost=5,
            isk_destroyed=100,
            ships_destroyed=1,
            pilots={3, 4, 5},
        )

        analysis = SideAnalysis(sides=[side1, side2])
        analysis.kills_by_side["a:12345"]["a:67890"] = 500.0
        analysis.kills_by_side["a:67890"]["a:12345"] = 100.0

        config = Config(
            bot_token="",
            preferred_alliances=frozenset({12345}),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        result = build_battle_report(
            url="https://test.com/br",
            system_name="Jita",
            timestamp_str="2025-01-01 12:00",
            analysis=analysis,
            config=config,
        )

        assert result is not None
        assert result.system_name == "Jita"
        assert result.winner == "preferred_win"
        assert result.color == "green"
        assert result.attackers.name == "Preferred"
        assert result.defenders.name == "Enemy"

    def test_builds_report_preferred_loss(self):
        side1 = SideStats(
            key="a:12345",
            label="Preferred",
            isk_lost=500,  # Lost more
            ships_lost=5,
            isk_destroyed=100,
            ships_destroyed=1,
            pilots={1, 2},
        )
        side2 = SideStats(
            key="a:67890",
            label="Enemy",
            isk_lost=100,  # Lost less
            ships_lost=1,
            isk_destroyed=500,
            ships_destroyed=5,
            pilots={3, 4, 5},
        )

        analysis = SideAnalysis(sides=[side1, side2])
        analysis.kills_by_side["a:12345"]["a:67890"] = 100.0
        analysis.kills_by_side["a:67890"]["a:12345"] = 500.0

        config = Config(
            bot_token="",
            preferred_alliances=frozenset({12345}),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        result = build_battle_report(
            url="https://test.com/br",
            system_name="Jita",
            timestamp_str="2025-01-01 12:00",
            analysis=analysis,
            config=config,
        )

        assert result is not None
        assert result.winner == "preferred_loss"
        assert result.color == "red"

    def test_builds_neutral_report(self):
        side1 = SideStats(
            key="a:111",
            label="Side A",
            isk_lost=100,
            ships_lost=1,
            isk_destroyed=200,
            ships_destroyed=2,
            pilots={1},
        )
        side2 = SideStats(
            key="a:222",
            label="Side B",
            isk_lost=200,
            ships_lost=2,
            isk_destroyed=100,
            ships_destroyed=1,
            pilots={2},
        )

        analysis = SideAnalysis(sides=[side1, side2])
        analysis.kills_by_side["a:111"]["a:222"] = 200.0
        analysis.kills_by_side["a:222"]["a:111"] = 100.0

        config = Config(
            bot_token="",
            preferred_alliances=frozenset(),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        result = build_battle_report(
            url="https://test.com/br",
            system_name="Jita",
            timestamp_str="2025-01-01 12:00",
            analysis=analysis,
            config=config,
        )

        assert result is not None
        assert result.winner == "neutral"
        assert result.color == "green"  # Side with less ISK lost wins
