"""
Replay speed, and the guarantee that speed does not change results.

Backtests used to crawl because the paper broker slept between every replayed
tick and again before every fill. Those pauses simulate exchange latency; they
are not part of the strategy's logic, so removing them must leave the numbers
identical. The equivalence tests here are the ones that matter — the timing
assertions only stop the delays creeping back in as defaults.
"""

import threading
import time

import pytest

from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker
from unified_trading_platform.trading_core.brokers.paper_broker.jio import (
    JioH5Adapter,
    clear_tick_cache,
)
from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.data_models import (
    Contract,
    Order,
    OrderAction,
    OrderStatus,
    OrderType,
    SecurityType,
)

from helpers import NIFTY_SYMBOL

STRATEGY = "atm_short_straddle_1100_1515"


def nifty_contract():
    return Contract(
        symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
    )


def limit_order(price=100.0, action=OrderAction.BUY, quantity=75):
    return Order(action=action, quantity=quantity, order_type=OrderType.LIMIT, limit_price=price)


class TestDefaultsAreFast:
    """Replay should run at full speed unless somebody asks for pacing."""

    def test_config_defaults_to_no_delay(self):
        assert float(settings.get("brokers.paper_broker.fill_delay_s")) == 0.0
        assert float(settings.get("brokers.paper_broker.emit_interval_s")) == 0.0

    def test_db_tailer_keeps_a_poll_interval(self):
        """The SQLite tailer polls for new rows; 0 there would spin a core."""
        assert float(settings.get("brokers.paper_broker.poll_interval_s")) > 0

    def test_broker_picks_up_the_fast_defaults(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path))
        assert broker.config.fill_delay_s == 0.0
        assert broker.config.emit_interval_s == 0.0
        assert broker.config.poll_interval_s > 0

    def test_pacing_can_still_be_requested(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path), emit_interval_s=0.25, fill_delay_s=0.5)
        assert broker.config.emit_interval_s == 0.25
        assert broker.config.fill_delay_s == 0.5


class TestImmediateFills:
    """A fill with no simulated latency must not be lost.

    The broker reports it during submit_order(), before the order manager has
    registered the order, so the status has nowhere to land unless it is held.
    """

    def test_order_fills_without_any_delay(self, trading_system, h5_path):
        trading_system.add_broker(name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=0.0)
        order_id = trading_system.order_manager.submit_order(nifty_contract(), limit_order(), "paper")

        status = trading_system.get_order_status(order_id)
        assert status["status"] == OrderStatus.FILLED.value
        assert status["filled_quantity"] == 75
        assert status["avg_fill_price"] == pytest.approx(100.0)

    def test_fill_callback_fires_without_delay(self, trading_system, h5_path):
        trading_system.add_broker(name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=0.0)
        filled = []
        trading_system.register_order_callback("order_filled", filled.append)

        trading_system.order_manager.submit_order(nifty_contract(), limit_order(), "paper")
        assert len(filled) == 1, "the fill callback must fire even with no latency"

    def test_early_status_buffer_is_drained(self, trading_system, h5_path):
        """Nothing should be left waiting once the order is registered."""
        trading_system.add_broker(name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=0.0)
        trading_system.order_manager.submit_order(nifty_contract(), limit_order(), "paper")
        assert trading_system.order_manager._early_status == {}

    def test_status_for_an_unknown_order_is_held_not_dropped(self, trading_system):
        manager = trading_system.order_manager
        manager._on_order_status("never-submitted", {"status": OrderStatus.FILLED, "filled": 5})
        assert "never-submitted" in manager._early_status

    def test_delayed_fill_still_works(self, trading_system, h5_path):
        """The asynchronous path must keep working for anyone simulating latency."""
        trading_system.add_broker(name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=0.05)
        order_id = trading_system.order_manager.submit_order(nifty_contract(), limit_order(), "paper")

        deadline = time.time() + 5
        while time.time() < deadline:
            if trading_system.get_order_status(order_id)["status"] == OrderStatus.FILLED.value:
                break
            time.sleep(0.01)
        assert trading_system.get_order_status(order_id)["status"] == OrderStatus.FILLED.value

    def test_caller_can_choose_the_order_id(self, trading_system, h5_path):
        """Lets a caller register bookkeeping before a synchronous fill arrives."""
        trading_system.add_broker(name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=0.0)
        chosen = "my-own-correlation-id"
        returned = trading_system.order_manager.submit_order(
            nifty_contract(), limit_order(), "paper", order_id=chosen
        )
        assert returned == chosen
        assert trading_system.get_order_status(chosen)["order_id"] == chosen


def _run_backtest(h5_path, db_path, **broker_kwargs):
    """Run the reference strategy and return a comparable summary of the result."""
    from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

    manager = StrategyManager(
        broker_name="paper",
        exchange="NSE",
        strategy_name=STRATEGY,
        start_date="2024-01-01",
        end_date="2024-01-31",
        db_path=str(db_path),
    )
    manager.initialize({"h5_path": str(h5_path), **broker_kwargs})
    manager.start()
    fingerprint = [
        (
            leg.leg_id,
            leg.strike,
            str(leg.entry_ts),
            round(leg.entry_px or 0.0, 6),
            str(leg.exit_ts),
            round(leg.exit_px or 0.0, 6),
            leg.exit_reason,
            round(leg.pnl, 6),
        )
        for leg in manager.strategy_engine.get_all_positions()
    ]
    summary = manager.get_portfolio_summary()
    rows = len(manager.strategy_engine.rows)
    manager.trading_system.shutdown()
    return fingerprint, summary, rows


