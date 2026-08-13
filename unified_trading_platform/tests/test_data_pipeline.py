"""
Accuracy tests for the market-data pipeline.

Everything here is checked against the H5 tick log read directly with pandas
(the `raw_*` fixtures), never against previously recorded adapter output. The
most important test in this file is `TestNoLookahead` — a backtest that can see
future prices produces profitable nonsense, so the chain resolved at time T must
contain nothing that happened after T.
"""

import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from unified_trading_platform.trading_core.brokers.paper_broker.jio import JioH5Adapter, to_pandas_freq
from unified_trading_platform.trading_core.data.data_manager import DataManager
from unified_trading_platform.trading_core.data_models import Contract, SecurityType, TickData

from helpers import NIFTY_SYMBOL, SESSION_EXPIRY, at

SESSION = "2024-01-02"


@pytest.fixture(scope="session")
def adapter(h5_path) -> JioH5Adapter:
    return JioH5Adapter(Path(h5_path), exchange="NSE")


@pytest.fixture(scope="session")
def options_table(adapter) -> pd.DataFrame:
    return adapter.options_table()


@pytest.fixture(scope="session")
def backtest_manager(h5_path, tmp_path_factory):
    """A StrategyManager with the backtest chain caches built, but not started.

    Session-scoped: loading and pivoting 1.2M option ticks is the slowest step in
    the suite, and every consumer here only reads from it.
    """
    from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

    db = str(tmp_path_factory.mktemp("chain") / "chain.db")
    mgr = StrategyManager(
        broker_name="paper",
        exchange="NSE",
        strategy_name="atm_short_straddle_1100_1515",
        start_date="2024-01-01",
        end_date="2024-01-31",
        db_path=db,
    )
    mgr._additional_config = {"h5_path": str(h5_path)}
    mgr._load_options_for_backtest()
    mgr._build_option_chain_template()
    yield mgr
    mgr.trading_system.shutdown()


class TestFrequencyNormalisation:
    """pandas >= 2.2 renamed the hour/minute aliases; bar sizes must survive."""

    @pytest.mark.parametrize(
        "given,expected",
        [
            ("1H", "1h"),
            ("1 hour", "1h"),
            ("2 hours", "2h"),
            ("1min", "1min"),
            ("1 min", "1min"),
            ("5 mins", "5min"),
            ("15min", "15min"),
            ("30 secs", "30s"),
            ("1 sec", "1s"),
        ],
    )
    def test_normalises_to_pandas_alias(self, given, expected):
        assert to_pandas_freq(given) == expected

    @pytest.mark.parametrize("alias", ["1h", "1min", "5min", "30s"])
    def test_output_is_accepted_by_pandas(self, alias):
        assert pd.tseries.frequencies.to_offset(to_pandas_freq(alias)) is not None


class TestSpotBars:
    """hist_ohlc on the underlying must equal an independent pandas resample."""

    def _oracle_bars(self, raw_spot_ticks, freq):
        grouped = raw_spot_ticks["price"].resample(freq)
        return pd.DataFrame(
            {
                "open": grouped.first(),
                "high": grouped.max(),
                "low": grouped.min(),
                "close": grouped.last(),
            }
        ).dropna()

    @pytest.mark.parametrize("freq", ["1min", "1h"])
    def test_ohlc_matches_independent_resample(self, adapter, raw_spot_ticks, freq):
        bars = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length=freq)
        expected = self._oracle_bars(raw_spot_ticks, freq)

        assert not bars.empty
        got = bars.set_index("timestamp").sort_index()
        assert len(got) == len(expected), f"bar count differs for {freq}"

        for ts, row in expected.iterrows():
            actual = got.loc[ts]
            for field in ("open", "high", "low", "close"):
                assert float(actual[field]) == pytest.approx(float(row[field]), abs=1e-9), (
                    f"{field} mismatch in {freq} bar at {ts}"
                )

    def test_high_low_bracket_open_close(self, adapter):
        bars = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        assert (bars["high"] >= bars["low"]).all()
        assert (bars["high"] >= bars[["open", "close"]].max(axis=1)).all()
        assert (bars["low"] <= bars[["open", "close"]].min(axis=1)).all()

    def test_known_11am_bar(self, adapter):
        """Hand-checked against the raw log: the 11:00 minute closes at 21612.20."""
        bars = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        bar = bars.set_index("timestamp").loc[at("11:00")]
        assert float(bar["open"]) == pytest.approx(21616.30)
        assert float(bar["high"]) == pytest.approx(21620.50)
        assert float(bar["low"]) == pytest.approx(21612.20)
        assert float(bar["close"]) == pytest.approx(21612.20)

    def test_bars_are_time_ordered(self, adapter):
        bars = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        ts = bars["timestamp"]
        assert ts.is_monotonic_increasing

    def test_bars_stay_within_the_session(self, adapter):
        bars = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        assert bars["timestamp"].dt.date.unique().tolist() == [dt.date(2024, 1, 2)]


