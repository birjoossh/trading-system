# Strategy Engine Implementation

This directory contains the unified strategy engine implementation that supports both live trading and backtesting through a tick-by-tick processing pipeline.

## Architecture Overview

The strategy engine consists of several key components:

### 1. StrategyManager
The main orchestrator that coordinates all components:
- **Initialization**: Loads strategy config, connects to broker, sets up database
- **Execution**: Manages tick processing, order submission, and portfolio tracking
- **State Management**: Tracks run status, portfolio, and PnL

### 2. UnifiedStrategyEngine
The core strategy logic engine:
- **Tick Processing**: Evaluates buy/sell signals on each tick
- **Risk Management**: Implements stop-loss, take-profit, and trailing stops
- **Re-entry Logic**: Handles position re-entries based on strategy rules
- **Position Tracking**: Maintains state of all open and closed positions

### 3. Database Integration
Three main tables for tracking:
- **RUN_CONFIG**: Strategy run configuration and status
- **PORTFOLIO**: Portfolio snapshots over time
- **STRATEGY_PROFIT_LOSS**: PnL tracking and performance metrics

## Key Features

### Unified Processing
- Single engine handles both live and historical data
- Tick-by-tick processing for accurate strategy evaluation
- Queue-based architecture for handling high-frequency data

### Risk Management
- Configurable stop-loss and take-profit rules
- Trailing stop functionality
- Re-entry logic with multiple modes (ASAP, COST, MOMENTUM)
- Position sizing and lot management

### Strategy Configuration
- JSON-based strategy definitions
- Support for complex multi-leg strategies
- Flexible strike selection criteria
- Customizable risk parameters

### Broker Integration
- Unified interface across multiple brokers
- Real-time market data subscription
- Historical data fetching for backtesting
- Order management and execution

## Usage Examples

### Live Trading
```python
from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

# Create strategy manager
manager = StrategyManager(
    venue="paper",  # or "ib", "alpaca", etc.
    strategy_name="atm_short_straddle_1100_1515"
)

# Initialize and start
manager.initialize()
manager.start()  # Runs until exit_time or manual stop

# Check status
status = manager.get_status()
portfolio = manager.get_portfolio_summary()
```

### Backtesting
```python
# Historical backtesting
manager = StrategyManager(
    venue="paper",
    strategy_name="atm_short_straddle_1100_1515",
    start_date="2024-01-01",
    end_date="2024-01-31"
)

manager.initialize()
manager.start()  # Processes all historical data
```

## Strategy Configuration

Strategies are defined in JSON files in the `strategies/` directory. Example:

```json
{
  "strategy_type": "Intraday",
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
        "params": { "strike_type": "ATM", "symbol": "NIFTY" }
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

## Database Schema

### RUN_CONFIG Table
- `run_id`: Unique identifier for each strategy run
- `venue`: Broker name (paper, ib, etc.)
- `strategy_name`: Strategy configuration name
- `start_date`/`end_date`: For backtesting periods
- `status`: INITIAL, RUNNING, FINISHED, ERROR
- `initial_portfolio`: Starting portfolio state

### PORTFOLIO Table
- `portfolio_id`: Unique identifier
- `run_id`: Links to strategy run
- `positions`: JSON serialized position data
- `cash_balance`: Available cash
- `total_value`: Total portfolio value

### STRATEGY_PROFIT_LOSS Table
- `pnl_id`: Unique identifier
- `run_id`: Links to strategy run
- `realized_pnl`: Realized profit/loss
- `unrealized_pnl`: Unrealized profit/loss
- `total_pnl`: Total PnL
- `num_trades`: Number of trades executed
- `win_count`/`loss_count`: Win/loss statistics

## Exit Conditions

The strategy manager supports multiple exit conditions:

1. **Time-based**: Exit at specified time (from strategy config)
2. **Manual stop**: User-initiated stop via `stop()` method
3. **Data exhaustion**: All historical data processed (backtesting)
4. **Error conditions**: Automatic stop on errors

## Error Handling

- Comprehensive error logging and database tracking
- Graceful degradation on broker disconnections
- Automatic status updates on errors
- Recovery mechanisms for transient failures

## Performance Considerations

- Queue-based processing for high-frequency data
- Efficient database operations with batching
- Memory-efficient position tracking
- Thread-safe operations for concurrent access

## Testing

The implementation includes:
- Unit tests for strategy engine logic
- Integration tests with paper broker
- Performance tests for high-frequency scenarios
- Error handling and recovery tests

## Future Enhancements

- Real-time performance monitoring
- Advanced risk management features
- Machine learning integration
- Multi-strategy portfolio management
- Enhanced reporting and analytics
