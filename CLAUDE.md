# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A modular Python algorithmic trading system (`unified_trading_platform`) built around a broker-agnostic core. It provides historical/real-time market data, order management, and an options-strategy engine, exposed both as a Python library and as a FastAPI HTTP gateway. Two brokers are implemented: Interactive Brokers (live trading, via the optional `ibapi` package) and an internal paper broker (backtesting/dev, replays HDF5 tick data). The strategy engine is purpose-built for Indian NSE index-options strategies (straddles, strangles, iron condors, credit/debit spreads).

The package root is `unified_trading_platform/`, not the repo root — all internal imports are absolute, e.g. `from unified_trading_platform.trading_core.trading_system import TradingSystem`. Run scripts from the repo root so this import path resolves.

## Commands

```bash
# Install (ibapi is optional — only needed for live IB trading)
pip install -r requirements.txt
pip install -e .              # optional, editable install (packaging lives in pyproject.toml)

# Lint (ruff is the only linter; config in pyproject.toml — py310, line-length 120)
ruff check .
ruff check --fix .

# Tests (pytest suites live in unified_trading_platform/tests/)
pytest unified_trading_platform/tests/
pytest unified_trading_platform/tests/test_backtest_smoke.py   # end-to-end backtest on bundled H5

# Run the FastAPI gateway
python -m unified_trading_platform.api                      # uvicorn on 0.0.0.0:8000, reload on
python unified_trading_platform/examples/run_api.py --reload --port 8000

# Examples (runnable scripts, not tests)
python unified_trading_platform/examples/example_paper_broker.py      # no IB needed
python unified_trading_platform/examples/example_strategy_manager.py  # backtest on examples/2024-01-02.h5
python unified_trading_platform/examples/example_ib.py                # needs TWS/Gateway + ibapi
```

CI (`.github/workflows/ci.yml`) runs `ruff check`, the pytest suite, and an API import check (without `ibapi`, to guard the optional-dependency path) on every push/PR.

## Architecture

### Layering

```
api/            FastAPI HTTP gateway (thin layer over trading_core)
trading_core/   All business logic — usable as a standalone library without the API
examples/       Runnable scripts + the bundled 2024-01-02.h5 NIFTY sample data
tests/          pytest suites (unit + end-to-end backtest smoke test)
docs/           Design notes (strategy_engine.md is the most useful one)
```

`TradingSystem` (`trading_core/trading_system.py`) is the central facade: it owns one `DataManager`, one `OrderManager`, one `EventEngine`, and a `{name: BrokerInterface}` map of connected brokers. Almost everything else is reached through it. Both `api/endpoints/*` and `strategy_engine/strategy_manager.py` drive the system exclusively through this facade rather than talking to brokers/managers directly.

### Broker abstraction

- `trading_core/brokers/base_broker.py` — `BrokerInterface` ABC. Every broker must implement connect/disconnect, historical data, order submission/cancel, positions, account info, market-data subscribe/unsubscribe, contract details, option chain, and greeks.
- `trading_core/brokers/broker_factory.py` — `BrokerFactory` is a class-level registry. Brokers self-register in `_register_builtin_brokers()` at the bottom of this file (`"ib"`/`"interactive_brokers"` → `IBBroker`, `"paper"` → `PaperBroker`). The IB registration is wrapped in try/except ImportError so everything else works without `ibapi` installed. Adding a new broker means: implement `BrokerInterface`, then add a `register_broker(...)` call there — nothing else needs to know about it.
- `trading_core/brokers/interactive_brokers/` — `IBBroker` wraps `IBClient` (raw `ibapi` EWrapper/EClient) via `IBRequestManager`, which bridges the async, callback-driven `ibapi` protocol to synchronous-looking calls using per-request `Future`s: `IBClient` asks the manager for a `reqId` + `Future`, sends the request, accumulates callback data as it streams in, and resolves the `Future` when the matching "End" callback (e.g. `contractDetailsEnd`) arrives. The `nextValidId` callback signals connection readiness (`IBBroker.connect` blocks on it). When touching IB code, preserve this reqId → Future → resolve-on-End pattern rather than adding new blocking/polling loops.
- `trading_core/brokers/paper_broker/` — simulated broker for backtesting/dev without a live IB connection. Orders are acknowledged immediately and auto-filled (at limit price) after a short delay, driving the same `order_status` callback path as IB. `jio.py` (`JioH5Adapter`) reads historical tick/options data from local HDF5 files (schema: `/tick_data` with timestamp/price/volume/tsym/strike/type/expiry/lot columns); `to_pandas_freq()` there normalizes bar sizes like "1H"/"1 hour" to pandas ≥2.2 aliases.

