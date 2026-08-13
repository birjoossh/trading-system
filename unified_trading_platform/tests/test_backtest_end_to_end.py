"""
End-to-end backtest accuracy.

A full short-straddle backtest is replayed over the bundled 2024-01-02 NIFTY
session, then every headline number is re-derived *independently from the H5*
with plain pandas and compared. If the engine, the chain resolution and the
adapter ever disagree with the raw tick log, these tests fail.

The hand-derived reference values (spot 21612.20 at 11:00, ATM 21600, CE 121.15,
PE 81.75) come from the raw log and are re-checked here rather than assumed.
"""

import sqlite3

import pandas as pd
import pytest

from helpers import NIFTY_SYMBOL, SESSION_EXPIRY, at

STRATEGY = "atm_short_straddle_1100_1515"
ENTRY_TIME = "11:00"
EXIT_TIME = "15:15"
STRIKE_STEP = 50.0
LOT_QTY = 75


def run_backtest(h5_path, db_path):
    from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

    manager = StrategyManager(
        broker_name="paper",
        exchange="NSE",
        strategy_name=STRATEGY,
        start_date="2024-01-01",
        end_date="2024-01-31",
        db_path=db_path,
    )
    assert manager.initialize({"h5_path": str(h5_path)})
    assert manager.start()
    return manager


def leg_fingerprint(manager):
    """A comparable summary of the run's outcome."""
    return [
        (
            leg.leg_id,
            leg.strike,
            str(leg.entry_ts),
            None if leg.entry_px is None else round(leg.entry_px, 6),
            str(leg.exit_ts),
            None if leg.exit_px is None else round(leg.exit_px, 6),
            leg.exit_reason,
            round(leg.pnl, 6),
        )
        for leg in manager.strategy_engine.get_all_positions()
    ]


@pytest.fixture(scope="module")
def backtest(h5_path, tmp_path_factory):
    db = str(tmp_path_factory.mktemp("bt") / "backtest.db")
    manager = run_backtest(h5_path, db)
    yield manager, db
    manager.trading_system.shutdown()


@pytest.fixture(scope="module")
def oracle(raw_h5):
    """Reference values derived straight from the tick log with pandas."""
    spot = raw_h5[raw_h5["tsym"].astype(str) == NIFTY_SYMBOL].set_index("timestamp").sort_index(kind="stable")
    entry_bar_start = at(ENTRY_TIME)
    entry_bar_end = entry_bar_start + pd.Timedelta(minutes=1)

    window = spot.loc[(spot.index >= entry_bar_start) & (spot.index < entry_bar_end)]
    underlying_close = float(window["price"].iloc[-1])
    atm_strike = round(underlying_close / STRIKE_STEP) * STRIKE_STEP

    options = raw_h5[raw_h5["type"].astype(str).isin(["CE", "PE"])].set_index("timestamp").sort_index(kind="stable")
    premiums = {}
    for option_type in ("CE", "PE"):
        history = options[
            (options["strike"] == atm_strike)
            & (options["type"].astype(str) == option_type)
            & (options.index < entry_bar_end)
        ]
        premiums[option_type] = float(history["price"].iloc[-1])

    return {
        "underlying": underlying_close,
        "atm_strike": atm_strike,
        "premiums": premiums,
        "session_date": entry_bar_start.date(),
    }


class TestOracleSanity:
    """The oracle itself must match the values quoted in the module docstring."""

    def test_underlying_at_entry(self, oracle):
        assert oracle["underlying"] == pytest.approx(21612.20)

    def test_atm_strike(self, oracle):
        assert oracle["atm_strike"] == 21600.0

    def test_atm_premiums(self, oracle):
        assert oracle["premiums"]["CE"] == pytest.approx(121.15)
        assert oracle["premiums"]["PE"] == pytest.approx(81.75)


class TestBacktestRuns:
    def test_completes_and_opens_positions(self, backtest):
        manager, _ = backtest
        legs = manager.strategy_engine.get_all_positions()
        assert legs, "backtest produced no legs"
        assert any(leg.entry_ts is not None for leg in legs)

    def test_produces_pnl_rows(self, backtest):
        manager, _ = backtest
        assert manager.strategy_engine.rows, "no PnL rows recorded"

    def test_reports_a_portfolio_summary(self, backtest):
        manager, _ = backtest
        summary = manager.get_portfolio_summary()
        for key in ("total_pnl", "open_positions", "closed_positions", "total_positions"):
            assert key in summary
        assert summary["total_positions"] >= 2


