"""
End-to-end backtest smoke test: replays the bundled 2024-01-02 NIFTY H5 sample
through StrategyManager with the paper broker and checks the run produces
sane, fully-simulated results.
"""

import os
from pathlib import Path

import pytest

H5_PATH = Path(__file__).resolve().parent.parent / "examples" / "2024-01-02.h5"


@pytest.mark.skipif(not H5_PATH.exists(), reason="sample H5 data not available")
def test_short_straddle_backtest(tmp_path):
    os.chdir(Path(__file__).resolve().parent.parent.parent)  # repo root, so config.yaml resolves
    from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

    manager = StrategyManager(
        broker_name="paper",
        exchange="NSE",
        strategy_name="atm_short_straddle_1100_1515",
        start_date="2024-01-01",
        end_date="2024-01-31",
        db_path=str(tmp_path / "test.db"),
    )
    assert manager.initialize({"h5_path": str(H5_PATH)})
    assert manager.start()

    engine = manager.strategy_engine
    legs = engine.get_all_positions()
    entered = [leg for leg in legs if leg.entry_ts is not None]
    assert entered, "no legs entered"

    for leg in entered:
        # Entry time gate: strategy is configured to enter at 11:00
        assert leg.entry_ts.time().hour >= 11
        # All bookkeeping must stay inside the simulated day (no wall-clock leakage)
        assert leg.entry_ts.date().isoformat() == "2024-01-02"
        assert leg.entry_px and leg.entry_px > 0
        if leg.exit_ts is not None:
            assert leg.exit_ts.date().isoformat() == "2024-01-02"
            assert leg.exit_px and leg.exit_px > 0

    summary = engine.get_portfolio_summary()
    assert summary["total_positions"] == len(entered)
    assert summary["closed_positions"] >= 2  # both straddle legs exit by 15:15

    manager.stop()
    manager.trading_system.shutdown()
