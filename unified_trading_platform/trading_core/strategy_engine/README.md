# Strategy Engine

Unified strategy engine supporting both live trading and backtesting through a tick-by-tick processing pipeline.

## Module Structure

| File | Purpose |
|------|---------|
| `strategy_manager.py` | Top-level orchestrator — broker setup, market data, order routing, DB logging |
| `live_engine.py` | Core `UnifiedStrategyEngine` — tick processing, entry/exit logic, position state |
| `config.py` | `StrategyConfig` dataclass + `load_strategy_config()` JSON loader |
| `strikes.py` | Strike selection (ATM, OTM, closest-premium, delta-based) |
| `strategy_utils.py` | Expiry resolution helpers (weekly, monthly, next-weekly, etc.) |
| `greeks_helper.py` | Black-Scholes pricing and Greeks (scalar + vectorized) |

## Usage

### Live Trading
```python
from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

manager = StrategyManager(
    broker_name="paper",   # broker connection (paper, ib, alpaca, etc.)
    exchange="NSE",        # exchange to trade on (NSE, NYSE, BSE, etc.)
    strategy_name="atm_short_straddle_1100_1515"
)

manager.initialize()
manager.start()         # runs until exit_time or manual stop

status = manager.get_status()
portfolio = manager.get_portfolio_summary()
```

### Backtesting
```python
manager = StrategyManager(
    broker_name="paper",
    exchange="NSE",
    strategy_name="atm_short_straddle_1100_1515",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

manager.initialize()
manager.start()         # processes all historical data
```

> **Note:** `broker_name` and `exchange` are separate concepts — `broker_name` selects the connection method, `exchange` selects the trading market. A single broker can connect to multiple exchanges.

## Strategy Configuration

Strategies are defined as JSON files in `../strategies/`. Required top-level fields:

```json
{
  "strategy_type": "Intraday",
  "symbol": "NIFTY 50",
  "currency": "INR",
  "underlying_from": "Cash",
  "entry_time": "11:00",
  "exit_time": "15:15",
  "lot_size": 75,
  "legs": [
    {
      "segment": "Options",
      "position": "Sell",
      "option_type": "CE",
      "expiry": "Weekly",
      "qty_lots": 1,
      "strike_criteria": {
        "mode": "STRIKE_TYPE",
        "params": { "strike_type": "ATM", "symbol": "NIFTY", "strike_step": 50 }
      },
      "risk": {
        "target": { "enabled": true, "basis": "premium_pct", "value": 30 },
        "sl": { "enabled": true, "basis": "premium_pct", "value": 25 }
      },
      "reentry_on_sl": { "enabled": true, "mode": "RE_ASAP", "max_count": 1 }
    }
  ]
}
```

> **`symbol` and `currency` are required** — the engine will raise a `ValueError` if either is missing from the JSON.

### Strike Selection Modes

| Mode | Description | Key Params |
|------|-------------|------------|
| `STRIKE_TYPE` | ATM, ITM1-5, OTM1-5 | `strike_type`, `symbol`, `strike_step` |
| `CLOSEST_PREMIUM` | Nearest to target premium | `premium`, `symbol`, `strike_step` |
| `CLOSEST_DELTA` | Nearest to target delta | `delta`, `symbol`, `strike_step` |
| `PREMIUM_RANGE` | Within premium range | `value`, `symbol`, `strike_step` |

### Re-entry Modes

| Mode | Behavior |
|------|----------|
| `RE_ASAP` | Re-enter immediately at current market price |
| `RE_COST` | Re-enter only at or better than original entry price |
| `RE_MOMENTUM` | Re-enter based on momentum indicators |

## Database Schema

### RUN_CONFIG
| Column | Description |
|--------|-------------|
| `run_id` | Unique run identifier (UUID) |
| `broker_name` | Broker connection used |
| `exchange` | Exchange traded on |
| `strategy_name` | Strategy config name |
| `start_date` / `end_date` | Backtesting period (nullable) |
| `status` | `INITIAL` → `RUNNING` → `FINISHED` / `ERROR` |
| `initial_portfolio` | Starting portfolio state (JSON) |

### PORTFOLIO
Periodic portfolio snapshots: `positions` (JSON), `cash_balance`, `total_value`.

### STRATEGY_PROFIT_LOSS
Performance tracking: `realized_pnl`, `unrealized_pnl`, `total_pnl`, `num_trades`, `win_count`, `loss_count`.

## Exit Conditions

1. **Time-based** — exit at `exit_time` from strategy config
2. **Manual** — `manager.stop()`
3. **Data exhaustion** — all historical ticks processed (backtesting)
4. **Error** — automatic stop with status logged to DB

## Design Principles

- **Explicit configuration** — no hardcoded symbols, exchanges, or currencies; everything flows from config
- **Broker ≠ Exchange** — `broker_name` (connection) and `exchange` (market) are always separate parameters
- **Exchange-aware** — expiry logic, trading hours, and currency are resolved from exchange-specific config
- **Unified pipeline** — same `UnifiedStrategyEngine` processes both live ticks and historical data
- **Queue-based** — thread-safe tick ingestion for high-frequency data
