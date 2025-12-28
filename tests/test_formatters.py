"""Tests for beacon.formatters module."""

from beacon.formatters import format_isk_short, make_ratio_bar


class TestFormatIskShort:
    """Tests for format_isk_short function."""

    def test_formats_billions(self):
        assert format_isk_short(1_500_000_000) == "1.5b"
        assert format_isk_short(10_000_000_000) == "10.0b"

    def test_formats_millions(self):
        assert format_isk_short(250_000_000) == "250.0m"
        assert format_isk_short(1_500_000) == "1.5m"

    def test_formats_thousands(self):
        assert format_isk_short(50_000) == "50.0k"
        assert format_isk_short(1_500) == "1.5k"

    def test_formats_small_values(self):
        assert format_isk_short(999) == "999"
        assert format_isk_short(0) == "0"

    def test_handles_float_input(self):
        assert format_isk_short(1_500_000_000.5) == "1.5b"

    def test_handles_string_number(self):
        assert format_isk_short("1500000000") == "1.5b"

    def test_handles_invalid_input(self):
        assert format_isk_short("not-a-number") == "N/A"
        assert format_isk_short(None) == "N/A"

    def test_boundary_at_billion(self):
        assert format_isk_short(1_000_000_000) == "1.0b"
        assert format_isk_short(999_999_999) == "1000.0m"

    def test_boundary_at_million(self):
        assert format_isk_short(1_000_000) == "1.0m"
        assert format_isk_short(999_999) == "1000.0k"

    def test_boundary_at_thousand(self):
        assert format_isk_short(1_000) == "1.0k"


class TestMakeRatioBar:
    """Tests for make_ratio_bar function."""

    def test_equal_losses(self):
        bar = make_ratio_bar(100, 100)
        # Should have underscores wrapped in backticks
        assert bar.startswith("`")
        assert bar.endswith("`")
        assert len(bar) == 22  # 20 chars + 2 backticks

    def test_one_side_only(self):
        bar = make_ratio_bar(100, 0)
        assert bar == "`____________________`"

    def test_other_side_only(self):
        bar = make_ratio_bar(0, 100)
        assert bar == "`____________________`"

    def test_zero_total(self):
        bar = make_ratio_bar(0, 0)
        assert bar == "`____________________`"

    def test_custom_length(self):
        bar = make_ratio_bar(50, 50, length=10)
        assert len(bar) == 12  # 10 chars + 2 backticks

    def test_lopsided_losses(self):
        # When a_isk is much higher, should show more blocks on left
        bar = make_ratio_bar(900, 100)
        content = bar[1:-1]  # Strip backticks
        assert len(content) == 20

    def test_returns_string(self):
        bar = make_ratio_bar(100, 200)
        assert isinstance(bar, str)
