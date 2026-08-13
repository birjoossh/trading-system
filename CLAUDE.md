# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A modular Python algorithmic trading system (`unified_trading_platform`) built around a broker-agnostic core. It provides historical/real-time market data, order management, and an options-strategy engine, exposed both as a Python library and as a FastAPI HTTP gateway. Interactive Brokers (via `ibapi`) and an internal paper broker are the two implemented brokers; the strategy engine is purpose-built for Indian NSE index-options strategies (straddles, strangles, iron condors, credit/debit spreads).

The package root is `unified_trading_platform/`, not the repo root — all internal imports are absolute, e.g. `from unified_trading_platform.trading_core.trading_system import TradingSystem`. Run scripts from the repo root so this import path resolves.

## Commands

```bash
# Install
pip install -r requirements.txt
pip install -e .              # optional, installs the package in editable mode

# Lint (ruff is the only configured linter; see pyproject.toml — py310, line-length 120)
ruff check .
ruff check --fix .

# Run the FastAPI gateway
python -m unified_trading_platform.api                      # uvicorn on 0.0.0.0:8000, reload on
python unified_trading_platform/examples/run_api.py --reload --port 8000

# Run a library example directly (most "examples" are standalone scripts, not pytest)
python unified_trading_platform/examples/example_ib.py
python unified_trading_platform/examples/example_paper_broker.py
python unified_trading_platform/examples/example_strategy_manager.py

# The only pytest-discoverable tests live under examples/ (test_*.py with def test_*).
# tests/ at the package root is currently an empty placeholder.
pytest unified_trading_platform/examples/test_greeks.py
pytest unified_trading_platform/examples/test_exchange_config.py
pytest unified_trading_platform/examples/ -k test_          # both together

# test_options.py / test_strategy_components.py in examples/ are NOT pytest suites
# despite the name — they're runnable scripts:
python unified_trading_platform/examples/test_options.py
```

There is no CI config, formatter (black/isort), or type checker wired up in this repo — `ruff check` is the full extent of automated code-quality tooling.

## Architecture

### Layering

```
api/            FastAPI HTTP gateway (thin layer over trading_core)
trading_core/   All business logic — usable as a standalone library without the API
examples/       Runnable scripts and the only pytest-discovered tests
docs/           Design notes (strategy_engine.md is the most useful one)
frontend/       Empty placeholder (no code yet)
scripts/        Empty placeholder (no code yet)
```

`TradingSystem` (`trading_core/trading_system.py`) is the central facade: it owns one `DataManager`, one `OrderManager`, one `EventEngine`, and a `{name: BrokerInterface}` map of connected brokers. Almost everything else is reached through it. Both `api/endpoints/*` and `strategy_engine/strategy_manager.py` drive the system exclusively through this facade rather than talking to brokers/managers directly.

### Broker abstraction

- `trading_core/brokers/base_broker.py` — `BrokerInterface` ABC. Every broker must implement connect/disconnect, historical data, order submission/cancel, positions, account info, market-data subscribe/unsubscribe, contract details, option chain, and greeks.
- `trading_core/brokers/broker_factory.py` — `BrokerFactory` is a class-level registry (`register_broker(name, cls)` / `create_broker(name, **kwargs)`). Brokers self-register at import time, at the bottom of `broker_factory.py` (`"ib"`/`"interactive_brokers"` → `IBBroker`, `"paper"` → `PaperBroker`). Adding a new broker means: implement `BrokerInterface`, then add a `register_broker(...)` call in this file — nothing else needs to know about it.
- `trading_core/brokers/interactive_brokers/` — `IBBroker` wraps `IBClient` (raw `ibapi` EWrapper/EClient) via `IBRequestManager`, which bridges the async, callback-driven `ibapi` protocol to synchronous-looking calls using per-request `Future`s: `IBClient` asks the manager for a `reqId` + `Future`, sends the request, accumulates callback data as it streams in, and resolves the `Future` when the matching "End" callback (e.g. `contractDetailsEnd`) arrives. When touching IB code, preserve this reqId → Future → resolve-on-End pattern rather than adding new blocking/polling loops.
- `trading_core/brokers/paper_broker/` — simulated broker for backtesting/dev without a live IB connection; `jio.py` (`JioH5Adapter`) reads historical tick/options data out of local HDF5 files for backtests.

### Event flow (real-time data)

`trading_core/event_system.py` provides a minimal `EventEngine`: a background thread draining a `queue.Queue`, dispatching to handlers registered per `EventType` (`TICK`, `BAR`, `ORDER_STATUS`, `TRADE`, `ERROR`, `LOG`). `TradingSystem.subscribe_market_data` wraps the caller's callback in a producer that pushes a `TICK` event onto the engine instead of calling back synchronously from the broker thread; `TradingSystem._process_tick_event` is the sole `TICK` handler and both persists the tick via `DataManager` and invokes the user's callback. This decouples broker network threads from strategy/DB code — don't call user callbacks directly from broker threads; go through the event engine.

### Data and order persistence