@pytest.fixture(scope="module")
def instant(h5_path, tmp_path_factory):
    return _run_backtest(h5_path, tmp_path_factory.mktemp("instant") / "a.db", fill_delay_s=0.0)


@pytest.fixture(scope="module")
def delayed(h5_path, tmp_path_factory):
    return _run_backtest(h5_path, tmp_path_factory.mktemp("delayed") / "b.db", fill_delay_s=0.25)


class TestResultsAreUnchangedByTiming:
    """The headline guarantee: pacing changes duration, never output."""

    def test_positions_are_identical(self, instant, delayed):
        assert instant[0] == delayed[0], "simulated fill latency changed the positions"

    def test_pnl_is_identical(self, instant, delayed):
        assert instant[1]["total_pnl"] == pytest.approx(delayed[1]["total_pnl"])

    def test_row_counts_are_identical(self, instant, delayed):
        assert instant[2] == delayed[2]

    def test_the_run_still_produces_the_known_entries(self, instant):
        """Cross-check against the hand-verified values from the raw tick log."""
        entries = {(leg[1], leg[3]) for leg in instant[0] if leg[3]}
        assert (21600.0, 121.15) in entries, "CE entry no longer matches the raw data"
        assert (21600.0, 81.75) in entries, "PE entry no longer matches the raw data"


class TestTickCache:
    """The same H5 is parsed for the chain and again for the bars; cache it."""

    def test_repeated_reads_return_equal_frames(self, h5_path):
        clear_tick_cache()
        first = JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        second = JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        assert first.shape == second.shape
        assert list(first.columns) == list(second.columns)
        assert first["price"].equals(second["price"])

    def test_second_read_is_faster(self, h5_path):
        clear_tick_cache()
        start = time.perf_counter()
        JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        cold = time.perf_counter() - start

        start = time.perf_counter()
        JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        warm = time.perf_counter() - start
        assert warm < cold, f"cached read ({warm:.3f}s) should beat the parse ({cold:.3f}s)"

    def test_callers_cannot_corrupt_the_cache(self, h5_path):
        """Each caller gets its own frame; hist_ohlc mutates what it is given."""
        clear_tick_cache()
        first = JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        first["price"] = -1.0

        second = JioH5Adapter(h5_path, exchange="NSE")._read_tick()
        assert (second["price"] != -1.0).any(), "a mutation leaked into the cache"

    def test_a_changed_file_is_re_read(self, tmp_path):
        """The key includes size and mtime, so edited data is never served stale."""
        pytest.importorskip("tables")
        import pandas as pd

        path = tmp_path / "day.h5"

        def write(price):
            pd.DataFrame(
                {
                    "timestamp": [pd.Timestamp("2024-01-02 09:15:00")],
                    "price": [price],
                    "volume": [1],
                    "oi": [0],
                    "iid": [1],
                    "tsym": ["NIFTY 50"],
                    "strike": [0.0],
                    "type": ["EQ"],
                    "expiry": [pd.NaT],
                    "lot": [0],
                }
            ).to_hdf(path, key="tick_data", mode="w", format="table")

        clear_tick_cache()
        write(100.0)
        assert JioH5Adapter(path, exchange="NSE")._read_tick()["price"].iloc[0] == 100.0

        time.sleep(0.01)
        write(200.0)
        assert JioH5Adapter(path, exchange="NSE")._read_tick()["price"].iloc[0] == 200.0

    def test_adapter_output_matches_after_caching(self, h5_path):
        """Cached input must give the same bars as a cold parse."""
        clear_tick_cache()
        cold = JioH5Adapter(h5_path, exchange="NSE").hist_ohlc(
            ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min"
        )
        warm = JioH5Adapter(h5_path, exchange="NSE").hist_ohlc(
            ticker=NIFTY_SYMBOL, exchange="NSE", opt_type="EQ", bar_length="1min"
        )
        import pandas as pd

        pd.testing.assert_frame_equal(cold, warm)


class TestStreamingThroughput:
    """A replay with no pacing should be limited by work, not by sleeping."""

    def test_ticks_stream_far_faster_than_realtime(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path))
        broker.connect()
        try:
            seen, done, started = [], threading.Event(), []
            limit = 2000

            def on_tick(tick):
                if not seen:
                    started.append(time.perf_counter())
                seen.append(tick)
                if len(seen) >= limit:
                    done.set()

            broker.subscribe_market_data(nifty_contract(), on_tick)
            assert done.wait(timeout=120), "replay did not deliver ticks in time"
            elapsed = time.perf_counter() - started[0]
        finally:
            broker.disconnect()

        rate = len(seen) / elapsed
        # The old default paced at 0.5s/tick, i.e. 2 ticks/sec.
        assert rate > 200, f"replay only managed {rate:,.0f} ticks/sec"

    def test_pacing_is_honoured_when_asked_for(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path), emit_interval_s=0.05)
        broker.connect()
        try:
            seen, done = [], threading.Event()

            def on_tick(tick):
                seen.append(tick)
                if len(seen) >= 3:
                    done.set()

            start = time.perf_counter()
            broker.subscribe_market_data(nifty_contract(), on_tick)
            assert done.wait(timeout=120)
            elapsed = time.perf_counter() - start
        finally:
            broker.disconnect()

        assert elapsed >= 0.1, "explicit pacing should still slow the replay down"
