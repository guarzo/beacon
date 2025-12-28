"""Tests for beacon.config module."""

import pytest

from beacon.config import (
    WARBEACON_RELATED_RE,
    WARBEACON_REPORT_RE,
    Config,
    _parse_int_set,
)


class TestParseIntSet:
    """Tests for _parse_int_set function."""

    def test_parses_single_value(self):
        result = _parse_int_set("12345")
        assert result == {12345}

    def test_parses_multiple_values(self):
        result = _parse_int_set("1,2,3")
        assert result == {1, 2, 3}

    def test_handles_whitespace(self):
        result = _parse_int_set(" 1 , 2 , 3 ")
        assert result == {1, 2, 3}

    def test_returns_empty_for_empty_string(self):
        result = _parse_int_set("")
        assert result == set()

    def test_skips_invalid_values(self):
        result = _parse_int_set("1,invalid,3")
        assert result == {1, 3}

    def test_handles_all_invalid(self):
        result = _parse_int_set("invalid,bad,nope")
        assert result == set()


class TestConfig:
    """Tests for Config class."""

    def test_from_env_defaults(self, monkeypatch):
        monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
        monkeypatch.delenv("PREFERRED_ALLIANCES", raising=False)
        monkeypatch.delenv("PREFERRED_CORPS", raising=False)
        monkeypatch.delenv("DEBUG_BR", raising=False)

        config = Config.from_env()

        assert config.bot_token == ""
        assert config.preferred_alliances == frozenset({99010452})
        assert config.preferred_corps == frozenset({98648442})
        assert config.debug_br is False

    def test_from_env_custom_values(self, monkeypatch):
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
        monkeypatch.setenv("PREFERRED_ALLIANCES", "111,222")
        monkeypatch.setenv("PREFERRED_CORPS", "333,444")
        monkeypatch.setenv("DEBUG_BR", "true")

        config = Config.from_env()

        assert config.bot_token == "test-token"
        assert config.preferred_alliances == frozenset({111, 222})
        assert config.preferred_corps == frozenset({333, 444})
        assert config.debug_br is True

    def test_debug_br_variations(self, monkeypatch):
        for value in ["true", "TRUE", "True", "1", "yes", "YES"]:
            monkeypatch.setenv("DEBUG_BR", value)
            config = Config.from_env()
            assert config.debug_br is True, f"Failed for {value}"

        for value in ["false", "FALSE", "0", "no", ""]:
            monkeypatch.setenv("DEBUG_BR", value)
            config = Config.from_env()
            assert config.debug_br is False, f"Failed for {value}"

    def test_is_preferred_side_key_alliance(self):
        config = Config(
            bot_token="",
            preferred_alliances=frozenset({12345}),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        assert config.is_preferred_side_key("a:12345") is True
        assert config.is_preferred_side_key("a:99999") is False
        assert config.is_preferred_side_key("c:12345") is False

    def test_is_preferred_side_key_corp(self):
        config = Config(
            bot_token="",
            preferred_alliances=frozenset(),
            preferred_corps=frozenset({67890}),
            debug_br=False,
        )

        assert config.is_preferred_side_key("c:67890") is True
        assert config.is_preferred_side_key("c:99999") is False
        assert config.is_preferred_side_key("a:67890") is False

    def test_is_preferred_side_key_invalid(self):
        config = Config(
            bot_token="",
            preferred_alliances=frozenset({12345}),
            preferred_corps=frozenset(),
            debug_br=False,
        )

        assert config.is_preferred_side_key("p:12345") is False
        assert config.is_preferred_side_key("invalid") is False
        assert config.is_preferred_side_key("a:notanumber") is False

    def test_config_is_frozen(self):
        config = Config(
            bot_token="test",
            preferred_alliances=frozenset({1}),
            preferred_corps=frozenset({2}),
            debug_br=False,
        )

        with pytest.raises(AttributeError):
            config.bot_token = "new-token"


class TestWarBeaconRelatedRe:
    """Tests for WARBEACON_RELATED_RE pattern."""

    def test_matches_basic_url(self):
        url = "https://warbeacon.net/br/related/30002187/202512030400/"
        match = WARBEACON_RELATED_RE.search(url)
        assert match is not None
        assert match.group(2) == "30002187"
        assert match.group(3) == "202512030400"

    def test_matches_without_trailing_slash(self):
        url = "https://warbeacon.net/br/related/30002187/202512030400"
        match = WARBEACON_RELATED_RE.search(url)
        assert match is not None

    def test_matches_www_subdomain(self):
        url = "https://www.warbeacon.net/br/related/30002187/202512030400/"
        match = WARBEACON_RELATED_RE.search(url)
        assert match is not None

    def test_matches_http(self):
        url = "http://warbeacon.net/br/related/30002187/202512030400/"
        match = WARBEACON_RELATED_RE.search(url)
        assert match is not None

    def test_does_not_match_invalid_url(self):
        assert WARBEACON_RELATED_RE.search("https://other.com/br/related/1/2/") is None
        assert (
            WARBEACON_RELATED_RE.search("https://warbeacon.net/br/report/123/") is None
        )


class TestWarBeaconReportRe:
    """Tests for WARBEACON_REPORT_RE pattern."""

    def test_matches_uuid(self):
        url = "https://warbeacon.net/br/report/a1b2c3d4-e5f6-7890-abcd-ef1234567890/"
        match = WARBEACON_REPORT_RE.search(url)
        assert match is not None
        assert match.group(2) == "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

    def test_matches_without_trailing_slash(self):
        url = "https://warbeacon.net/br/report/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        match = WARBEACON_REPORT_RE.search(url)
        assert match is not None

    def test_matches_www_subdomain(self):
        url = (
            "https://www.warbeacon.net/br/report/a1b2c3d4-e5f6-7890-abcd-ef1234567890/"
        )
        match = WARBEACON_REPORT_RE.search(url)
        assert match is not None

    def test_does_not_match_invalid_uuid(self):
        assert (
            WARBEACON_REPORT_RE.search("https://warbeacon.net/br/report/notauuid/")
            is None
        )
