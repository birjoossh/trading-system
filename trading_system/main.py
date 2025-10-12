"""
Main trading system that integrates all components.
Provides a unified interface for algorithmic trading across multiple brokers.
"""

from typing import Dict, List, Optional, Callable
from datetime import datetime
import pandas as pd

from trading_system.brokers.broker_factory import BrokerFactory
from trading_system.brokers.base_broker import Contract, Order, OrderType, OrderAction
from trading_system.data.data_manager import DataManager
from trading_system.orders.order_manager import OrderManager

class TradingSystem:
    """Main trading system class"""

    def __init__(self, db_path: str = "trading_system2.db"):
        self.data_manager = DataManager(db_path)
        self.order_manager = OrderManager(db_path)
        self.brokers = {}
        self.strategies = {}
        self.is_running = False
        self.order_manager.callbacks['order_submitted'].append(lambda args: print("Order submitted callback triggered " + str(args)))

    def add_broker(self, name: str, broker_type: str, **config) -> bool:
        """Add a broker to the system"""
        try:
            print("above broker...")
            broker = BrokerFactory.create_broker(broker_type, **config)
            print("here at main ...")
            if broker.connect(**config):
                self.brokers[name] = broker
                print("adding broker...")
                self.data_manager.add_broker(name, broker)
                self.order_manager.add_broker(name, broker)
                print(f"Broker '{name}' ({broker_type}) added successfully")
                return True
            else:
                print(f"Failed to connect to broker '{name}'")
                return False

        except Exception as e:
            print(f"Error adding broker '{name}': {e}")
            return False

    def remove_broker(self, name: str):
        """Remove a broker from the system"""
        if name in self.brokers:
            self.brokers[name].disconnect()
            del self.brokers[name]
            print(f"Broker '{name}' removed")

    def get_historical_data(self, symbol: str, exchange: str,
                          security_type: str = "STK", currency: str = "USD",
                          duration: str = "1 D", bar_size: str = "1 hour",
                          broker_name: Optional[str] = None) -> pd.DataFrame:
        """Get historical data for a symbol"""
        contract = Contract(
            symbol=symbol,
            security_type=security_type,
            exchange=exchange,
            currency=currency
        )

        return self.data_manager.get_historical_data(
            contract, duration, bar_size, broker_name
        )

    def subscribe_market_data(self, symbol: str, exchange: str,
                            callback: Callable, security_type: str = "STK",
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
        print("Shutting down trading system...")

        for name, broker in self.brokers.items():
            broker.disconnect()
            print(f"Disconnected from broker '{name}'")

        self.brokers.clear()
        self.is_running = False
        print("Trading system shutdown complete")