### Event flow (real-time data)

`trading_core/event_system.py` provides a minimal `EventEngine`: a background thread draining a `queue.Queue`, dispatching to handlers registered per `EventType` (`TICK`, `BAR`, `ORDER_STATUS`, `TRADE`, `ERROR`, `LOG`). `TradingSystem.subscribe_market_data` wraps the caller's callback in a producer that pushes a `TICK` event onto the engine instead of calling back synchronously from the broker thread; `TradingSystem._process_tick_event` is the sole `TICK` handler and both persists the tick via `DataManager` and invokes the user's callback. Don't call user callbacks directly from broker threads; go through the event engine.

### Data and order persistence

`DataManager` and `OrderManager` each open their own `sqlite3` connection and create their own tables (`historical_bars`/`tick_data` vs. `orders`/`trades`), all in one SQLite file: the path comes from `config.yaml`'s `database.path` (default `trading_system.db`), resolved in `TradingSystem.__init__` when no explicit `db_path` is passed. `database/db_utils.py` (`init_strategy_tables`, `create_run_config`, `save_portfolio_snapshot`, ...) adds strategy-run tables (`run_config`, `portfolio`, `strategy_profit_loss`) to the same file. When adding persistence, follow this pattern (raw `sqlite3`, `CREATE TABLE IF NOT EXISTS`, JSON-serialized blobs for nested structures) — and keep INSERT column lists in sync with the CREATE TABLE schemas; mismatches were a historical source of runtime crashes.

### Strategy engine (`trading_core/strategy_engine/`)

See `docs/strategy_engine.md` for the file-by-file breakdown; summary:
- `strategy_manager.py` — service layer / orchestrator. Owns a `TradingSystem`, initializes a `UnifiedStrategyEngine`, and runs either **live mode** (subscribes to real market data, processes ticks off a queue on a background thread, stops when `_should_exit()` fires) or **backtest mode** (loads the option chain once via `JioH5Adapter`, pre-builds a forward-filled price pivot for O(log n) chain lookups per tick via `bisect`, then replays historical bars through the same `_process_tick` path used live). Keeping live and backtest on the same `_process_tick` code path is intentional — new signal/exit logic goes in `UnifiedStrategyEngine`, not per mode.
- `live_engine.py` — `UnifiedStrategyEngine`: the tick-by-tick state machine. Key invariants: entries are gated on `entry_time` and only recorded once a premium is available; exit signals are generated with `closing=True`, which **reverses the order side** (closing a short leg buys back) and sets `OrderSignal.is_exit` — fill handling relies on that flag to classify entry vs. exit; order fills refine bookkeeping via `update_position_on_fill` but never overwrite simulated timestamps/prices with empty fill data; untriggered pending re-entries stay queued rather than being dropped.
- `config.py` — dataclass models for strategy configuration (`StrategyConfig`, `LegSpec`, `RiskConfig`, `ReEntryRule`, ...) loaded from JSON files in `trading_core/strategies/*.json` via `load_strategy_config(strategy_name)`. `symbol` and `currency` are required (validated in `__post_init__`). See `trading_core/strategies/Examples_README.md` for the schema.
- `strategy_utils.py`, `strikes.py`, `greeks_helper.py` — pure-logic helpers (exit condition checks, expiry resolution from exchange config, strike selection, Black-Scholes pricing/greeks). `select_strike` accepts chains with either a `price` or `Close` premium column and raises `ValueError` on empty chains (callers treat that as "skip this tick"). Prefer adding pure functions here over the manager/engine classes.

### Configuration

`config.yaml` at the repo root is the single source of truth, loaded by `trading_core/config/config.py` into a module-level `settings` singleton (`Config` class, dot-path `get`/`set`). Env var overrides use the `TRADING_CONFIG__SECTION__KEY` prefix (double underscore = path separator). The API layer reads the same `settings` object directly — `api/main.py` pulls FastAPI metadata from the `api.*` section, and `api/models/*` pull request-model defaults from `defaults.*` / `brokers.*`.

