"""
Accuracy tests for strike selection.

The chain used here is deliberately synthetic and regular (strikes every 50,
monotone premiums) so that every expected strike below is arithmetic that can be
checked by hand rather than a value copied from a previous run.

Chain layout (centre 21600, step 50):
    strike   21400 21450 21500 21550 21600 21650 21700 21750 21800
    CE price   200   180   160   140   120   100    80    60    40
    PE price     1    20    40    60    80   100   120   140   160
"""

import datetime as dt

import pandas as pd
import pytest

from unified_trading_platform.trading_core.strategy_engine.config import StrikeCriteria
from unified_trading_platform.trading_core.strategy_engine.strikes import _detect_step, select_strike

from helpers import straddle_chain


def criteria(mode: str, **params) -> StrikeCriteria:
    return StrikeCriteria(mode=mode, params=params)


@pytest.fixture
def chain() -> pd.DataFrame:
    return straddle_chain(center=21600.0, ce_atm=120.0, pe_atm=80.0, width=4)


class TestStepDetection:
    def test_detects_regular_step(self, chain):
        assert _detect_step(chain["strike"]) == 50.0

    def test_uses_most_common_gap_when_irregular(self):
        strikes = pd.Series([100, 150, 200, 250, 400])  # one gap of 150, three of 50
        assert _detect_step(strikes) == 50.0

    def test_falls_back_to_default_for_single_strike(self):
        assert _detect_step(pd.Series([21600.0]), default=100.0) == 100.0

    def test_ignores_nan(self):
        assert _detect_step(pd.Series([100.0, float("nan"), 150.0, 200.0])) == 50.0


class TestStrikeTypeMode:
    """ATM is round(spot / step) * step, snapped to an available strike."""

    @pytest.mark.parametrize(
        "spot,expected",
        [
            (21600.0, 21600.0),
            (21612.20, 21600.0),  # rounds down
            (21620.0, 21600.0),
            (21630.0, 21650.0),  # rounds up
            (21649.0, 21650.0),
            (21751.0, 21750.0),
        ],
    )
    def test_atm(self, chain, spot, expected):
        assert select_strike(chain, "CE", spot, criteria("STRIKE_TYPE", strike_type="ATM")) == expected

    @pytest.mark.parametrize(
        "option_type,strike_type,expected",
        [
            # OTM calls are above spot, OTM puts below.
            ("CE", "OTM1", 21650.0),
            ("CE", "OTM2", 21700.0),
            ("CE", "OTM4", 21800.0),
            ("PE", "OTM1", 21550.0),
            ("PE", "OTM2", 21500.0),
            # ITM is the mirror image.
            ("CE", "ITM1", 21550.0),
            ("CE", "ITM2", 21500.0),
            ("PE", "ITM1", 21650.0),
            ("PE", "ITM2", 21700.0),
        ],
    )
    def test_otm_and_itm_offsets(self, chain, option_type, strike_type, expected):
        got = select_strike(chain, option_type, 21600.0, criteria("STRIKE_TYPE", strike_type=strike_type))
        assert got == expected

    def test_otm_steps_parameter(self, chain):
        got = select_strike(chain, "CE", 21600.0, criteria("STRIKE_TYPE", strike_type="OTM", otm_steps=3))
        assert got == 21750.0

    def test_offsets_are_relative_to_atm_not_to_spot(self, chain):
        """Spot 21630 rounds to ATM 21650, so OTM1 CE is 21700."""
        got = select_strike(chain, "CE", 21630.0, criteria("STRIKE_TYPE", strike_type="OTM1"))
        assert got == 21700.0

    def test_snaps_to_an_existing_strike_beyond_chain_edge(self, chain):
        """Asking for OTM10 cannot invent strikes; it clamps to the widest one."""
        got = select_strike(chain, "CE", 21600.0, criteria("STRIKE_TYPE", strike_type="OTM10"))
        assert got == 21800.0


