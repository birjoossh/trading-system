"""
Accuracy tests for expiry resolution.

Every expectation here is a hand-checked calendar date, not a recorded output.
The NSE rules come from config.yaml: Thursday expiries before the 2025-09-01
switch date, Tuesday expiries from that date onward. NYSE is Friday.
"""

import datetime as dt

import pytest

from unified_trading_platform.trading_core.strategy_engine.strategy_utils import (
    _get_expiry_params,
    monthly_expiry_for,
    next_monthly_expiry_for,
    next_weekly_expiry_for,
    resolve_expiry_keyword,
    weekly_expiry_for,
)

D = dt.date.fromisoformat


class TestConfiguredParameters:
    def test_nse_params_match_config(self):
        params = _get_expiry_params("NSE")
        assert params["wd_before"] == 3, "NSE used Thursday expiries before the switch"
        assert params["wd_after"] == 1, "NSE moved to Tuesday expiries"
        assert params["switch_date"] == D("2025-09-01")

    def test_nyse_params_match_config(self):
        params = _get_expiry_params("NYSE")
        assert params["wd_after"] == 4, "NYSE expires on Friday"

    def test_unknown_exchange_falls_back_to_friday(self):
        params = _get_expiry_params("NO_SUCH_EXCHANGE")
        assert params["wd_before"] == 4 and params["wd_after"] == 4


class TestWeeklyExpiryNSE:
    @pytest.mark.parametrize(
        "today,expected",
        [
            ("2024-01-02", "2024-01-04"),  # Tue -> that week's Thursday
            ("2024-01-03", "2024-01-04"),  # Wed -> next day
            ("2024-01-04", "2024-01-04"),  # on expiry day -> itself
            ("2024-01-05", "2024-01-11"),  # Fri -> following Thursday
            ("2024-01-08", "2024-01-11"),  # Mon -> that week's Thursday
            ("2024-12-23", "2024-12-26"),  # spans a holiday week, still Thursday
        ],
    )
    def test_before_switch_date_is_thursday(self, today, expected):
        assert weekly_expiry_for(D(today), "NSE") == D(expected)
        assert weekly_expiry_for(D(today), "NSE").weekday() == 3

    @pytest.mark.parametrize(
        "today,expected",
        [
            ("2025-09-01", "2025-09-02"),  # switch date itself (Mon) -> Tuesday
            ("2025-09-02", "2025-09-02"),  # on expiry day -> itself
            ("2025-09-03", "2025-09-09"),  # Wed -> following Tuesday
            ("2025-10-15", "2025-10-21"),
        ],
    )
    def test_from_switch_date_is_tuesday(self, today, expected):
        assert weekly_expiry_for(D(today), "NSE") == D(expected)
        assert weekly_expiry_for(D(today), "NSE").weekday() == 1

    def test_switch_boundary_is_inclusive(self):
        """The day before the switch still uses the old weekday."""
        assert weekly_expiry_for(D("2025-08-31"), "NSE").weekday() == 3
        assert weekly_expiry_for(D("2025-09-01"), "NSE").weekday() == 1

    def test_result_is_never_in_the_past(self):
        day = D("2024-01-01")
        for _ in range(400):
            assert weekly_expiry_for(day, "NSE") >= day
            day += dt.timedelta(days=1)


class TestWeeklyExpiryNYSE:
    @pytest.mark.parametrize(
        "today,expected",
        [
            ("2024-01-02", "2024-01-05"),
            ("2024-01-05", "2024-01-05"),
            ("2024-01-06", "2024-01-12"),
        ],
    )
    def test_is_friday(self, today, expected):
        assert weekly_expiry_for(D(today), "NYSE") == D(expected)
        assert weekly_expiry_for(D(today), "NYSE").weekday() == 4


class TestMonthlyExpiry:
    @pytest.mark.parametrize(
        "today,expected",
        [
            ("2024-01-02", "2024-01-25"),  # last Thursday of Jan 2024
            ("2024-01-25", "2024-01-25"),  # on expiry day
            ("2024-02-01", "2024-02-29"),  # leap-year February, last Thursday
            ("2024-12-05", "2024-12-26"),
        ],
    )
    def test_last_configured_weekday_of_month_nse(self, today, expected):
        result = monthly_expiry_for(D(today), "NSE")
        assert result == D(expected)
        assert result.weekday() == 3

    def test_after_switch_uses_last_tuesday(self):
        result = monthly_expiry_for(D("2025-09-05"), "NSE")
        assert result == D("2025-09-30")
        assert result.weekday() == 1

    def test_is_always_within_the_same_month(self):
        for month in range(1, 13):
            day = dt.date(2024, month, 5)
            result = monthly_expiry_for(day, "NSE")
            assert result.month == month and result.year == 2024

    def test_is_the_latest_such_weekday_in_month(self):
        """Nothing later in the month shares the expiry weekday."""
        result = monthly_expiry_for(D("2024-03-01"), "NSE")
        later = result + dt.timedelta(days=7)
        assert later.month != result.month


class TestNextExpiries:
    def test_next_weekly_is_one_week_after_this_weekly(self):
        this_week = weekly_expiry_for(D("2024-01-02"), "NSE")
        nxt = next_weekly_expiry_for(D("2024-01-02"), "NSE")
        assert this_week == D("2024-01-04")
        assert nxt == D("2024-01-11")
        assert (nxt - this_week).days == 7

    def test_next_weekly_from_expiry_day_moves_forward(self):
        assert next_weekly_expiry_for(D("2024-01-04"), "NSE") == D("2024-01-11")

    def test_next_monthly_is_the_following_month(self):
        assert monthly_expiry_for(D("2024-01-02"), "NSE") == D("2024-01-25")
        assert next_monthly_expiry_for(D("2024-01-02"), "NSE") == D("2024-02-29")

    def test_next_monthly_is_strictly_later(self):
        for month in range(1, 12):
            day = dt.date(2024, month, 10)
            assert next_monthly_expiry_for(day, "NSE") > monthly_expiry_for(day, "NSE")


class TestKeywordResolution:
    BASE = D("2024-01-02")

    @pytest.mark.parametrize(
        "keyword,expected",
        [
            ("Weekly", "2024-01-04"),
            ("weekly", "2024-01-04"),
            ("WEEKLY", "2024-01-04"),
            ("NextWeekly", "2024-01-11"),
            ("Next Weekly", "2024-01-11"),
            ("Monthly", "2024-01-25"),
            ("NextMonthly", "2024-02-29"),
        ],
    )
    def test_keywords_are_case_and_space_insensitive(self, keyword, expected):
        assert resolve_expiry_keyword(self.BASE, keyword, "NSE") == D(expected)

    def test_unknown_and_empty_keywords_default_to_weekly(self):
        assert resolve_expiry_keyword(self.BASE, "SomethingElse", "NSE") == D("2024-01-04")
        assert resolve_expiry_keyword(self.BASE, None, "NSE") == D("2024-01-04")

    def test_matches_the_expiry_in_the_bundled_sample_data(self):
        """The 2024-01-02 sample H5 contains exactly one expiry: 2024-01-04."""
        assert resolve_expiry_keyword(D("2024-01-02"), "Weekly", "NSE") == D("2024-01-04")