Sections: `system` (limits, thread poll/shutdown timeouts), `exchanges` (per-exchange trading hours, currency, expiry-weekday rules — see `docs/exchange_config.md`), `logging`, `database`, `brokers` (connection details, per-request IB timeouts, paper-broker fill behaviour), `pricing` (risk-free rate, dividend yield, minimum tradeable premium, IV solver bounds), `backtest` (replay bar size, duration fallback, re-entry ceiling, default execution costs), `api`, `defaults`.

**No tunable number belongs in the code.** Rates, timeouts, strike steps, cost assumptions and fill latencies are all read from `settings` at the point of use, via small module-level accessors (`greeks_helper.risk_free_rate()`, `strikes.default_strike_step()`, `common.ib_timeout()`, `paper_broker._paper_default()`). The literal passed to those accessors is a last-resort fallback for a missing key, not a place to change behaviour. `tests/test_config_driven_behaviour.py` asserts every key the code reads exists in `config.yaml` and that changing it actually changes behaviour, so re-hardcoding a value fails the suite.

`TradingSystem.__init__` calls `_validate_config()` and raises `ValueError` at startup if `system.default_exchange` isn't set or has no matching entry under `exchanges`. Keep `config.yaml`'s `exchanges` section and `system.default_exchange` in sync when editing either.

Config layout is known to be uneven (e.g. execution costs appear both under `backtest.costs` and per-strategy JSON; `defaults.*` mixes wire defaults with domain ones) — normalizing it is planned separate work.

### Instrument facts vs. platform settings

Anything specific to an instrument lives in the strategy JSON, not in config.yaml and not in code: `symbol`, `currency`, `lot_size`, `underlying_con_id` (broker contract id, `0` when unused), `underlying_security_type`, and per-strategy `costs` which override `backtest.costs`. `StrategyManager._create_underlying_contract()` builds the underlying from these fields.

### Backtest sessions

A run may span several trading days. `StrategyManager._process_historical_data` watches the tick date and calls `UnifiedStrategyEngine.start_new_session(date)` when it changes: traded legs are archived into `completed_legs`, un-entered scaffolding is discarded, pending re-entries are cleared, and fresh legs are built against the new day's expiry. `get_all_positions()` and `get_portfolio_summary()` report across every session; `get_current_positions()` stays scoped to open legs. Leg ids are allocated from a run-wide counter so they never repeat between sessions. Point `h5_path` at a single file, a list, or a directory of `*.h5` (see `jio.resolve_h5_paths`).

### Fills and cost modelling

`OrderSignal` carries the `price` and `underlying_price` the engine acted on. The paper broker fills against that reference (`_fill_price`), so market orders no longer fill at zero, and `update_position_on_fill` reconciles against the state that *produced* the order rather than "now" — in a replayed backtest the fill callback arrives on wall-clock time, long after the simulated clock moved on. Execution cost is modelled once, in `UnifiedStrategyEngine._costs_for`: `per_lot_roundtrip` is charged half on entry and half on exit, `slippage_per_fill` per fill per unit. The paper broker's own `slippage_per_fill` shifts the fill price instead — use one or the other, not both.

### API layer (`api/`)

FastAPI app assembled in `api/main.py` from config-driven metadata. Routers live under `api/endpoints/` (`health`, `brokers`, `data`, `orders`, `strategies`), request/response schemas under `api/models/`. `api/runtime.py` holds the singleton `TradingSystem` all endpoints share via `get_trading_system()` — don't construct one per request. The strategies endpoints keep their own `{run_id: StrategyManager}` registry in `api/endpoints/strategies.py`.

### Data models

`trading_core/data_models/` holds the shared domain types (`Contract`, `Order`, `TickData`, `OptionChain`, `Greeks`, `Position`, `Trade`, enums for security type / order type / tick type / option right). These are the canonical vocabulary — import from here (not from `base_broker`, which only consumes them), and don't redefine similar shapes elsewhere. `api/models/` are the pydantic (wire) counterparts with `from_domain` converters.

## Conventions

- All cross-module imports are absolute from the package root: `from unified_trading_platform.trading_core.<module> import ...`.
- Logging goes through `trading_core/utils/logger.py`'s `get_logger(__name__)`, not `print()` or the stdlib `logging` module directly.
- Broker, data, and order errors are generally caught, logged with `exc_info=True`, and turned into a return value (`False`/`{}`/raised `ValueError`) rather than left to propagate raw — follow the existing pattern in `TradingSystem`/`OrderManager`/`DataManager` methods when adding new ones.
- Keep `ruff check .` clean — CI enforces it.