`DataManager` and `OrderManager` each open their own `sqlite3` connection and create their own tables (`historical_bars`/`tick_data` vs. `orders`/`trades`) but are constructed with the *same* `db_path` (default `trading_system2.db`, set on `TradingSystem.__init__`), so in practice both live in one SQLite file. `strategy_engine/database/db_utils` (`init_strategy_tables`, `create_run_config`, `save_portfolio_snapshot`, `save_pnl_snapshot`, ...) adds a third set of tables (`run_config`, `portfolio`, `strategy_profit_loss`) to that same file for strategy-run bookkeeping. When adding persistence, follow this pattern (raw `sqlite3`, `CREATE TABLE IF NOT EXISTS`, JSON-serialized blobs for nested structures) rather than introducing an ORM.

### Strategy engine (`trading_core/strategy_engine/`)

See `docs/strategy_engine.md` for the authoritative file-by-file breakdown; summary:
- `strategy_manager.py` — service layer / orchestrator. Owns a `TradingSystem`, initializes a `UnifiedStrategyEngine`, and runs either **live mode** (subscribes to real market data, processes ticks off a queue on a background thread) or **backtest mode** (loads a strategy's historical option chain once via `JioH5Adapter`, pre-builds a forward-filled price pivot table for O(1)/O(log n) chain lookups per tick via `bisect`, then replays historical bars tick-by-tick through the same `_process_tick` path used live). Keeping live and backtest on the same `_process_tick` code path is intentional — new signal/exit logic should go into `UnifiedStrategyEngine`, not be duplicated per mode.
- `live_engine.py` — `UnifiedStrategyEngine`: the tick-by-tick state machine (entries, exits, re-entries, PnL).
- `config.py` — dataclass models for strategy configuration (`StrategyConfig`, `LegSpec`, `RiskConfig`, `ReEntryRule`, ...) loaded from JSON files in `trading_core/strategies/*.json` via `load_strategy_config(strategy_name)`. `symbol` and `currency` are required fields in the JSON (no default — loading fails loudly without them). See `trading_core/strategies/Examples_README.md` and the existing `*.json` files there for the schema (multi-leg option strategies: strike-selection criteria, per-leg target/SL/trailing risk rules, re-entry rules, trail-to-breakeven).
- `strategy_utils.py`, `strikes.py`, `greeks_helper.py` — pure-logic helpers (exit condition checks, strike selection by delta/ATM offset, Black-Scholes pricing/greeks). Prefer adding pure functions here over the manager/engine classes.

### Configuration

`config.yaml` at the repo root is the single source of truth, loaded by `trading_core/config/config.py` into a module-level `settings` singleton (`Config` class, dot-path `get`/`set`, e.g. `settings.get("system.default_exchange")`). Env var overrides use the `TRADING_CONFIG__SECTION__KEY` prefix (double underscore = path separator), not the `TRADING_SYSTEM_...` prefix or pydantic-settings described in older docs — that part of the README/docs is stale. `api/config.py`'s `APIConfig` is a thin wrapper around the same `settings` object that remaps a few legacy short key names (e.g. `broker.default_host` → `brokers.interactive_brokers.host`) for the API layer; it doesn't load config independently. Config sections: `system` (limits/timeouts), `exchanges` (per-exchange trading hours, currency, expiry-weekday rules — see `docs/exchange_config.md`), `logging`, `database`, `brokers`, `api` (FastAPI metadata), `defaults` (contract/data/portfolio defaults).

`TradingSystem.__init__` calls `_validate_config()` and raises `ValueError` at startup if `system.default_exchange` isn't set or has no matching entry under `exchanges`. Keep `config.yaml`'s `exchanges` section and `system.default_exchange` in sync when editing either.

### API layer (`api/`)

FastAPI app assembled in `api/main.py` from config-driven metadata (title/version/docs URLs all come from `config.yaml`'s `api.*` section, not hardcoded). Routers live under `api/endpoints/` (`health`, `brokers`, `data`, `orders`, `strategies`), request/response schemas under `api/models/`. `api/runtime.py` presumably holds the shared runtime state (broker connections, running strategies) the endpoints operate on — check there before assuming a `TradingSystem` instance must be constructed per-request.

### Data models

`trading_core/data_models/` holds the shared domain types (`Contract`, `Order`, `TickData`, `OptionChain`, `Greeks`, `Position`, `Trade`, enums for security type / order type / tick type / option right). These are imported throughout `trading_core` and `api/models` — treat them as the canonical vocabulary rather than redefining similar shapes elsewhere.

## Conventions

- All cross-module imports are absolute from the package root: `from unified_trading_platform.trading_core.<module> import ...`.
- Logging goes through `trading_core/utils/logger.py`'s `get_logger(__name__)`, not `print()` or the stdlib `logging` module directly.
- Broker, data, and order errors are generally caught, logged with `exc_info=True`, and turned into a return value (`False`/`{}`/raised `ValueError`) rather than left to propagate raw — follow the existing pattern in `TradingSystem`/`OrderManager`/`DataManager` methods when adding new ones.
