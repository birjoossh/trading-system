"""
Multi-day backtest tests.

The bundled sample is a single session, so these build small synthetic H5 files
in the sample's schema — one per day — and replay them together. That exercises
the part single-day data cannot: rolling the engine over a session boundary, so
an intraday strategy starts each day flat with a fresh expiry.
"""

import datetime as dt

import pandas as pd
import pytest

from unified_trading_platform.trading_core.brokers.paper_broker.jio import JioH5Adapter, resolve_h5_paths

pytest.importorskip("tables", reason="pytables is required to write H5 fixtures")

# Two consecutive NSE sessions, both expiring on the Thursday of that week.
DAY_ONE = dt.date(2024, 1, 2)
DAY_TWO = dt.date(2024, 1, 3)
WEEK_EXPIRY = dt.date(2024, 1, 4)
SPOT_SYMBOL = "NIFTY 50"
STRIKES = [21500.0, 21550.0, 21600.0, 21650.0, 21700.0]


def _session_frame(day: dt.date, spot: float) -> pd.DataFrame:
    """One session of ticks: the index plus a small option chain, once a minute."""
    rows = []
    start = pd.Timestamp(f"{day.isoformat()} 09:15:00")
    minutes = int((pd.Timestamp(f"{day.isoformat()} 15:30:00") - start).total_seconds() // 60)

    for minute in range(minutes + 1):
        stamp = start + pd.Timedelta(minutes=minute)
        # A gentle intraday drift so strikes and premiums move.
        level = spot + (minute % 60) - 30
        rows.append(
            {
                "timestamp": stamp,
                "price": float(level),
                "volume": 100,
                "oi": 0,
                "iid": 1,
                "tsym": SPOT_SYMBOL,
                "strike": 0.0,
                "type": "EQ",
                "expiry": pd.NaT,
                "lot": 0,
            }
        )
        for strike in STRIKES:
            for option_type in ("CE", "PE"):
                intrinsic = max(0.0, (level - strike) if option_type == "CE" else (strike - level))
                premium = round(intrinsic + 60.0 - abs(level - strike) * 0.05, 2)
                rows.append(
                    {
                        "timestamp": stamp,
                        "price": max(1.0, premium),
                        "volume": 10,
                        "oi": 0,
                        "iid": 2,
                        "tsym": f"NIFTY{day.strftime('%y%m%d')}{int(strike)}{option_type}",
                        "strike": strike,
                        "type": option_type,
                        "expiry": pd.Timestamp(WEEK_EXPIRY),
                        "lot": 50,
                    }
                )
    return pd.DataFrame(rows)


def _write_h5(path, frame: pd.DataFrame):
    frame.to_hdf(path, key="tick_data", mode="w", format="table")


@pytest.fixture(scope="module")
def two_day_dir(tmp_path_factory):
    directory = tmp_path_factory.mktemp("multiday")
    _write_h5(directory / "2024-01-02.h5", _session_frame(DAY_ONE, 21600.0))
    _write_h5(directory / "2024-01-03.h5", _session_frame(DAY_TWO, 21700.0))
    return directory


@pytest.fixture(scope="module")
def two_day_files(two_day_dir):
    return sorted(two_day_dir.glob("*.h5"))


class TestPathResolution:
    def test_single_file(self, two_day_files):
        assert resolve_h5_paths(two_day_files[0]) == [two_day_files[0]]

    def test_directory_expands_to_its_files(self, two_day_dir, two_day_files):
        assert resolve_h5_paths(two_day_dir) == two_day_files

    def test_explicit_list(self, two_day_files):
        assert resolve_h5_paths(list(two_day_files)) == two_day_files

    def test_results_are_chronological(self, two_day_dir):
        paths = resolve_h5_paths(two_day_dir)
        assert [p.name for p in paths] == sorted(p.name for p in paths)

    def test_duplicates_are_collapsed(self, two_day_files):
        first = two_day_files[0]
        assert resolve_h5_paths([first, first]) == [first]

    def test_missing_path_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_h5_paths(tmp_path / "nope.h5")

    def test_empty_directory_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            resolve_h5_paths(tmp_path)


class TestAdapterAcrossSessions:
    def test_bars_span_both_days(self, two_day_dir):
        adapter = JioH5Adapter(two_day_dir, exchange="NSE")
        bars = adapter.hist_ohlc(ticker=SPOT_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        days = set(bars["timestamp"].dt.date)
        assert days == {DAY_ONE, DAY_TWO}

    def test_option_table_spans_both_days(self, two_day_dir):
        adapter = JioH5Adapter(two_day_dir, exchange="NSE")
        table = adapter.options_table()
        days = set(pd.DatetimeIndex(table.index).date)
        assert days == {DAY_ONE, DAY_TWO}

    def test_single_file_sees_only_its_own_day(self, two_day_files):
        adapter = JioH5Adapter(two_day_files[0], exchange="NSE")
        bars = adapter.hist_ohlc(ticker=SPOT_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        assert set(bars["timestamp"].dt.date) == {DAY_ONE}

    def test_bars_stay_time_ordered_across_the_boundary(self, two_day_dir):
        adapter = JioH5Adapter(two_day_dir, exchange="NSE")
        bars = adapter.hist_ohlc(ticker=SPOT_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min")
        assert bars["timestamp"].is_monotonic_increasing


class TestEngineSessionRollover:
    def _engine(self):
        from unified_trading_platform.trading_core.strategy_engine.config import load_strategy_config
        from unified_trading_platform.trading_core.strategy_engine.live_engine import UnifiedStrategyEngine

        config = load_strategy_config("atm_short_straddle_1100_1515")
        engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
        engine.initialize(current_date=DAY_ONE, entry_time="11:00", exit_time="15:15")
        return engine

    def test_new_session_rearms_the_legs(self):
        engine = self._engine()
        engine.start_new_session(DAY_TWO)
        assert engine.current_date == DAY_TWO
        assert len(engine.live_legs) == len(engine.config.legs)
        assert all(leg.entry_ts is None for leg in engine.live_legs)

    def test_traded_legs_are_archived(self):
        from helpers import make_tick, straddle_chain

        engine = self._engine()
        chain = straddle_chain(center=21600.0, expiry=WEEK_EXPIRY)
        engine.process_tick(make_tick(pd.Timestamp(f"{DAY_ONE} 11:00"), 21600.0), 21600.0, chain)
        traded = [leg for leg in engine.live_legs if leg.entry_ts is not None]
        assert traded

        engine.start_new_session(DAY_TWO)
        assert len(engine.completed_legs) == len(traded)
        assert all(leg.entry_ts is not None for leg in engine.completed_legs)

    def test_untraded_scaffolding_is_discarded(self):
        engine = self._engine()
        engine.start_new_session(DAY_TWO)
        assert engine.completed_legs == [], "legs that never entered are not positions"

    def test_pending_reentries_do_not_leak_across_days(self):
        from unified_trading_platform.trading_core.strategy_engine.strategy_utils import PendingReEntry

        engine = self._engine()
        engine.pending_reentries.append(
            PendingReEntry(
                parent_leg_id=1,
                trigger="SL",
                mode="RE_COST",
                created_ts=pd.Timestamp(f"{DAY_ONE} 12:00"),
                spec=engine.config.legs[0],
            )
        )
        engine.start_new_session(DAY_TWO)
        assert engine.pending_reentries == []

    def test_leg_ids_stay_unique_across_sessions(self):
        engine = self._engine()
        first = [leg.leg_id for leg in engine.live_legs]
        engine.start_new_session(DAY_TWO)
        second = [leg.leg_id for leg in engine.live_legs]
        assert not set(first) & set(second), "leg ids must not repeat between sessions"

    def test_expiry_is_resolved_for_the_new_date(self):
        engine = self._engine()
        engine.start_new_session(dt.date(2024, 1, 8))  # the following week
        assert all(leg.expiry_date == dt.date(2024, 1, 11) for leg in engine.live_legs)

    def test_reporting_covers_every_session(self):
        from helpers import make_tick, straddle_chain

        engine = self._engine()
        chain = straddle_chain(center=21600.0, expiry=WEEK_EXPIRY)
        engine.process_tick(make_tick(pd.Timestamp(f"{DAY_ONE} 11:00"), 21600.0), 21600.0, chain)
        engine.start_new_session(DAY_TWO)
        engine.process_tick(make_tick(pd.Timestamp(f"{DAY_TWO} 11:00"), 21600.0), 21600.0, chain)

        traded = [leg for leg in engine.get_all_positions() if leg.entry_ts is not None]
        assert len(traded) == 4, "two legs on each of two days"
        assert engine.get_portfolio_summary()["total_positions"] >= 4


@pytest.fixture(scope="module")
def run(two_day_dir, tmp_path_factory):
    """A real two-session backtest driven through StrategyManager."""
    from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

    manager = StrategyManager(
        broker_name="paper",
        exchange="NSE",
        strategy_name="atm_short_straddle_1100_1515",
        start_date="2024-01-01",
        end_date="2024-01-31",
        db_path=str(tmp_path_factory.mktemp("md") / "run.db"),
    )
    assert manager.initialize({"h5_path": str(two_day_dir)})
    assert manager.start()
    yield manager
    manager.trading_system.shutdown()


class TestMultiDayRun:
    def test_trades_on_both_days(self, run):
        entries = {
            leg.entry_ts.date() for leg in run.strategy_engine.get_all_positions() if leg.entry_ts is not None
        }
        assert entries == {DAY_ONE, DAY_TWO}, f"expected both sessions to trade, got {entries}"

    def test_each_day_opens_the_full_straddle(self, run):
        legs = [leg for leg in run.strategy_engine.get_all_positions() if leg.entry_ts is not None]
        for day in (DAY_ONE, DAY_TWO):
            per_day = [leg for leg in legs if leg.entry_ts.date() == day]
            assert {leg.spec.option_type for leg in per_day} == {"CE", "PE"}

    def test_every_position_closes_within_its_own_day(self, run):
        for leg in run.strategy_engine.get_all_positions():
            if leg.entry_ts is None:
                continue
            assert leg.exit_ts is not None, "an intraday leg must not survive the session"
            assert leg.exit_ts.date() == leg.entry_ts.date(), "a position must not straddle two days"

    def test_entries_respect_the_entry_time_each_day(self, run):
        for leg in run.strategy_engine.get_all_positions():
            if leg.entry_ts is not None:
                assert leg.entry_ts.time() >= dt.time(11, 0)

    def test_pnl_rows_cover_both_days(self, run):
        dates = {pd.Timestamp(row["date"]).date() for row in run.strategy_engine.rows}
        assert dates == {DAY_ONE, DAY_TWO}

    def test_pnl_formula_holds_across_days(self, run):
        for row in run.strategy_engine.rows:
            mult = -1 if row["position"].lower().startswith("sell") else 1
            expected = (row["exit_price"] - row["entry_price"]) * mult * row["qty"]
            assert row["pnl"] == pytest.approx(round(expected, 2))

    def test_leg_ids_are_unique_over_the_whole_run(self, run):
        ids = [leg.leg_id for leg in run.strategy_engine.get_all_positions()]
        assert len(ids) == len(set(ids))

    def test_summary_counts_the_whole_run(self, run):
        summary = run.get_portfolio_summary()
        assert summary["total_positions"] >= 4
        assert summary["open_positions"] == 0
