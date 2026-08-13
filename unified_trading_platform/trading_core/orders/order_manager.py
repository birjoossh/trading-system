"""
Order manager for handling trade orders across multiple brokers.
Provides unified interface for order submission, tracking, and management.
"""

from typing import Dict, List, Optional, Callable
from datetime import datetime
import uuid
import sqlite3

from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.data_models import OrderStatus, ManagedOrder, Contract, Order, Trade
from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface

# Initialize logger
logger = get_logger(__name__)


class OrderManager:
    """Manages orders across multiple brokers"""

    def __init__(self, db_path: str = "trading_orders.db"):
        self.db_path = db_path
        self.brokers: Dict[str, BrokerInterface] = {}
        self.orders: Dict[str, ManagedOrder] = {}
        self.callbacks: Dict[str, List[Callable]] = {
            "order_submitted": [],
            "order_filled": [],
            "order_cancelled": [],
            "order_rejected": [],
            "trade_executed": [],
        }
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for order storage"""
        logger.info(f"Initializing database at {self.db_path}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS orders (
                        order_id TEXT PRIMARY KEY,
                        broker_order_id TEXT,
                        broker_name TEXT NOT NULL,
                        symbol TEXT NOT NULL,
                        security_type TEXT NOT NULL,
                        exchange TEXT,
                        currency TEXT,
                        action TEXT NOT NULL,
                        order_type TEXT NOT NULL,
                        quantity INTEGER NOT NULL,
                        limit_price REAL,
                        stop_price REAL,
                        time_in_force TEXT,
                        status TEXT NOT NULL,
                        filled_quantity INTEGER DEFAULT 0,
                        remaining_quantity INTEGER,
                        avg_fill_price REAL DEFAULT 0.0,
                        commission REAL DEFAULT 0.0,
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        strategy_id TEXT,
                        parent_order_id TEXT,
                        notes TEXT,
                        metadata TEXT
                    )
                """)

                # Create trades table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        trade_id TEXT PRIMARY KEY,
                        order_id TEXT NOT NULL,
                        broker_trade_id TEXT,
                        execution_id TEXT,
                        quantity INTEGER NOT NULL,
                        price REAL NOT NULL,
                        commission REAL DEFAULT 0.0,
                        realized_pnl REAL,
                        timestamp TIMESTAMP NOT NULL,
                        exchange TEXT,
                        liquidity TEXT,
                        FOREIGN KEY (order_id) REFERENCES orders (order_id)
                    )
                """)
            logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing database: {e}", exc_info=True)
            raise

    def add_broker(self, name: str, broker: BrokerInterface):
        """Add a broker for order management"""
        self.brokers[name] = broker

        # Register callbacks for broker events
        broker.register_callback("order_status", self._on_order_status)
        broker.register_callback("trade_execution", self._on_trade_execution)

    def submit_order(self, contract: Contract, order: Order, broker_name: str) -> str:
        """Submit an order through specified broker"""
        if broker_name not in self.brokers:
            raise ValueError(f"Broker '{broker_name}' not found")

        broker = self.brokers[broker_name]

        # Create managed order
        order_id = str(uuid.uuid4())
        managed_order = ManagedOrder(
            order_id=order_id,
            broker_order_id=None,
            contract=contract,
            order=order,
            broker_name=broker_name,
            status=OrderStatus.PENDING,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            remaining_quantity=order.quantity,
        )

        try:
            # Submit to broker
            broker_order_id = broker.submit_order(contract, order)
            managed_order.broker_order_id = broker_order_id
            managed_order.status = OrderStatus.SUBMITTED

            # Store order
            self.orders[order_id] = managed_order
            self._save_order(managed_order)

            # Trigger callbacks
            self._trigger_callbacks("order_submitted", managed_order)

            return order_id

        except Exception as e:
            managed_order.status = OrderStatus.REJECTED
            self.orders[order_id] = managed_order
            self._save_order(managed_order)

            self._trigger_callbacks("order_rejected", managed_order)
            raise e

    def cancel_order(self, order_id: str, broker_name: Optional[str] = None) -> bool:
        """Cancel an active order"""
        try:
            logger.info(f"Cancelling order {order_id}")
            order = self.get_order(order_id)
            if not order:
                logger.warning(f"Order {order_id} not found")
                return False

            if broker_name and order.broker_name != broker_name:
                logger.warning(f"Order {order_id} is not managed by broker {broker_name}")
                return False

            broker = self.brokers.get(order.broker_name)
            if not broker:
                logger.error(f"Broker {order.broker_name} not found for order {order_id}")
                return False

            success = broker.cancel_order(order.broker_order_id or order_id)
            if success:
                logger.info(f"Successfully submitted cancel order {order_id}")
            else:
                logger.warning(f"Failed to submit cancel order {order_id}")
            return success
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
            return False

    def get_order(self, order_id: str) -> Optional[ManagedOrder]:
        """Get order by ID"""
        return self.orders.get(order_id)

    def get_orders(self, status: Optional[OrderStatus] = None, broker_name: Optional[str] = None) -> List[ManagedOrder]:
        """Get orders with optional filtering"""
        orders = list(self.orders.values())

        if status:
            orders = [o for o in orders if o.status == status]

        if broker_name:
            orders = [o for o in orders if o.broker_name == broker_name]

        return orders

    def get_positions(self, broker_name: Optional[str] = None) -> List[Dict]:
        """Get current positions from broker(s)"""
        positions = []

        if broker_name:
            broker = self.brokers[broker_name]
            positions.extend(broker.get_positions())
        else:
            for broker in self.brokers.values():
                positions.extend(broker.get_positions())

        return positions

    def register_callback(self, event_type: str, callback: Callable):
        """Register callback for order events"""
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
        else:
            raise ValueError(f"Unknown event type: {event_type}")

    def _on_order_status(self, broker_order_id: str, order_info: Dict):
        """Handle order status updates from broker"""
        # Find our managed order
        managed_order = None
        for order in self.orders.values():
            if order.broker_order_id == broker_order_id:
                managed_order = order
                break

        if not managed_order:
            return

        # Update order status
        old_status = managed_order.status
        managed_order.status = order_info.get("status", managed_order.status)
        managed_order.filled_quantity = order_info.get("filled", 0)
        managed_order.remaining_quantity = order_info.get("remaining", managed_order.remaining_quantity)
        managed_order.avg_fill_price = order_info.get("avg_fill_price", 0.0)
        managed_order.updated_at = datetime.now()

        # Save updates
        self._save_order(managed_order)

        # Trigger appropriate callback
        if old_status != managed_order.status:
            if managed_order.status == OrderStatus.FILLED:
                self._trigger_callbacks("order_filled", managed_order)
            elif managed_order.status == OrderStatus.CANCELLED:
                self._trigger_callbacks("order_cancelled", managed_order)

    def _on_trade_execution(self, trade: Trade):
        """Handle trade execution from broker"""
        # Find the managed order
        managed_order = None
        for order in self.orders.values():
            if order.broker_order_id == trade.order_id:
                managed_order = order
                break

        if managed_order:
            managed_order.trades.append(trade)
            self._save_trade(trade, managed_order.order_id)
            self._trigger_callbacks("trade_executed", trade)

    def _save_order(self, order: ManagedOrder):
        """Save order to database"""
        logger.debug(f"Saving order {order.order_id} to database")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders 
                (order_id, broker_order_id, broker_name, symbol, exchange, 
                 security_type, currency, action, quantity, order_type, 
                 limit_price, stop_price, time_in_force, status, 
                 filled_quantity, remaining_quantity, avg_fill_price, 
                 commission, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    order.order_id,
                    order.broker_order_id,
                    order.broker_name,
                    order.contract.symbol,
                    order.contract.exchange,
                    order.contract.security_type.value,
                    order.contract.currency,
                    order.order.action.value,
                    order.order.quantity,
                    order.order.order_type.value,
                    order.order.limit_price,
                    order.order.stop_price,
                    order.order.time_in_force,
                    order.status.value,
                    order.filled_quantity,
                    order.remaining_quantity,
                    order.avg_fill_price,
                    order.commission,
                    order.created_at.isoformat(),
                    order.updated_at.isoformat(),
                ),
            )

    def _save_trade(self, trade: Trade, order_id: str):
        """Save trade to database"""
        trade_id = trade.trade_id or str(uuid.uuid4())

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO trades
                (trade_id, order_id, broker_trade_id, execution_id,
                 quantity, price, commission, timestamp, exchange)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    trade_id,
                    order_id,
                    trade.order_id,
                    trade.execution_id,
                    trade.quantity,
                    trade.price,
                    trade.commission,
                    trade.timestamp.isoformat(),
                    trade.contract.exchange,
                ),
            )

    def _trigger_callbacks(self, event_type: str, *args, **kwargs):
        """Trigger all callbacks for an event"""
        callbacks = self.callbacks.get(event_type, [])
        if not callbacks:
            return

        logger.debug(f"Triggering {len(callbacks)} callbacks for event: {event_type}")
        for callback in callbacks:
            try:
                callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in {event_type} callback: {e}", exc_info=True)

    def get_order_history(
        self, symbol: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get order history with optional filtering"""
        query = "SELECT * FROM orders WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        if start_date:
            query += " AND created_at >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND created_at <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY created_at DESC"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            columns = [description[0] for description in cursor.description]
            results = []

            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

        return results

    def get_trade_history(
        self, symbol: Optional[str] = None, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """Get trade history with optional filtering"""
        query = "SELECT * FROM trades WHERE 1=1"
        params = []

        if symbol:
            query += " AND symbol = ?"
            params.append(symbol)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat())

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat())

        query += " ORDER BY timestamp DESC"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, params)
            columns = [description[0] for description in cursor.description]
            results = []

            for row in cursor.fetchall():
                results.append(dict(zip(columns, row)))

        return results
