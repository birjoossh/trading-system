# Strategy Engine Module Documentation

This directory (`trading_core/strategy_engine`) contains the core logic for the trading strategies.

## File Structure

| File | Purpose |
|------|---------|
| **`strategy_manager.py`** | **Service Layer**. The main entry point. Orchestrates the interaction between the `TradingSystem` (Broker/Data) and the `UnifiedStrategyEngine`. Handles lifecycle (Init, Start, Stop). |
| **`live_engine.py`** | **Core Logic**. Contains `UnifiedStrategyEngine`. Implements the tick-by-tick state machine, entry/exit signal generation, and position management. |
| **`config.py`** | **Data Models**. Defines Pydantic models for Strategy Configuration (`StrategyConfig`, `LegSpec`, `RiskConfig`). |
| **`strategy_utils.py`** | **Helpers**. Contains pure logic functions for lifecycle management (`_hit_target`, `_hit_stop`), expiry calculation, and shared data structures (`LiveLeg`). (Formerly `engine.py`) |
| **`strikes.py`** | **Strike Selection**. Logic for selecting strikes based on Delta or ATM offset. |
| **`greeks_helper.py`** | **Math**. Utility functions for calculating/estimating Option Greeks. |

## relationships
`StrategyManager` -> initializes -> `UnifiedStrategyEngine` (`live_engine.py`)
`UnifiedStrategyEngine` -> uses -> `strategy_utils.py`, `strikes.py`, `config.py`
