"""
Main trading system that integrates all components.
Provides a unified interface for algorithmic trading across multiple brokers.
"""

from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from unified_trading_platform.trading_core.utils import get_logger

from unified_trading_platform.trading_core.brokers.broker_factory import BrokerFactory
from unified_trading_platform.trading_core.data.data_manager import DataManager
from unified_trading_platform.trading_core.orders.order_manager import OrderManager
from unified_trading_platform.trading_core.event_system import EventEngine, Event, EventType
from unified_trading_platform.trading_core.data_models import (
    Contract,
    Order,
    OrderType,
    OrderAction,
    SecurityType,
    TickData,
    OptionChain,
)


class TradingSystem:
    """Main trading system class"""

    def __init__(self, db_path: Optional[str] = None):
        # Initialize logger
        self.logger = get_logger(__name__)

        # Validate config upfront
        self._validate_config()

        if db_path is None:
            from unified_trading_platform.trading_core.config.config import settings

            db_path = settings.get("database.path", "trading_system.db")

        self.db_path = db_path
        self.data_manager = DataManager(db_path)
        self.order_manager = OrderManager(db_path)
        self.brokers = {}

        # Set up order submission callback
        def log_order_submission(args: Dict[str, Any]) -> None:
            self.logger.info(f"Order submitted: {args}")

        self.order_manager.callbacks["order_submitted"].append(log_order_submission)

        # Initialize Event Engine
        self.event_engine = EventEngine()
        self.event_engine.start()
        self.event_engine.register(EventType.TICK, self._process_tick_event)

    def _validate_config(self):
        """Validate critical configuration parameters at startup."""
        from unified_trading_platform.trading_core.config.config import settings

        errors = []
        warnings = []

        # 1. default_exchange must be set
        default_ex = settings.get("system.default_exchange")
        if not default_ex:
            errors.append("system.default_exchange is not set in config.yaml")
        else:
            # 2. Exchange config must exist for the default exchange
            ex_cfg = settings.get_exchange_config(default_ex)
            if not ex_cfg:
                errors.append(f"No exchange config found for default exchange '{default_ex}'")
            else:
                if "trading_hours" not in ex_cfg:
                    warnings.append(f"Exchange '{default_ex}' missing 'trading_hours' section")
                if "currency" not in ex_cfg:
                    warnings.append(f"Exchange '{default_ex}' missing 'currency'")
                expiry_cfg = ex_cfg.get("expiry", {})
                if not expiry_cfg:
                    warnings.append(f"Exchange '{default_ex}' missing 'expiry' config")

        for w in warnings:
            self.logger.warning(f"Config warning: {w}")
        if errors:
            msg = "Config validation failed:\n  - " + "\n  - ".join(errors)
            self.logger.error(msg)
            raise ValueError(msg)

    def _process_tick_event(self, event: Event):
        """Process tick event: Store data and call user callback"""
        data = event.data
        tick = data.get("tick")
        callback = data.get("callback")
        
        if tick:
            # Async DB Write
            self.data_manager.store_tick(tick)
            # User Callback
            if callback:
                try:
                    callback(tick)
                except Exception as e:
                    self.logger.error(f"Error in user callback: {e}")

    def add_broker(self, name: str, broker_type: str, **config) -> bool:
        """Add a broker to the system"""
        try:
            self.logger.info(f"Creating broker of type: {broker_type} with config: {config}")
            # Create broker instance with config
            broker = BrokerFactory.create_broker(broker_type, **config)

            # Connect the broker
            self.logger.info(f"Connecting to {broker_type}...")
            if broker.connect():
                self.brokers[name] = broker
                self.logger.info("Broker connected, initializing data and order management...")
                self.data_manager.add_broker(name, broker)
                self.order_manager.add_broker(name, broker)
                self.logger.info(f"Broker '{name}' ({broker_type}) added and initialized successfully")
                return True
            else:
                self.logger.error(f"Failed to connect to broker '{name}'")
                return False

        except Exception as e:
            self.logger.error(f"Error adding broker '{name}': {str(e)}", exc_info=True)
            return False

    def remove_broker(self, name: str):
        """Remove a broker from the system"""
        if name in self.brokers:
            self.logger.info(f"Removing broker: {name}")
            self.brokers[name].disconnect()
            del self.brokers[name]
            self.logger.info(f"Broker '{name}' removed")
            return True
        return False

    def shutdown(self):
        """Shutdown the trading system"""
        self.logger.info("Shutting down trading system...")

        # Stop event engine
        if hasattr(self, "event_engine"):
            self.event_engine.stop()

        for name, broker in self.brokers.items():
            try:
                broker.disconnect()
                self.logger.info(f"Disconnected from broker '{name}'")
            except Exception as e:
                self.logger.error(f"Error disconnecting from broker '{name}': {e}", exc_info=True)

        self.brokers.clear()
        self.logger.info("Trading system shutdown complete")

    @staticmethod
    def _make_contract(symbol: str, exchange: str, security_type, currency: str) -> Contract:
        """Build a Contract, accepting the security type as an enum or its string value."""
        if isinstance(security_type, str):
            security_type = SecurityType(security_type.upper())
        return Contract(symbol=symbol, security_type=security_type, exchange=exchange, currency=currency)

    def get_historical_data(
        self,
        symbol: str,
        exchange: str,
        security_type: SecurityType = SecurityType.STOCK,
        currency: str = "USD",
        duration: str = "1 D",
        bar_size: str = "1H",
        broker_name: Optional[str] = None,
    ) -> List[TickData]:
        """Get historical data for a symbol"""
        contract = self._make_contract(symbol, exchange, security_type, currency)

        return self.data_manager.get_historical_data(contract, duration, bar_size, broker_name, False)

    def subscribe_market_data(
        self,
        symbol: str,
        exchange: str,
        callback: Callable,
        security_type: SecurityType = SecurityType.STOCK,
        currency: str = "USD",
        broker_name: Optional[str] = None,
    ) -> bool:
        """Subscribe to real-time market data"""
        contract = self._make_contract(symbol, exchange, security_type, currency)
        
        # Create non-blocking producer callback
        def producer_callback(tick: TickData):
            event = Event(EventType.TICK, {"tick": tick, "callback": callback})
            self.event_engine.put(event)
            
        # Call data manager with store_data=False (handled by event engine)
        return self.data_manager.subscribe_real_time_data(
            contract, producer_callback, broker_name, store_data=False
        )

    def get_option_chain(self, broker_name: str, contract: Contract) -> OptionChain:
        return self.data_manager.get_option_chain(broker_name, contract)

    def submit_market_order(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        broker_name: str,
        security_type: SecurityType = SecurityType.STOCK,
        currency: str = "USD",
        account: Optional[str] = None,
    ) -> str:
        """Submit a market order"""
        contract = self._make_contract(symbol, exchange, security_type, currency)

        order = Order(
            action=OrderAction(action.upper()), quantity=quantity, order_type=OrderType.MARKET, account=account
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def submit_limit_order(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        limit_price: float,
        broker_name: str,
        security_type: SecurityType = SecurityType.STOCK,
        currency: str = "USD",
        time_in_force: str = "DAY",
        account: Optional[str] = None,
    ) -> str:
        """Submit a limit order"""
        contract = self._make_contract(symbol, exchange, security_type, currency)

        order = Order(
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=account,
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def submit_stop_order(
        self,
        symbol: str,
        exchange: str,
        action: str,
        quantity: int,
        stop_price: float,
        broker_name: str,
        security_type: SecurityType = SecurityType.STOCK,
        currency: str = "USD",
        time_in_force: str = "DAY",
        account: Optional[str] = None,
    ) -> str:
        """Submit a stop order"""
        contract = self._make_contract(symbol, exchange, security_type, currency)

        order = Order(
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=stop_price,
            time_in_force=time_in_force,
            account=account,
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        return self.order_manager.cancel_order(order_id)

    @staticmethod
    def _order_to_dict(order) -> Dict:
        return {
            "order_id": order.order_id,
            "broker_order_id": order.broker_order_id,
            "broker_name": order.broker_name,
            "symbol": order.contract.symbol,
            "exchange": order.contract.exchange,
            "security_type": order.contract.security_type.value,
            "currency": order.contract.currency,
            "action": order.order.action.value,
            "quantity": order.order.quantity,
            "order_type": order.order.order_type.value,
            "limit_price": order.order.limit_price,
            "stop_price": order.order.stop_price,
            "time_in_force": order.order.time_in_force,
            "status": order.status.value,
            "filled_quantity": order.filled_quantity,
            "remaining_quantity": order.remaining_quantity,
            "avg_fill_price": order.avg_fill_price,
            "created_at": order.created_at,
            "updated_at": order.updated_at,
        }

    def get_order_status(self, order_id: str) -> Dict:
        """Get order status"""
        order = self.order_manager.get_order(order_id)
        return self._order_to_dict(order) if order else {}

    def get_all_orders(self) -> List[Dict]:
        """Get all orders"""
        return [self._order_to_dict(order) for order in self.order_manager.get_orders()]

    def get_positions(self, broker_name: Optional[str] = None) -> List[Dict]:
        """Get current positions"""
        return self.order_manager.get_positions(broker_name)

    def get_account_info(self, broker_name: str) -> Dict:
        """Get account information"""
        if broker_name in self.brokers:
            return self.brokers[broker_name].get_account_info()
        return {}

    def register_order_callback(self, event_type: str, callback: Callable):
        """Register callback for order events"""
        self.order_manager.register_callback(event_type, callback)

    def get_order_history(
        self, symbol: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get order history"""
        return self.order_manager.get_order_history(symbol, start_date, end_date)

    def get_trade_history(
        self, symbol: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get trade history"""
        return self.order_manager.get_trade_history(symbol, start_date, end_date)