class TestOptionsTable:
    def test_only_contains_options(self, options_table):
        assert set(options_table["OptionType"].unique()) == {"CE", "PE"}
        assert options_table["Strike"].notna().all()
        assert (options_table["Strike"] > 0).all()

    def test_expiry_matches_the_session_contract(self, options_table):
        assert set(options_table["Expiry"].unique()) == {SESSION_EXPIRY}

    def test_strike_coverage_matches_raw_data(self, options_table, raw_option_ticks):
        expected = set(raw_option_ticks["strike"].unique())
        assert set(options_table["Strike"].unique()) == expected

    @pytest.mark.parametrize("option_type", ["CE", "PE"])
    @pytest.mark.parametrize("minute", ["11:00", "12:30", "14:45"])
    def test_price_is_the_last_tick_of_the_minute(self, options_table, raw_option_ticks, option_type, minute):
        """Aggregation is 'last' — verified against the raw ticks for that minute."""
        strike = 21600.0
        start = at(minute)
        end = start + pd.Timedelta(minutes=1)

        raw_window = raw_option_ticks[
            (raw_option_ticks["strike"] == strike)
            & (raw_option_ticks["type"].astype(str) == option_type)
            & (raw_option_ticks.index >= start)
            & (raw_option_ticks.index < end)
        ]
        if raw_window.empty:
            pytest.skip(f"no {option_type} {strike} ticks in the {minute} minute")

        row = options_table[
            (options_table["Strike"] == strike)
            & (options_table["OptionType"] == option_type)
            & (options_table.index == start)
        ]
        assert len(row) == 1
        assert float(row.iloc[0]["price"]) == pytest.approx(float(raw_window["price"].iloc[-1]))

    def test_volume_is_summed_over_the_minute(self, options_table, raw_option_ticks):
        strike, option_type, start = 21600.0, "CE", at("11:00")
        end = start + pd.Timedelta(minutes=1)
        raw_window = raw_option_ticks[
            (raw_option_ticks["strike"] == strike)
            & (raw_option_ticks["type"].astype(str) == option_type)
            & (raw_option_ticks.index >= start)
            & (raw_option_ticks.index < end)
        ]
        row = options_table[
            (options_table["Strike"] == strike)
            & (options_table["OptionType"] == option_type)
            & (options_table.index == start)
        ]
        assert int(row.iloc[0]["volume"]) == int(raw_window["volume"].sum())

    def test_known_atm_premiums_at_entry_time(self, options_table):
        """Hand-checked against the raw log at the strategy's 11:00 entry."""
        snapshot = options_table[options_table.index == at("11:00")]
        ce = snapshot[(snapshot["Strike"] == 21600.0) & (snapshot["OptionType"] == "CE")]
        pe = snapshot[(snapshot["Strike"] == 21600.0) & (snapshot["OptionType"] == "PE")]
        assert float(ce.iloc[0]["price"]) == pytest.approx(121.15)
        assert float(pe.iloc[0]["price"]) == pytest.approx(81.75)

    def test_timestamps_are_floored_to_the_minute(self, options_table):
        idx = pd.DatetimeIndex(options_table.index)
        assert (idx.second == 0).all() and (idx.microsecond == 0).all()


