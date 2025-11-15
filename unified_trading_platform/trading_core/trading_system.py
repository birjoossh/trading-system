"""
Main trading system that integrates all components.
Provides a unified interface for algorithmic trading across multiple brokers.
"""

from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
import pandas as pd

from unified_trading_platform.trading_core.utils import get_logger

from unified_trading_platform.trading_core.brokers.broker_factory import BrokerFactory
from unified_trading_platform.trading_core.brokers.base_broker import Contract, Order, OrderType, OrderAction, SecurityType
from unified_trading_platform.trading_core.data.data_manager import DataManager
from unified_trading_platform.trading_core.orders.order_manager import OrderManager

class TradingSystem:
    """Main trading system class"""

    def __init__(self, db_path: str = "trading_system2.db"):
        # Initialize logger
        self.logger = get_logger(__name__)
        
        self.data_manager = DataManager(db_path)
        self.order_manager = OrderManager(db_path)
        self.brokers = {}
        self.strategies = {}
        self.is_running = False
        
        # Set up order submission callback
        def log_order_submission(args: Dict[str, Any]) -> None:
            self.logger.info(f"Order submitted: {args}")
        self.order_manager.callbacks['order_submitted'].append(log_order_submission)

    def add_broker(self, name: str, broker_type: str, **config) -> bool:
        """Add a broker to the system"""
        try:
            self.logger.info(f"Creating broker of type: {broker_type}")
            # Create broker instance with required parameters
            if broker_type.lower() == 'interactive_brokers':
                host = config.get('host', '127.0.0.1')
                port = config.get('port', 7497)  # Default paper trading port
                client_id = config.get('client_id', 1)
                self.logger.info(f"Connecting to Interactive Brokers at {host}:{port} with client ID {client_id}")
                broker = BrokerFactory.create_broker(broker_type, host=host, port=port, client_id=client_id)
            else:
                self.logger.debug(f"Creating broker with config: {config}")
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

    def get_historical_data(self, symbol: str, exchange: str,
                          security_type: str = "STK", currency: str = "USD",
                          duration: str = "1 D", bar_size: str = "1H",
                          broker_name: Optional[str] = None) -> pd.DataFrame:
        """Get historical data for a symbol"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        return self.data_manager.get_historical_data(
            contract, duration, bar_size, broker_name, False
        )

    def subscribe_market_data(self, symbol: str, exchange: str,
                            callback: Callable, security_type: SecurityType = SecurityType.STOCK,
                            currency: str = "USD", broker_name: Optional[str] = None) -> bool:
        """Subscribe to real-time market data"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        return self.data_manager.subscribe_real_time_data(
            contract, callback, broker_name
        )
    
    def get_option_chain(self, broker_name: str, contract: Contract):
        return self.data_manager.get_option_chain(broker_name, contract)

    def submit_market_order(self, symbol: str, exchange: str, action: str,
                          quantity: int, broker_name: str,
                          security_type: str = "STK", currency: str = "USD",
                          account: Optional[str] = None) -> str:
        """Submit a market order"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        order = Order(
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.MARKET,
            account=account
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def submit_limit_order(self, symbol: str, exchange: str, action: str,
                         quantity: int, limit_price: float, broker_name: str,
                         security_type: str = "STK", currency: str = "USD",
                         time_in_force: str = "DAY", account: Optional[str] = None) -> str:
        """Submit a limit order"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        order = Order(
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            time_in_force=time_in_force,
            account=account
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def submit_stop_order(self, symbol: str, exchange: str, action: str,
                        quantity: int, stop_price: float, broker_name: str,
                        security_type: str = "STK", currency: str = "USD",
                        time_in_force: str = "DAY", account: Optional[str] = None) -> str:
        """Submit a stop order"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        order = Order(
            action=OrderAction(action.upper()),
            quantity=quantity,
            order_type=OrderType.STOP,
            stop_price=stop_price,
            time_in_force=time_in_force,
            account=account
        )

        return self.order_manager.submit_order(contract, order, broker_name)

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        return self.order_manager.cancel_order(order_id)

    def get_order_status(self, order_id: str) -> Dict:
        """Get order status"""
        order = self.order_manager.get_order(order_id)
        if order:
            return {
                'order_id': order.order_id,
                'broker_order_id': order.broker_order_id,
                'symbol': order.contract.symbol,
                'action': order.order.action.value,
                'quantity': order.order.quantity,
                'order_type': order.order.order_type.value,
                'status': order.status.value,
                'filled_quantity': order.filled_quantity,
                'remaining_quantity': order.remaining_quantity,
                'avg_fill_price': order.avg_fill_price,
                'created_at': order.created_at,
                'updated_at': order.updated_at
            }
        return {}

    def get_all_orders(self) -> List[Dict]:
        """Get all orders"""
        orders = self.order_manager.get_orders()
        return [
            {
                'order_id': order.order_id,
                'broker_order_id': order.broker_order_id,
                'symbol': order.contract.symbol,
                'action': order.order.action.value,
                'quantity': order.order.quantity,
                'order_type': order.order.order_type.value,
                'status': order.status.value,
                'filled_quantity': order.filled_quantity,
                'remaining_quantity': order.remaining_quantity,
                'avg_fill_price': order.avg_fill_price,
                'created_at': order.created_at,
                'updated_at': order.updated_at
            }
            for order in orders
        ]

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

    def get_order_history(self, symbol: Optional[str] = None,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> List[Dict]:
        """Get order history"""
        return self.order_manager.get_order_history(symbol, start_date, end_date)

    def get_trade_history(self, symbol: Optional[str] = None,
                         start_date: Optional[datetime] = None,
                         end_date: Optional[datetime] = None) -> List[Dict]:
        """Get trade history"""
        return self.order_manager.get_trade_history(symbol, start_date, end_date)

    def shutdown(self):
        """Shutdown the trading system"""
        self.logger.info("Shutting down trading system...")

        for name, broker in self.brokers.items():
            try:
                broker.disconnect()
                self.logger.info(f"Disconnected from broker '{name}'")
            except Exception as e:
                self.logger.error(f"Error disconnecting from broker '{name}': {e}", exc_info=True)

        self.brokers.clear()
        self.is_running = False
        self.logger.info("Trading system shutdown complete")