class TestEntryMatchesTheOracle:
    def _initial_legs(self, manager):
        """The two legs the strategy opens at 11:00 (before any re-entries)."""
        legs = [leg for leg in manager.strategy_engine.get_all_positions() if leg.entry_ts is not None]
        earliest = min(leg.entry_ts for leg in legs)
        return [leg for leg in legs if leg.entry_ts == earliest]

    def test_enters_at_the_configured_time(self, backtest):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            assert leg.entry_ts.strftime("%H:%M") == ENTRY_TIME

    def test_opens_both_sides_of_the_straddle(self, backtest):
        manager, _ = backtest
        assert {leg.spec.option_type for leg in self._initial_legs(manager)} == {"CE", "PE"}

    def test_selects_the_strike_the_oracle_computes(self, backtest, oracle):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            assert leg.strike == oracle["atm_strike"], (
                f"engine chose {leg.strike}, raw data implies {oracle['atm_strike']}"
            )

    def test_entry_premiums_match_the_raw_tick_log(self, backtest, oracle):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            expected = oracle["premiums"][leg.spec.option_type]
            assert leg.entry_px == pytest.approx(expected), (
                f"{leg.spec.option_type} entry {leg.entry_px} != raw-data premium {expected}"
            )

    def test_entry_underlying_matches_the_raw_tick_log(self, backtest, oracle):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            assert leg.entry_S == pytest.approx(oracle["underlying"])

    def test_quantity_comes_from_the_strategy_config(self, backtest):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            assert leg.qty == LOT_QTY

    def test_uses_the_weekly_expiry_present_in_the_data(self, backtest):
        manager, _ = backtest
        for leg in self._initial_legs(manager):
            assert leg.expiry_date == SESSION_EXPIRY


class TestSimulatedClockIntegrity:
    """Nothing in a historical run may carry a wall-clock timestamp."""

    def test_all_entries_are_on_the_session_date(self, backtest, oracle):
        manager, _ = backtest
        for leg in manager.strategy_engine.get_all_positions():
            if leg.entry_ts is not None:
                assert leg.entry_ts.date() == oracle["session_date"]

    def test_all_exits_are_on_the_session_date(self, backtest, oracle):
        manager, _ = backtest
        for leg in manager.strategy_engine.get_all_positions():
            if leg.exit_ts is not None:
                assert leg.exit_ts.date() == oracle["session_date"]

    def test_exits_never_precede_entries(self, backtest):
        manager, _ = backtest
        for leg in manager.strategy_engine.get_all_positions():
            if leg.entry_ts is not None and leg.exit_ts is not None:
                assert leg.exit_ts >= leg.entry_ts

    def test_no_activity_before_the_entry_time(self, backtest):
        manager, _ = backtest
        cutoff = at(ENTRY_TIME).time()
        for leg in manager.strategy_engine.get_all_positions():
            if leg.entry_ts is not None:
                assert leg.entry_ts.time() >= cutoff

    def test_no_activity_after_the_session_close(self, backtest):
        manager, _ = backtest
        close = pd.Timestamp(f"{2024}-01-02 15:30:59").time()
        for leg in manager.strategy_engine.get_all_positions():
            if leg.exit_ts is not None:
                assert leg.exit_ts.time() <= close

    def test_recorded_rows_are_all_on_the_session_date(self, backtest, oracle):
        manager, _ = backtest
        dates = {pd.Timestamp(row["date"]).date() for row in manager.strategy_engine.rows}
        assert dates == {oracle["session_date"]}


class TestPnLIntegrity:
    def test_every_row_satisfies_the_pnl_formula(self, backtest):
        manager, _ = backtest
        for row in manager.strategy_engine.rows:
            mult = -1 if row["position"].lower().startswith("sell") else 1
            expected = (row["exit_price"] - row["entry_price"]) * mult * row["qty"]
            assert row["pnl"] == pytest.approx(round(expected, 2)), f"PnL formula violated in row {row}"

    def test_no_nan_or_infinite_values(self, backtest):
        manager, _ = backtest
        frame = pd.DataFrame(manager.strategy_engine.rows)
        for column in ("entry_price", "exit_price", "pnl", "underlying_price", "strike"):
            values = pd.to_numeric(frame[column], errors="coerce")
            assert values.notna().all(), f"{column} contains NaN"
            assert (values.abs() != float("inf")).all(), f"{column} contains inf"

    def test_prices_are_positive(self, backtest):
        manager, _ = backtest
        frame = pd.DataFrame(manager.strategy_engine.rows)
        assert (frame["entry_price"] > 0).all()
        assert (frame["exit_price"] >= 0).all()

    def test_underlying_stays_in_a_plausible_range(self, backtest):
        """Guards against an option premium leaking into the underlying column."""
        manager, _ = backtest
        frame = pd.DataFrame(manager.strategy_engine.rows)
        assert frame["underlying_price"].between(20_000, 23_000).all()

    def test_entry_premiums_are_option_sized_not_index_sized(self, backtest):
        manager, _ = backtest
        frame = pd.DataFrame(manager.strategy_engine.rows)
        assert (frame["entry_price"] < 5_000).all(), "an index level leaked into a premium"

    def test_exit_reasons_are_from_the_known_set(self, backtest):
        manager, _ = backtest
        allowed = {"TARGET", "SL", "TRAIL", "EOD", "TIME"}
        assert {row["exit_reason"] for row in manager.strategy_engine.rows} <= allowed

    def test_summary_total_matches_the_legs(self, backtest):
        manager, _ = backtest
        engine = manager.strategy_engine
        expected = sum(leg.pnl for leg in engine.get_all_positions() if leg.entry_ts is not None)
        assert engine.get_portfolio_summary()["total_pnl"] == pytest.approx(expected)