class TestBacktestChainResolution:
    """The forward-filled pivot the backtest uses for per-tick chain lookups."""

    def test_every_strike_has_a_price_after_forward_fill(self, backtest_manager):
        chain = backtest_manager._resolve_option_chain_for_tick(at("14:00"))
        assert not chain.empty
        assert chain["price"].notna().all()
        assert (chain["price"] > 0).all()

    def test_chain_has_both_sides(self, backtest_manager):
        chain = backtest_manager._resolve_option_chain_for_tick(at("14:00"))
        assert set(chain["option_type"].unique()) == {"CE", "PE"}

    def test_chain_columns_match_engine_expectations(self, backtest_manager):
        chain = backtest_manager._resolve_option_chain_for_tick(at("11:00"))
        for column in ("strike", "option_type", "price", "expiry", "lot"):
            assert column in chain.columns

    def test_resolves_known_entry_premiums(self, backtest_manager):
        chain = backtest_manager._resolve_option_chain_for_tick(at("11:00"))
        ce = chain[(chain["strike"] == 21600.0) & (chain["option_type"] == "CE")]
        pe = chain[(chain["strike"] == 21600.0) & (chain["option_type"] == "PE")]
        assert float(ce.iloc[0]["price"]) == pytest.approx(121.15)
        assert float(pe.iloc[0]["price"]) == pytest.approx(81.75)

    def test_timestamps_between_minutes_use_the_earlier_minute(self, backtest_manager):
        """A tick at 11:00:30 must see the 11:00 snapshot, never 11:01."""
        on_minute = backtest_manager._resolve_option_chain_for_tick(at("11:00"))
        mid_minute = backtest_manager._resolve_option_chain_for_tick(at("11:00:30"))
        pd.testing.assert_frame_equal(on_minute, mid_minute)

    def test_before_first_tick_clamps_to_first_snapshot(self, backtest_manager):
        early = backtest_manager._resolve_option_chain_for_tick(at("00:00"))
        first = backtest_manager._resolve_option_chain_for_tick(pd.Timestamp(backtest_manager._options_timestamps[0]))
        pd.testing.assert_frame_equal(early, first)

    def test_repeated_lookups_are_stable(self, backtest_manager):
        first = backtest_manager._resolve_option_chain_for_tick(at("13:15"))
        second = backtest_manager._resolve_option_chain_for_tick(at("13:15"))
        pd.testing.assert_frame_equal(first, second)


class TestNoLookahead:
    """A resolved chain must never contain information from the future.

    This is the property that decides whether backtest results mean anything.
    """

    @pytest.mark.parametrize("when", ["11:00", "12:00", "13:30", "15:00"])
    @pytest.mark.parametrize("strike", [21500.0, 21600.0, 21700.0])
    def test_price_equals_last_tick_at_or_before_now(self, backtest_manager, raw_option_ticks, when, strike):
        now = at(when)
        # The pivot is minute-bucketed, so "at or before now" means the last raw
        # tick strictly before the end of the current minute.
        cutoff = now + pd.Timedelta(minutes=1)
        chain = backtest_manager._resolve_option_chain_for_tick(now)

        for option_type in ("CE", "PE"):
            row = chain[(chain["strike"] == strike) & (chain["option_type"] == option_type)]
            if row.empty:
                continue
            resolved = float(row.iloc[0]["price"])

            history = raw_option_ticks[
                (raw_option_ticks["strike"] == strike)
                & (raw_option_ticks["type"].astype(str) == option_type)
                & (raw_option_ticks.index < cutoff)
            ]
            assert not history.empty, "chain offered a price before any tick existed"
            assert resolved == pytest.approx(float(history["price"].iloc[-1])), (
                f"{option_type} {strike} at {when}: resolved {resolved} is not the latest known price"
            )

    def test_resolved_price_is_never_a_future_only_value(self, backtest_manager, raw_option_ticks):
        """Stronger form: the value must appear in the past, and a later-only price must not leak."""
        now = at("11:30")
        cutoff = now + pd.Timedelta(minutes=1)
        chain = backtest_manager._resolve_option_chain_for_tick(now)

        checked = 0
        for row in chain.itertuples():
            past = raw_option_ticks[
                (raw_option_ticks["strike"] == row.strike)
                & (raw_option_ticks["type"].astype(str) == row.option_type)
                & (raw_option_ticks.index < cutoff)
            ]
            if past.empty:
                continue
            assert float(row.price) == pytest.approx(float(past["price"].iloc[-1]))
            checked += 1
        assert checked > 50, "expected to verify a substantial part of the chain"