class TestPremiumModes:
    def test_closest_premium(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("CLOSEST_PREMIUM", premium=140)) == 21550.0
        assert select_strike(chain, "PE", 21600.0, criteria("CLOSEST_PREMIUM", premium=140)) == 21750.0

    def test_closest_premium_picks_nearest_when_no_exact_match(self, chain):
        # CE premiums are ...100 (21650), 80 (21700)... so 95 is nearest to 100.
        assert select_strike(chain, "CE", 21600.0, criteria("CLOSEST_PREMIUM", premium=95)) == 21650.0

    def test_premium_le_picks_richest_option_within_limit(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_LE", value=100)) == 21650.0
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_LE", value=99)) == 21700.0

    def test_premium_le_falls_back_to_cheapest_when_all_exceed_limit(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_LE", value=1)) == 21800.0

    def test_premium_ge_picks_cheapest_option_above_limit(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_GE", value=160)) == 21500.0
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_GE", value=161)) == 21450.0

    def test_premium_ge_falls_back_to_richest_when_none_qualify(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_GE", value=10_000)) == 21400.0

    def test_premium_range_targets_the_midpoint(self, chain):
        # Range [60, 100] -> midpoint 80 -> CE priced 80 is strike 21700.
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_RANGE", lower=60, upper=100)) == 21700.0

    def test_premium_range_accepts_reversed_bounds(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("PREMIUM_RANGE", lower=100, upper=60)) == 21700.0

    def test_premium_range_falls_back_to_closest_outside_range(self, chain):
        got = select_strike(chain, "CE", 21600.0, criteria("PREMIUM_RANGE", lower=500, upper=600))
        assert got == 21400.0  # richest available (200) is closest to the range

    def test_reads_price_column_when_close_is_absent(self, chain):
        """Backtest chains carry `price`; broker chains carry `Close`."""
        assert "Close" not in chain.columns and "price" in chain.columns
        renamed = chain.rename(columns={"price": "Close"})
        assert select_strike(chain, "CE", 21600.0, criteria("CLOSEST_PREMIUM", premium=140)) == select_strike(
            renamed, "CE", 21600.0, criteria("CLOSEST_PREMIUM", premium=140)
        )


class TestSyntheticModes:
    """Modes that combine both sides of the chain. ATM straddle = 120 + 80 = 200."""

    def test_straddle_width(self, chain):
        # target = 21600 + 0.5 * 200 = 21700
        got = select_strike(chain, "CE", 21600.0, criteria("STRADDLE_WIDTH", sign="+", multiplier=0.5))
        assert got == 21700.0

    def test_straddle_width_negative_direction(self, chain):
        got = select_strike(chain, "PE", 21600.0, criteria("STRADDLE_WIDTH", sign="-", multiplier=0.5))
        assert got == 21500.0

    def test_synthetic_future(self, chain):
        # synthetic future = 21600 - 80 + 120 = 21640 -> snaps to 21650
        got = select_strike(chain, "CE", 21600.0, criteria("SYNTHETIC_FUTURE", strike_type="ATM"))
        assert got == 21650.0

    def test_synthetic_future_with_otm_offset(self, chain):
        got = select_strike(chain, "CE", 21600.0, criteria("SYNTHETIC_FUTURE", strike_type="OTM1"))
        assert got == 21700.0

    def test_pct_of_atm(self, chain):
        # 21600 * 1.005 = 21708 -> snaps to 21700
        got = select_strike(chain, "CE", 21600.0, criteria("PCT_OF_ATM", pct=0.5, sign="+"))
        assert got == 21700.0

    def test_pct_of_atm_alias(self, chain):
        assert select_strike(chain, "CE", 21600.0, criteria("%_OF_ATM", pct=0.5, sign="+")) == 21700.0

    def test_pct_of_atm_negative(self, chain):
        got = select_strike(chain, "CE", 21600.0, criteria("PCT_OF_ATM", pct=0.5, sign="-"))
        assert got == 21500.0

    def test_atm_premium_pct(self, chain):
        # 50% of the 200-point straddle = 100 -> CE priced 100 is strike 21650
        got = select_strike(chain, "CE", 21600.0, criteria("ATM_PREMIUM_PCT", pct=50))
        assert got == 21650.0

    def test_requires_both_sides_of_chain(self, chain):
        calls_only = chain[chain["option_type"] == "CE"]
        with pytest.raises(ValueError, match="[Bb]oth CE and PE"):
            select_strike(calls_only, "CE", 21600.0, criteria("STRADDLE_WIDTH", sign="+", multiplier=0.5))


class TestDeltaModes:
    """Delta values are supplied explicitly so selection is isolated from pricing."""

    @pytest.fixture
    def delta_chain(self):
        chain = straddle_chain(center=21600.0, width=4)
        deltas = {
            21400.0: 0.90,
            21450.0: 0.80,
            21500.0: 0.70,
            21550.0: 0.60,
            21600.0: 0.50,
            21650.0: 0.35,
            21700.0: 0.25,
            21750.0: 0.15,
            21800.0: 0.05,
        }
        chain = chain.copy()
        chain["Delta"] = [
            deltas[row.strike] if row.option_type == "CE" else -(1.0 - deltas[row.strike])
            for row in chain.itertuples()
        ]
        return chain

    def test_closest_delta(self, delta_chain):
        got = select_strike(delta_chain, "CE", 21600.0, criteria("CLOSEST_DELTA", delta=30), exchange="NSE")
        assert got == 21650.0  # |0.35 - 0.30| < |0.25 - 0.30|

    def test_closest_delta_accepts_fractional_target(self, delta_chain):
        got = select_strike(delta_chain, "CE", 21600.0, criteria("CLOSEST_DELTA", delta=0.25), exchange="NSE")
        assert got == 21700.0

    def test_closest_delta_uses_absolute_value_for_puts(self, delta_chain):
        # PE delta at 21550 is -(1 - 0.60) = -0.40
        got = select_strike(delta_chain, "PE", 21600.0, criteria("CLOSEST_DELTA", delta=40), exchange="NSE")
        assert got == 21550.0

    def test_delta_range_buy_takes_the_lowest_delta(self, delta_chain):
        got = select_strike(
            delta_chain, "CE", 21600.0, criteria("DELTA_RANGE", lower=20, upper=60, position="BUY"), exchange="NSE"
        )
        assert got == 21700.0  # 0.25 is the lowest delta inside [0.20, 0.60]

    def test_delta_range_sell_takes_the_highest_delta(self, delta_chain):
        got = select_strike(
            delta_chain, "CE", 21600.0, criteria("DELTA_RANGE", lower=20, upper=60, position="SELL"), exchange="NSE"
        )
        assert got == 21550.0  # 0.60 is the highest delta inside the band

    def test_delta_range_rejects_empty_band(self, delta_chain):
        with pytest.raises(ValueError, match="delta range"):
            select_strike(
                delta_chain, "CE", 21600.0, criteria("DELTA_RANGE", lower=95, upper=99, position="BUY"), exchange="NSE"
            )

    def test_delta_modes_require_exchange(self, delta_chain):
        """Expiry inference needs the exchange's close time; refuse to guess."""
        with pytest.raises(ValueError):
            select_strike(delta_chain, "CE", 21600.0, criteria("CLOSEST_DELTA", delta=30))


class TestErrorHandling:
    def test_empty_chain_raises(self):
        empty = straddle_chain().iloc[0:0]
        with pytest.raises(ValueError):
            select_strike(empty, "CE", 21600.0, criteria("STRIKE_TYPE", strike_type="ATM"))

    def test_missing_option_type_raises(self, chain):
        puts_only = chain[chain["option_type"] == "PE"]
        with pytest.raises(ValueError, match="No CE rows"):
            select_strike(puts_only, "CE", 21600.0, criteria("STRIKE_TYPE", strike_type="ATM"))

    def test_unknown_mode_raises(self, chain):
        with pytest.raises(NotImplementedError):
            select_strike(chain, "CE", 21600.0, criteria("NOT_A_REAL_MODE"))

    def test_selection_never_invents_a_strike(self, chain):
        """Whatever the mode, the answer must exist in the chain."""
        available = set(chain["strike"])
        modes = [
            criteria("STRIKE_TYPE", strike_type="ATM"),
            criteria("STRIKE_TYPE", strike_type="OTM2"),
            criteria("CLOSEST_PREMIUM", premium=95),
            criteria("PREMIUM_LE", value=100),
            criteria("PREMIUM_GE", value=150),
            criteria("PREMIUM_RANGE", lower=60, upper=100),
            criteria("STRADDLE_WIDTH", sign="+", multiplier=0.5),
            criteria("SYNTHETIC_FUTURE", strike_type="ATM"),
            criteria("PCT_OF_ATM", pct=0.5, sign="+"),
            criteria("ATM_PREMIUM_PCT", pct=50),
        ]
        for crit in modes:
            assert select_strike(chain, "CE", 21612.2, crit) in available, f"{crit.mode} invented a strike"


class TestRealChainShape:
    """Selection must work on a chain shaped exactly like the backtest's."""

    def test_expiry_filtered_chain(self):
        chain = straddle_chain(expiry=dt.date(2024, 1, 4))
        snap = chain[(chain["expiry"] == dt.date(2024, 1, 4)) & (chain["option_type"] == "CE")]
        assert not snap.empty
        assert select_strike(snap, "CE", 21612.2, criteria("STRIKE_TYPE", strike_type="ATM")) == 21600.0

    def test_wrong_expiry_filter_yields_empty_and_raises(self):
        chain = straddle_chain(expiry=dt.date(2024, 1, 4))
        snap = chain[chain["expiry"] == dt.date(2024, 1, 11)]
        with pytest.raises(ValueError):
            select_strike(snap, "CE", 21612.2, criteria("STRIKE_TYPE", strike_type="ATM"))
