"""
Strategy Manager for orchestrating strategy execution.
Coordinates broker connections, market data, strategy engine, and order management.
"""

import queue
import threading
import time as time_module  # Rename to avoid conflict
import os
from typing import Dict, List, Optional, Any
from datetime import datetime, date
import pandas as pd
from dataclasses import asdict

from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)

from unified_trading_platform.trading_core.config.config import Config
from ..brokers.broker_factory import BrokerFactory
from ..brokers.base_broker import (
    BrokerInterface,
    Contract,
    Order,
    OrderAction,
    OrderType,
    TickData,
    SecurityType,
    OptionChain
)
from ..orders.order_manager import OrderManager, ManagedOrder
from ..data.data_manager import DataManager
from .config import load_strategy_config, StrategyConfig
from .live_engine import UnifiedStrategyEngine, OrderSignal
from ...database.db_utils import (
    init_strategy_tables,
    create_run_config,
    update_run_status,
    save_portfolio_snapshot,
    save_pnl_snapshot,
)
from unified_trading_platform.trading_core.main import TradingSystem
from unified_trading_platform.trading_core.config.config import Config

class StrategyManager:
    """Main orchestrator for strategy execution"""

    def __init__(
        self,
        venue: str,
        strategy_name: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        db_path: str = "trading_system.db",
    ):
        self.venue = venue
        self.strategy_name = strategy_name
        self.start_date = start_date
        self.end_date = end_date
        self.db_path = db_path

        self.config = Config()

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
        self.order_queue = queue.Queue()  # For pending orders
        self.current_portfolio: Dict = {}
        self.initial_portfolio: Dict = {}
        
        # Initialize config
        self.config = Config()

        # Threading
        self._stop_event = threading.Event()
        self._processing_thread: Optional[threading.Thread] = None

        # Initialize database tables
        init_strategy_tables(db_path)

    def on_order_filled(self, order):
        """Callback for when an order is filled"""
        logger.info(f"Order filled: {order.contract.symbol} - {order.filled_quantity} shares")

    def on_trade_executed(self, trade):
        """Callback for trade execution"""
        logger.info(f"Trade executed: {trade.contract.symbol} - {trade.quantity} @ ${trade.price}")

    def on_market_data(self, tick_data):
        """Callback for market data updates"""
        logger.debug(f"Market data update - {tick_data.symbol}: Bid={tick_data.bid}, Ask={tick_data.ask}, Last={tick_data.last}")

    def initialize(self) -> bool:
        """Initialize the strategy manager"""
        logger.debug("Starting initialization of StrategyManager")
        try:
            # Load strategy configuration
            self.strategy_config = load_strategy_config(self.strategy_name)

            # Create run configuration entry
            self.run_id = create_run_config(
                db_path=self.db_path,
                venue=self.venue,
                strategy_name=self.strategy_name,
                start_date=self.start_date,
                end_date=self.end_date,
                initial_portfolio={},  # Will be updated after getting broker positions
                exit_time=self.strategy_config.exit_time,
            )
            exch_config = self.config.get_broker_config(self.venue)
            logger.debug(f"Broker config: {exch_config}")

            self.trading_system.add_broker(
                name=self.venue,
                broker_type=exch_config.get("broker_type", self.venue),
                host=exch_config.get("host"),
                port=exch_config.get("port"),
                client_id=exch_config.get("client_id", 1)
            )

            # Register order callbacks
            self.trading_system.register_order_callback("order_filled", self._on_order_filled)
            self.trading_system.register_order_callback( "order_rejected", self._on_order_rejected)
            # trading_system.register_order_callback('trade_executed', self.on_trade_executed)

            # Get initial portfolio from broker
            # self.initial_portfolio = self._get_initial_portfolio()

            # Update run config with initial portfolio
            self._update_run_config_initial_portfolio()

            # Initialize strategy engine
            current_date = (date.today() if not self.start_date else datetime.strptime(self.start_date, "%Y-%m-%d").date())

            self.strategy_engine = UnifiedStrategyEngine(self.strategy_config)
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
            raise RuntimeError( "Strategy manager not initialized. Call initialize() first.")

        try:
            update_run_status(self.db_path, self.run_id, "RUNNING")
            self.is_running = True
            self._stop_event.clear()

            # Determine execution mode
            if self.start_date and self.end_date:
                # Historical backtesting mode
                logger.info("Starting backtesting mode")
                self._start_backtest_mode()
            else:
                # Live trading mode
                logger.info("Starting forward testing mode")
                self._start_live_mode()

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
        historical_data = self._get_historical_data()
        self._process_historical_data(historical_data)

    def _subscribe_to_market_data(self):
        """Subscribe to real-time market data"""
        ## placeholder values for now
        sub_id = self.trading_system.subscribe_market_data("SPY", "SMART", self._on_tick_callback, SecurityType.STOCK, "USD", self.venue) 
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
        option_chain_dict = asdict(option_chain)
        # Create all combinations of expiries and strikes
        expiries = option_chain_dict['expiration_dates']
        strikes = option_chain_dict['strikes']
        
        # Create a row for each combination
        rows = []
        for expiry in expiries:
            for strike in strikes:
                rows.append({
                    'underlying_symbol': option_chain_dict['underlying_symbol'],
                    'expiry': expiry,
                    'strike': strike,
                    'trading_class': option_chain_dict['trading_class'],
                    'tick_size': option_chain_dict['tick_size'],
                    'last_updated': option_chain_dict['last_updated']
                })
        return pd.DataFrame(rows)

    def _process_tick(self, tick_data: TickData):
        """Process a single tick"""
        try:
            # Get current underlying price
            underlying_price = self._get_underlying_price(tick_data)

            # Get option chain if needed
            option_chain = self._get_option_chain(tick_data.timestamp)
            df_option_chain = self.option_chain_to_df(option_chain)
            logger.debug(f"Option chain data: {df_option_chain.to_string()}")

            # Process with strategy engine
            signals = self.strategy_engine.process_tick( tick_data, underlying_price, df_option_chain)

            # Execute order signals
            for signal in signals:
                self._execute_order_signal(signal)

            # Update portfolio and PnL
            self._update_portfolio_and_pnl()

        except Exception as e:
            logger.error(f"Error processing tick: {e}", exc_info=True)
            self._handle_error(e)

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
            order_id = self.trading_system.order_manager.submit_order(signal.contract, order, self.venue)

            # Add to order queue for tracking
            self.order_queue.put(
                {"order_id": order_id, "signal": signal, "timestamp": datetime.now()}
            )
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
                    "action": "entry" if signal.action == OrderAction.BUY else "exit",
                    "timestamp": order.updated_at.isoformat(),
                    "price": order.avg_fill_price,
                    "underlying_price": self._get_current_underlying_price(),
                }
                self.strategy_engine.update_position_on_fill(signal.leg_id, fill_info)

            # Update portfolio
            self._update_portfolio_and_pnl()

        except Exception as e:
            logger.error(f"Error handling order fill: {e}", exc_info=True)
            self._handle_error(e)

    def _on_order_rejected(self, order: ManagedOrder):
        """Handle order rejection"""
        logger.warning(f"Order rejected: {order.order_id}")
        # Could implement retry logic here

    def _process_historical_data(self, historical_data: pd.DataFrame):
        """Process historical data for backtesting"""
        for timestamp, row in historical_data.iterrows():
            if self._stop_event.is_set():
                break

            # Create tick data from historical row
            tick_data = TickData(
                timestamp=timestamp,
                exchange="NSE",
                security_type="CASH",
                symbol="NIFTY",
                currency="INR",
                last=row.get("close"),
                bid=row.get("close"),
                ask=row.get("close"),
            )

            # Process the tick
            self._process_tick(tick_data)

            # Check exit conditions
            if self._should_exit():
                break

    def _get_historical_data(self) -> pd.DataFrame:
        """Get historical data for backtesting"""
        # Create contract for underlying
        contract = self._create_underlying_contract()

        # Calculate duration
        start_dt = datetime.strptime(self.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(self.end_date, "%Y-%m-%d")
        duration_days = (end_dt - start_dt).days

        # Get historical data
        historical_data = self.trading_system.data_manager.get_historical_data(contract, f"{duration_days} D", "1 min", self.venue)

        return historical_data

    def _create_underlying_contract(self) -> Contract:
        """Create contract for underlying instrument"""
        return Contract(symbol="SPY", security_type="STK", exchange="SMART", currency="USD", conId = 756733)

    def _get_underlying_price(self, tick_data: TickData) -> float:
        """Get current underlying price"""
        return tick_data.last or tick_data.bid or tick_data.ask or 0.0

    def _get_current_underlying_price(self) -> float:
        """Get current underlying price from broker"""
        # This would typically query the broker for current price
        return 0.0  # Placeholder

    def _get_option_chain(self, timestamp: pd.Timestamp) -> Optional[pd.DataFrame]:
        """Get option chain for given timestamp"""
        #fixme: placeholder args for now
        contract = Contract(symbol="SPY", security_type=SecurityType.STOCK, exchange="", currency="USD", conId=756733)
        logger.debug(f"Fetching option chain for contract: {contract}")
        # TODO: This should be for the specified timestamp. Right now we don't have an implementation for that
        return self.trading_system.get_option_chain(self.venue, contract) 

    def _get_initial_portfolio(self) -> Dict[str, Any]:
        """Get initial portfolio from broker"""
        try:
            positions = self.trading_system.get_positions()
            account_info = self.trading_system.get_account_info()

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
        # This would search through the order queue to find the matching signal
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
            "venue": self.venue,
            "strategy_name": self.strategy_name,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    def get_portfolio_summary(self) -> Dict:
        """Get current portfolio summary"""
        if self.strategy_engine:
            return self.strategy_engine.get_portfolio_summary()
        return {}
