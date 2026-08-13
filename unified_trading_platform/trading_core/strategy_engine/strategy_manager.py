"""
Strategy Manager for orchestrating strategy execution.
Coordinates broker connections, market data, strategy engine, and order management.
"""

# Standard library imports
import bisect
import queue
import threading
from datetime import datetime, date
from typing import Dict, List, Optional, Any

# Third-party imports
import numpy as np
import pandas as pd

# Local application imports
from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.config.config import Config
from unified_trading_platform.trading_core.data_models import (
    Contract,
    OptionChain,
    SecurityType,
    TickData,
    ManagedOrder,
    Order,
)
from unified_trading_platform.trading_core.strategy_engine.config import load_strategy_config, StrategyConfig
from unified_trading_platform.trading_core.strategy_engine.live_engine import UnifiedStrategyEngine, OrderSignal
from unified_trading_platform.trading_core.trading_system import TradingSystem
from unified_trading_platform.trading_core.database.db_utils import (
    init_strategy_tables,
    create_run_config,
    update_run_status,
    save_portfolio_snapshot,
    save_pnl_snapshot,
)
from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)


class StrategyManager:
    """Main orchestrator for strategy execution"""

    def __init__(
        self,
        broker_name: str,
        exchange: str,
        strategy_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db_path: str = "trading_system.db",
    ):
        self.broker_name = broker_name
        self.exchange = exchange
        self.strategy_name = strategy_name
        self.start_date = start_date
        self.end_date = end_date
        self.db_path = db_path

        # Core components
        self.trading_system = TradingSystem()
        self.broker: Optional[BrokerInterface] = None
        self.strategy_engine: Optional[UnifiedStrategyEngine] = None
        self.strategy_config: Optional[StrategyConfig] = None

        # State management
        self.run_id: Optional[str] = None
        self.is_running = False
        self.is_initialized = False
        self.tick_queue = queue.Queue()
        self.order_tracker: Dict[str, dict] = {}  # order_id -> order_info for O(1) lookups
        self.current_portfolio: Dict = {}
        self.initial_portfolio: Dict = {}

        # Initialize config
        self.config = Config()
        self._additional_config: Dict = {}  # Stored for backtest option loading
        self._is_backtest = bool(start_date)  # True if backtesting

        # Backtest option chain cache
        self._options_table: Optional[pd.DataFrame] = None  # Raw options (all timestamps)
        self._price_pivot: Optional[pd.DataFrame] = None  # Forward-filled price matrix
        self._option_meta: Optional[pd.DataFrame] = None  # Static metadata per (OptionType, Strike)
        self._options_by_time: Dict = {}  # Grouped by timestamp for O(1) lookup
        self._options_timestamps: List = []  # Sorted timestamps for bisect

        # Threading
        self._stop_event = threading.Event()
        self._processing_thread: Optional[threading.Thread] = None

        # Initialize database tables
        init_strategy_tables(db_path)

    ## fixme: additional config should not be passed here
    def initialize(self, additional_config: Optional[Dict] = None) -> bool:
        """Initialize the strategy manager"""
        logger.debug("Starting initialization of StrategyManager")
        try:
            # Load strategy configuration
            self.strategy_config = load_strategy_config(self.strategy_name)

            # Create run configuration entry
            self.run_id = create_run_config(
                db_path=self.db_path,
                broker_name=self.broker_name,
                exchange=self.exchange,
                strategy_name=self.strategy_name,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_portfolio={},  # Will be updated after getting broker positions
                exit_time=self.strategy_config.exit_time,
            )
            broker_config = self.config.get_broker_config(self.broker_name)
            logger.debug(f"Broker config: {broker_config}")

            self._additional_config = additional_config or {}

            self.trading_system.add_broker(
                name=self.broker_name,
                broker_type=broker_config.get("broker_type", self.broker_name),
                host=broker_config.get("host"),
                port=broker_config.get("port"),
                client_id=broker_config.get("client_id", 1),
                **self._additional_config,
            )

            # Register order callbacks
            self.trading_system.register_order_callback("order_filled", self._on_order_filled)
            self.trading_system.register_order_callback("order_rejected", self._on_order_rejected)
            # trading_system.register_order_callback('trade_executed', self.on_trade_executed)

            # Get initial portfolio from broker
            self.initial_portfolio = self._get_initial_portfolio()
            logger.info(f"Initial portfolio: {self.initial_portfolio}")

            # Initialize strategy engine
            current_date = (
                date.today() if not self.start_date else datetime.strptime(self.start_date, "%Y-%m-%d").date()
            )
            self.end_date = current_date if not self.end_date else self.end_date

            # Derive currency from exchange config
            from unified_trading_platform.trading_core.config.config import settings
            exch_cfg = settings.get_exchange_config(self.exchange)
            currency = exch_cfg.get("currency")

            self.strategy_engine = UnifiedStrategyEngine(self.strategy_config, exchange=self.exchange, currency=currency)
            self.strategy_engine.initialize(
                current_date=current_date,
                entry_time=self.strategy_config.entry_time,
                exit_time=self.strategy_config.exit_time,
            )
            self.is_initialized = True
            # update_run_status(self.db_path, self.run_id, "INITIAL")
            return True
        except Exception as e:
            if self.run_id:
                update_run_status(self.db_path, self.run_id, "ERROR", str(e))
            raise e

    def start(self) -> bool:
        """Start strategy execution"""
        if not self.is_initialized:
            raise RuntimeError("Strategy manager not initialized. Call initialize() first.")
        try:
            update_run_status(self.db_path, self.run_id, "RUNNING")
            self.is_running = True
            self._stop_event.clear()

            # Determine execution mode
            if self.start_date:
                # Historical backtesting mode
                logger.info("Starting backtesting mode")
                self._start_backtest_mode()
            else:
                # Live trading mode
                logger.info("Starting forward testing mode")
                self._start_live_mode()

            logger.info("Strategy started successfully")
            logger.info("Results")

            result_df = pd.DataFrame(self.strategy_engine.rows)
            logger.info(result_df)
            return True

        except Exception as e:
            update_run_status(self.db_path, self.run_id, "ERROR", str(e))
            self.is_running = False
            raise e

    def stop(self):
        """Stop strategy execution"""
        self.is_running = False
        self._stop_event.set()

        if self._processing_thread and self._processing_thread.is_alive():
            self._processing_thread.join(timeout=5.0)

        # Update final status
        if self.run_id:
            update_run_status(self.db_path, self.run_id, "FINISHED")

        # Disconnect from broker
        self.trading_system.shutdown()

    def _start_live_mode(self):
        """Start live trading mode"""
        logger.info("Starting forward testing mode")
        self._subscribe_to_market_data()
        # Start processing thread
        self._processing_thread = threading.Thread(target=self._process_tick_queue)
        self._processing_thread.daemon = True
        self._processing_thread.start()

    def _start_backtest_mode(self):
        """Start historical backtesting mode"""
        logger.info("Starting backtesting mode")
        self._load_options_for_backtest()
        if self._option_meta is not None:
            self._build_option_chain_template()
        historical_data = self._get_historical_data()
        self._process_historical_data(historical_data)

    def _subscribe_to_market_data(self):
        """Subscribe to real-time market data"""
        sub_id = self.trading_system.subscribe_market_data(
            self.strategy_config.symbol,
            self.exchange,
            self._on_tick_callback,
            SecurityType.STOCK,
            self.strategy_config.currency,
            self.broker_name,
        )
        logger.info(f"Subscribed to market data with subscription ID: {sub_id}")

    def _on_tick_callback(self, tick_data: TickData):
        """Callback for real-time tick data"""
        if self.is_running:
            self.tick_queue.put(tick_data)

    def _process_tick_queue(self):
        """Main processing loop for tick queue"""
        while not self._stop_event.is_set():
            try:
                tick_data = self.tick_queue.get(timeout=1.0)
                self._process_tick(tick_data)
                if self._should_exit():
                    logger.info("Exit condition met; stopping tick processing")
                    break
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error processing tick: {e}", exc_info=True)
                self._handle_error(e)
                break

    def option_chain_to_df(self, option_chain: OptionChain) -> pd.DataFrame:
        """
        Create a simplified DataFrame from an OptionChain.
        Each row represents a strike/expiry combination.
        """
        if option_chain is None:
            return pd.DataFrame()
        rows = []

        # Extract underlying symbol from the contract
        underlying_symbol = option_chain.contract.symbol if hasattr(option_chain, "contract") else ""

        # Process each expiry group
        for expiry_group in option_chain.expiration_dates:
            expiry_date = expiry_group.expiry_date

            # Process each strike in the expiry group
            for strike_group in expiry_group.strikes:
                strike_price = strike_group.strike_price

                # Add call option if exists
                if strike_group.call_option:
                    call = strike_group.call_option
                    rows.append(
                        {
                            "underlying_symbol": underlying_symbol,
                            "expiry": expiry_date,
                            "strike": strike_price,
                            "option_type": "CE",
                            "price": call.ltp,
                            "lot": call.lot,
                            "last_updated": call.last_updated,
                        }
                    )

                # Add put option if exists
                if strike_group.put_option:
                    put = strike_group.put_option
                    rows.append(
                        {
                            "underlying_symbol": underlying_symbol,
                            "expiry": expiry_date,
                            "strike": strike_price,
                            "option_type": "PE",
                            "price": put.ltp,
                            "lot": put.lot,
                            "last_updated": put.last_updated,
                        }
                    )

        # Create and return the DataFrame
        return pd.DataFrame(rows) if rows else pd.DataFrame()

    def _process_tick(self, tick_data: TickData):
        """Process a single tick"""
        try:
            # Get current underlying price
            underlying_price = self._get_underlying_price(tick_data)

            # Resolve option chain based on mode
            if self._is_backtest:
                # Backtest: look up from pre-loaded options table by timestamp
                df_option_chain = self._resolve_option_chain_for_tick(tick_data.timestamp)
            else:
                # Live/forward: get from broker
                option_chain = self._get_option_chain(tick_data)
                df_option_chain = self.option_chain_to_df(option_chain)

            logger.debug(f"Option chain snapshot: {len(df_option_chain)} rows")

            # Process with strategy engine
            signals = self.strategy_engine.process_tick(tick_data, underlying_price, df_option_chain)

            # Execute order signals
            for signal in signals:
                self._execute_order_signal(signal)

            logger.debug("PnL rows so far:")
            pd.set_option("display.max_columns", None)
            logger.debug("\n%s", pd.DataFrame(self.strategy_engine.rows))

        except Exception as e:
            logger.error(f"Error processing tick: {e}", exc_info=True)
            self._handle_error(e)

    # ---- Backtest option chain helpers ----

    def _load_options_for_backtest(self):
        """Load the full options table once at backtest start.
        Builds a forward-filled price matrix so every (timestamp, strike, option_type)
        has a price — even if that specific option didn't tick at that minute.
        This is necessary because the H5 is a tick log, not a full-chain snapshot."""
        from pathlib import Path
        from unified_trading_platform.trading_core.brokers.paper_broker.jio import JioH5Adapter

        h5_path = self._additional_config.get("h5_path")
        if not h5_path:
            logger.warning("No h5_path in config — option premiums will not be available in backtest")
            return

        logger.info(f"Loading options table from {h5_path} for backtest...")
        adapter = JioH5Adapter(Path(h5_path), exchange=self.exchange)
        self._options_table = adapter.options_table()
        logger.info(f"Loaded {len(self._options_table)} option price rows")

        # Build forward-filled pivot: rows=timestamp, columns=(OptionType, Strike), values=price
        # At any minute, every strike has a price (the most recent known tick)
        self._price_pivot = self._options_table.pivot_table(
            index=self._options_table.index,
            columns=["OptionType", "Strike"],
            values="price",
            aggfunc="last",
        ).ffill()

        self._options_timestamps = list(self._price_pivot.index)

        # Store static metadata (Expiry, lot) per (OptionType, Strike) — doesn't vary over time
        meta = self._options_table.groupby(["OptionType", "Strike"]).agg(
            {
                "Expiry": "first",
                "lot": "first",
                "Symbol": "first",
            }
        )
        self._option_meta = meta

        logger.info(
            f"Built price matrix: {self._price_pivot.shape[0]} timestamps × "
            f"{self._price_pivot.shape[1]} options, "
            f"spans {self._options_timestamps[0]} → {self._options_timestamps[-1]}"
        )

    def _build_option_chain_template(self):
        """Pre-build a template DataFrame with static columns and a numpy column-index
        mapping for O(1) vectorized price extraction from the pivot matrix."""
        rows = []
        col_indices = []  # Maps each template row → pivot column index
        pivot_columns = list(self._price_pivot.columns)
        pivot_col_lookup = {col: i for i, col in enumerate(pivot_columns)}

        for opt_type, strike in self._option_meta.index:
            meta = self._option_meta.loc[(opt_type, strike)]
            symbol = meta["Symbol"]
            rows.append(
                {
                    "underlying_symbol": symbol.split("2")[0] if isinstance(symbol, str) else self.strategy_config.symbol,
                    "expiry": meta["Expiry"],
                    "strike": strike,
                    "option_type": opt_type,
                    "price": 0.0,
                    "lot": meta["lot"],
                    "last_updated": None,
                }
            )
            col_indices.append(pivot_col_lookup.get((opt_type, strike), -1))

        self._chain_template = pd.DataFrame(rows)
        self._col_indices = np.array(col_indices)
        self._price_values = self._price_pivot.values  # Numpy array for fast indexing
        self._last_resolved_idx = -1
        self._last_resolved_df = None

    def _resolve_option_chain_for_tick(self, tick_timestamp) -> pd.DataFrame:
        """Get option chain snapshot at this tick's timestamp.
        Uses bisect for O(log n) timestamp lookup + numpy indexing for O(1) price extraction.
        Caches result when consecutive ticks map to the same pivot row."""
        if self._price_pivot is None or self._price_pivot.empty:
            return pd.DataFrame()

        ts = pd.Timestamp(tick_timestamp)
        idx = bisect.bisect_right(self._options_timestamps, ts) - 1
        if idx < 0:
            idx = 0

        # Cache hit: same pivot row as last tick
        if idx == self._last_resolved_idx and self._last_resolved_df is not None:
            return self._last_resolved_df

        # Vectorized price extraction: one numpy index op instead of 200-iteration loop
        prices = self._price_values[idx, self._col_indices]

        df = self._chain_template.copy()
        df["price"] = prices
        df["last_updated"] = self._options_timestamps[idx]

        # Drop strikes with no price yet (NaN from before first tick)
        df = df.dropna(subset=["price"]).reset_index(drop=True)

        self._last_resolved_idx = idx
        self._last_resolved_df = df
        return df

    def _execute_order_signal(self, signal: OrderSignal):
        """Execute an order signal"""
        try:
            # Create order
            order = Order(
                action=signal.action,
                quantity=signal.quantity,
                order_type=signal.order_type,
                limit_price=signal.price,
                time_in_force="DAY",
            )
            # Submit order
            order_id = self.trading_system.order_manager.submit_order(signal.contract, order, self.broker_name)

            # Add to order tracker for O(1) lookups
            self.order_tracker[order_id] = {
                "signal": signal,
                "timestamp": datetime.now(),
                "status": "pending",
            }
        except Exception as e:
            logger.error(f"Error executing order signal: {e}", exc_info=True)
            self._handle_error(e)

    def _on_order_filled(self, order: ManagedOrder):
        """Handle order fill"""
        try:
            # Find the corresponding signal
            signal = self._find_signal_for_order(order.order_id)
            if signal:
                # Update strategy engine
                fill_info = {
                    "action": "exit" if signal.is_exit else "entry",
                    "timestamp": order.updated_at.isoformat(),
                    "price": order.avg_fill_price,
                    "underlying_price": self._get_current_underlying_price(),
                }
                self.strategy_engine.update_position_on_fill(signal.leg_id, fill_info)

            # Update order tracker
            self.order_tracker[order.order_id]["status"] = "filled"

            # Update portfolio
            self._update_portfolio_and_pnl()

        except Exception as e:
            logger.error(f"Error handling order fill: {e}", exc_info=True)
            self._handle_error(e)

    def _on_order_rejected(self, order: ManagedOrder):
        """Handle order rejection"""
        logger.warning(f"Order rejected: {order.order_id}")
        # Could implement retry logic here

    def _process_historical_data(self, historical_data: List[TickData]):
        """Process historical data for backtesting"""
        for tick in historical_data:
            if self._stop_event.is_set():
                break
            # Process the tick
            self._process_tick(tick)
        logger.info("All ticks processed")

    def _get_historical_data(self) -> List[TickData]:
        """Get historical data for backtesting"""
        # Create contract for underlying
        contract = self._create_underlying_contract()

        logger.info(f"Fetching historical data for {contract}")

        # Calculate duration
        start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
        duration_days = (end_dt - start_dt).days

        # Get historical data
        historical_data = self.trading_system.get_historical_data(
            symbol=contract.symbol,
            exchange=self.exchange,
            security_type=contract.security_type,
            currency=contract.currency,
            duration=f"{duration_days} D",
            bar_size="1min",
            broker_name=self.broker_name,
        )
        return historical_data

    def _create_underlying_contract(self) -> Contract:
        """Create contract for underlying instrument"""
        return Contract(
            symbol=self.strategy_config.symbol,
            security_type=SecurityType.STOCK,
            exchange=self.exchange,
            currency=self.strategy_config.currency,
            conId=756733,
        )

    def _get_underlying_price(self, tick_data: TickData) -> float:
        """Get current underlying price"""
        return tick_data.last or tick_data.bid or tick_data.ask or tick_data.close or 0.0

    def _get_current_underlying_price(self) -> float:
        """Get current underlying price from broker"""
        # This would typically query the broker for current price
        return 0.0  # Placeholder

    def _get_option_chain(self, tick_data: TickData) -> OptionChain:
        """Get option chain for given timestamp (cached per session)"""
        # Cache the option chain to avoid re-reading H5 on every tick
        if hasattr(self, "_cached_option_chain") and self._cached_option_chain is not None:
            return self._cached_option_chain
        contract = Contract(
            symbol=tick_data.symbol,
            security_type=tick_data.security_type,
            exchange=tick_data.exchange,
            currency=tick_data.currency,
            conId=756733,
        )
        logger.info(f"Fetching option chain for contract: {contract}")
        # TODO: This should be for the specified timestamp. Right now we don't have an implementation for that
        self._cached_option_chain = self.trading_system.get_option_chain(self.broker_name, contract)
        return self._cached_option_chain

    def _get_initial_portfolio(self) -> Dict[str, Any]:
        """Get initial portfolio from broker"""
        try:
            positions = self.trading_system.get_positions()
            account_info = self.trading_system.get_account_info(self.broker_name)

            return {
                "positions": positions,
                "cash_balance": account_info.get("cash_balance", 0.0),
                "total_value": account_info.get("total_value", 0.0),
            }
        except Exception as e:
            logger.error(f"Error getting initial portfolio: {e}", exc_info=True)
            return {}

    def _update_run_config_initial_portfolio(self):
        """Update run config with initial portfolio"""
        # This would update the database with initial portfolio
        pass

    def _update_portfolio_and_pnl(self):
        """Update portfolio and PnL in database"""
        try:
            # Get current positions from strategy engine
            positions = self.strategy_engine.get_current_positions()

            # Calculate PnL
            portfolio_summary = self.strategy_engine.get_portfolio_summary()

            # Save to database
            save_portfolio_snapshot(
                self.db_path,
                self.run_id,
                [
                    {
                        "leg_id": leg.leg_id,
                        "strike": leg.strike,
                        "qty": leg.qty,
                        "pnl": leg.pnl,
                    }
                    for leg in positions
                ],
                self.current_portfolio.get("cash_balance", 0.0),
                self.current_portfolio.get("total_value", 0.0),
            )

            save_pnl_snapshot(
                self.db_path,
                self.run_id,
                portfolio_summary.get("total_pnl", 0.0),
                0.0,  # unrealized_pnl
                portfolio_summary.get("total_pnl", 0.0),
                portfolio_summary.get("closed_positions", 0),
                0,  # win_count
                0,  # loss_count
            )

        except Exception as e:
            logger.error(f"Error updating portfolio and PnL: {e}", exc_info=True)

    def _find_signal_for_order(self, order_id: str) -> Optional[OrderSignal]:
        """Find the signal that corresponds to an order"""
        order_info = self.order_tracker.get(order_id)
        if order_info:
            return order_info["signal"]
        return None

    def _should_exit(self) -> bool:
        """Check if we should exit"""
        # Check time-based exit
        current_time = datetime.now().time()
        if self.strategy_engine.should_exit(current_time):
            return True

        # Check manual stop
        if self._stop_event.is_set():
            return True
        return False

    def _handle_error(self, error: Exception):
        """Handle errors during execution"""
        logger.error(f"Strategy execution error: {error}", exc_info=True)
        update_run_status(self.db_path, self.run_id, "ERROR", str(error))
        self.is_running = False

    def get_status(self) -> Dict:
        """Get current status of the strategy manager"""
        return {
            "run_id": self.run_id,
            "is_running": self.is_running,
            "is_initialized": self.is_initialized,
            "broker_name": self.broker_name,
            "exchange": self.exchange,
            "strategy_name": self.strategy_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary"""
        if self.strategy_engine:
            return self.strategy_engine.get_portfolio_summary()
        return {}