class TestExitBehaviour:
    def test_open_legs_are_closed_by_the_end_of_the_session(self, backtest):
        """An intraday strategy must not leave positions open past its exit time."""
        manager, _ = backtest
        legs = [leg for leg in manager.strategy_engine.get_all_positions() if leg.entry_ts is not None]
        assert legs
        for leg in legs:
            assert leg.exit_ts is not None, f"leg {leg.leg_id} was never closed"

    def test_exits_happen_at_or_before_the_exit_time_bar(self, backtest):
        manager, _ = backtest
        limit = pd.Timestamp(f"2024-01-02 {EXIT_TIME}:59").time()
        for leg in manager.strategy_engine.get_all_positions():
            if leg.exit_ts is not None and leg.exit_reason == "EOD":
                assert leg.exit_ts.time() >= at(EXIT_TIME).time()
                assert leg.exit_ts.time() <= limit

    def test_stopped_legs_lost_money_and_target_legs_made_money(self, backtest):
        """Sanity on direction: a short leg stopped out must show a loss."""
        manager, _ = backtest
        for leg in manager.strategy_engine.get_all_positions():
            if leg.entry_ts is None or leg.exit_px is None:
                continue
            if leg.exit_reason == "SL":
                assert leg.pnl < 0, f"leg {leg.leg_id} stopped out but shows a profit"
            elif leg.exit_reason == "TARGET":
                assert leg.pnl > 0, f"leg {leg.leg_id} hit target but shows a loss"


class TestPersistedRun:
    def test_run_config_row_is_written(self, backtest):
        manager, db = backtest
        with sqlite3.connect(db) as conn:
            row = conn.execute(
                "SELECT broker_name, exchange, strategy_name, status FROM run_config WHERE run_id = ?",
                (manager.run_id,),
            ).fetchone()
        assert row is not None
        broker_name, exchange, strategy_name, status = row
        assert (broker_name, exchange, strategy_name) == ("paper", "NSE", STRATEGY)
        assert status in {"INITIAL", "RUNNING", "FINISHED", "ERROR"}

    def test_strategy_tables_exist(self, backtest):
        _, db = backtest
        with sqlite3.connect(db) as conn:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"run_config", "portfolio", "strategy_profit_loss"} <= names

    def test_status_reports_the_run(self, backtest):
        manager, _ = backtest
        status = manager.get_status()
        assert status["run_id"] == manager.run_id
        assert status["strategy_name"] == STRATEGY
        assert status["is_initialized"] is True


class TestDeterminism:
    """The same inputs must produce the same run, every time."""

    def test_two_runs_agree(self, backtest, h5_path, tmp_path_factory):
        first, _ = backtest
        db = str(tmp_path_factory.mktemp("bt2") / "backtest2.db")
        second = run_backtest(h5_path, db)
        try:
            assert leg_fingerprint(second) == leg_fingerprint(first)
        finally:
            second.trading_system.shutdown()

    def test_row_counts_agree(self, backtest, h5_path, tmp_path_factory):
        first, _ = backtest
        db = str(tmp_path_factory.mktemp("bt3") / "backtest3.db")
        second = run_backtest(h5_path, db)
        try:
            assert len(second.strategy_engine.rows) == len(first.strategy_engine.rows)
            assert second.get_portfolio_summary()["total_pnl"] == pytest.approx(
                first.get_portfolio_summary()["total_pnl"]
            )
        finally:
            second.trading_system.shutdown()