class TestPaperBrokerHistoricalData:
    def test_returns_tickdata_matching_the_adapter(self, paper_system, adapter):
        bars = paper_system.get_historical_data(
            symbol=NIFTY_SYMBOL,
            exchange="NSE",
            security_type=SecurityType.STOCK,
            currency="INR",
            duration="5 D",
            bar_size="1min",
            broker_name="paper",
        )
        assert bars, "no bars returned"
        assert all(isinstance(b, TickData) for b in bars)

        expected = adapter.hist_ohlc(ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        assert len(bars) == len(expected)
        assert bars[0].close == pytest.approx(float(expected.iloc[0]["close"]))
        assert bars[-1].close == pytest.approx(float(expected.iloc[-1]["close"]))

    def test_bars_carry_contract_metadata(self, paper_system):
        bars = paper_system.get_historical_data(
            symbol=NIFTY_SYMBOL, exchange="NSE", currency="INR", duration="1 D", bar_size="1h", broker_name="paper"
        )
        assert bars
        for bar in bars[:5]:
            assert bar.symbol == NIFTY_SYMBOL
            assert bar.exchange == "NSE"
            assert bar.currency == "INR"
            assert bar.security_type == SecurityType.STOCK

    def test_hourly_bars_are_coarser_than_minute_bars(self, paper_system):
        kwargs = dict(symbol=NIFTY_SYMBOL, exchange="NSE", currency="INR", duration="1 D", broker_name="paper")
        minute = paper_system.get_historical_data(bar_size="1min", **kwargs)
        hourly = paper_system.get_historical_data(bar_size="1H", **kwargs)
        assert 0 < len(hourly) < len(minute)


class TestOptionChainRetrieval:
    def test_paper_broker_option_chain_structure(self, paper_system):
        chain = paper_system.get_option_chain(
            "paper",
            Contract(symbol="NIFTY", exchange="NSE", security_type=SecurityType.STOCK, expiry="2024-01-04"),
        )
        assert chain is not None
        assert chain.expiration_dates, "no expiries in chain"

        group = chain.expiration_dates[0]
        assert group.expiry_date == SESSION_EXPIRY
        strikes = [s.strike_price for s in group.strikes]
        assert strikes == sorted(strikes), "strikes must be sorted"
        assert len(strikes) > 50

    def test_option_chain_carries_both_sides_with_prices(self, paper_system):
        chain = paper_system.get_option_chain(
            "paper",
            Contract(symbol="NIFTY", exchange="NSE", security_type=SecurityType.STOCK, expiry="2024-01-04"),
        )
        group = chain.expiration_dates[0]
        with_both = [s for s in group.strikes if s.call_option and s.put_option]
        assert len(with_both) > 50
        for strike_group in with_both[:10]:
            assert strike_group.call_option.ltp > 0
            assert strike_group.put_option.ltp > 0

    def test_requires_h5_path(self, trading_system):
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        broker = PaperBroker()
        with pytest.raises(ValueError, match="h5_path"):
            broker.get_option_chain(Contract(symbol="NIFTY", exchange="NSE", security_type=SecurityType.STOCK))


class TestDataManagerPersistence:
    def _bar(self, ts, close):
        return TickData(
            timestamp=pd.Timestamp(ts),
            exchange="NSE",
            security_type=SecurityType.STOCK,
            symbol=NIFTY_SYMBOL,
            currency="INR",
            open=close - 5,
            high=close + 5,
            low=close - 10,
            close=close,
            volume=1000,
        )

    def test_bar_cache_round_trip(self, tmp_db):
        dm = DataManager(tmp_db)
        contract = Contract(
            symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        bars = [self._bar(f"{SESSION} 10:0{i}:00", 21600.0 + i) for i in range(5)]
        for bar in bars:
            bar.bar_size = "1min"

        dm._cache_bars(bars)
        # Duration is measured back from "now", so ask for a window that spans 2024.
        restored = dm._get_cached_bars(contract, "1min", "10000 D")

        assert len(restored) == len(bars)
        for original, back in zip(bars, restored):
            assert back.timestamp == original.timestamp
            assert back.open == pytest.approx(original.open)
            assert back.high == pytest.approx(original.high)
            assert back.low == pytest.approx(original.low)
            assert back.close == pytest.approx(original.close)
            assert back.volume == original.volume

    def test_cached_bars_are_scoped_to_the_contract(self, tmp_db):
        dm = DataManager(tmp_db)
        bar = self._bar(f"{SESSION} 10:00:00", 21600.0)
        bar.bar_size = "1min"
        dm._cache_bars([bar])

        other = Contract(symbol="BANKNIFTY", exchange="NSE", security_type=SecurityType.STOCK, currency="INR")
        assert dm._get_cached_bars(other, "1min", "10000 D") == []

    def test_cached_bars_are_scoped_to_bar_size(self, tmp_db):
        dm = DataManager(tmp_db)
        bar = self._bar(f"{SESSION} 10:00:00", 21600.0)
        bar.bar_size = "1min"
        dm._cache_bars([bar])
        contract = Contract(
            symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        assert dm._get_cached_bars(contract, "1h", "10000 D") == []

    def test_tick_storage_round_trip(self, tmp_db):
        import sqlite3

        dm = DataManager(tmp_db)
        tick = TickData(
            timestamp=pd.Timestamp(f"{SESSION} 11:00:00"),
            exchange="NSE",
            security_type=SecurityType.STOCK,
            symbol=NIFTY_SYMBOL,
            currency="INR",
            bid=21611.0,
            ask=21613.0,
            last=21612.20,
            volume=42,
        )
        dm.store_tick(tick)

        with sqlite3.connect(tmp_db) as conn:
            rows = conn.execute(
                "SELECT symbol, exchange, currency, bid, ask, last, volume FROM tick_data"
            ).fetchall()
        assert len(rows) == 1
        symbol, exchange, currency, bid, ask, last, volume = rows[0]
        assert (symbol, exchange, currency) == (NIFTY_SYMBOL, "NSE", "INR")
        assert (bid, ask, last, volume) == (21611.0, 21613.0, 21612.20, 42)

    def test_repeated_ticks_do_not_duplicate(self, tmp_db):
        import sqlite3

        dm = DataManager(tmp_db)
        tick = TickData(
            timestamp=pd.Timestamp(f"{SESSION} 11:00:00"),
            exchange="NSE",
            security_type=SecurityType.STOCK,
            symbol=NIFTY_SYMBOL,
            currency="INR",
            last=21612.20,
        )
        dm.store_tick(tick)
        dm.store_tick(tick)
        with sqlite3.connect(tmp_db) as conn:
            (count,) = conn.execute("SELECT COUNT(*) FROM tick_data").fetchone()
        assert count == 1, "same symbol+timestamp must upsert, not duplicate"


class TestBrokerResolution:
    def test_named_broker_is_used(self, paper_system):
        bars = paper_system.get_historical_data(
            symbol=NIFTY_SYMBOL, exchange="NSE", currency="INR", duration="1 D", bar_size="1h", broker_name="paper"
        )
        assert bars

    def test_single_broker_is_inferred_when_unnamed(self, paper_system):
        bars = paper_system.get_historical_data(
            symbol=NIFTY_SYMBOL, exchange="NSE", currency="INR", duration="1 D", bar_size="1h"
        )
        assert bars

    def test_unknown_broker_name_is_rejected(self, paper_system):
        with pytest.raises(ValueError, match="not found"):
            paper_system.data_manager.get_historical_data(
                Contract(symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"),
                "1 D",
                "1h",
                "no_such_broker",
                False,
            )

    def test_no_brokers_registered_is_rejected(self, trading_system):
        with pytest.raises(ValueError, match="No brokers"):
            trading_system.data_manager.get_historical_data(
                Contract(symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"),
                "1 D",
                "1h",
                None,
                False,
            )
