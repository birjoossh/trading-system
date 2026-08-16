#!/usr/bin/env bash
# Replay a strategy over recorded H5 data and print the result.
#
# Usage: scripts/run-backtest.sh [STRATEGY] [H5_PATH] [START_DATE] [END_DATE]
#   scripts/run-backtest.sh                          # bundled sample session
#   scripts/run-backtest.sh otm2_short_strangle_1100_1515
#   scripts/run-backtest.sh atm_short_straddle_1100_1515 ~/data/nifty 2024-01-01 2024-01-31
#
# H5_PATH may be a single file, or a directory of *.h5 files to replay several
# sessions in order. Strategy names are the JSON filenames (without .json) in
# unified_trading_platform/trading_core/strategies/.

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

STRATEGY="${1:-atm_short_straddle_1100_1515}"
DATA="${2:-unified_trading_platform/examples/2024-01-02.h5}"
START="${3:-2024-01-01}"
END="${4:-2024-01-31}"
EXCHANGE="${EXCHANGE:-NSE}"

echo "==> Backtesting '$STRATEGY' on $DATA ($START to $END)"

exec "$PYTHON" - "$STRATEGY" "$DATA" "$START" "$END" "$EXCHANGE" <<'PY'
import sys

from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

strategy, data, start, end, exchange = sys.argv[1:6]

manager = StrategyManager(
    broker_name="paper",
    exchange=exchange,
    strategy_name=strategy,
    start_date=start,
    end_date=end,
)
manager.initialize({"h5_path": data})
manager.start()

summary = manager.get_portfolio_summary()
print("\n=== Result ===")
for key, value in summary.items():
    print(f"{key:>20}: {value}")

for leg in manager.strategy_engine.get_all_positions():
    if leg.entry_ts is None:
        continue
    print(
        f"  leg {leg.leg_id}: {leg.spec.position} {leg.spec.option_type} @ {leg.strike}"
        f"  entry {leg.entry_px} ({leg.entry_ts})"
        f"  exit {leg.exit_px} ({leg.exit_reason})"
        f"  pnl {leg.pnl:.2f}"
    )

manager.trading_system.shutdown()
PY
