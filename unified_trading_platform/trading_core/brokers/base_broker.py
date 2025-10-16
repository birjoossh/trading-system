"""
Base broker interface for the modular trading system.
All broker implementations should inherit from this abstract base class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class OrderType(Enum):
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"

class OrderAction(Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    PENDING = "Pending"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

@dataclass
class Contract:
    """Represents a tradeable instrument"""
    symbol: str
    security_type: str  # STK, CASH, FUT, OPT, etc.
    exchange: str
    currency: str
    local_symbol: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None  # C for Call, P for Put
    multiplier: Optional[str] = None

@dataclass
class Order:
    """Represents a trading order"""
    action: OrderAction
    quantity: int
    order_type: OrderType
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"  # DAY, GTC, IOC, FOK
    account: Optional[str] = None

@dataclass
class Trade:
    """Represents an executed trade"""
    order_id: str
    contract: Contract
    execution_id: str
    quantity: int
    price: float
    timestamp: datetime
    side: OrderAction
    commission: Optional[float] = None

@dataclass
class BarData:
    """Represents OHLC bar data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class TickData:
    """Represents real-time tick data"""
    timestamp: datetime
    exchange: str
    security_type: str # STK, CASH, FUT, OPT, etc.
    symbol: str
    currency: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None

class BrokerInterface(ABC):
    """Abstract base class for all broker implementations"""

    def __init__(self):
        self.is_connected = False
        self.callbacks = {}

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """Establish connection to broker"""
        print("here at base_broker ...")
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """Disconnect from broker"""
        pass

    @abstractmethod
    def get_historical_data(self, contract: Contract, duration: str,
                          bar_size: str, what_to_show: str = "TRADES") -> List[BarData]:
        """Get historical bar data"""
        pass

    @abstractmethod
    def submit_order(self, contract: Contract, order: Order) -> str:
        """Submit an order and return order ID"""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        pass

    @abstractmethod
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get status of an order"""
        pass

    @abstractmethod
    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders"""
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions"""
        pass

    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        pass

    @abstractmethod
    def subscribe_market_data(self, contract: Contract, callback: Callable) -> bool:
        """Subscribe to real-time market data"""
        pass

    @abstractmethod
    def unsubscribe_market_data(self, contract: Contract) -> bool:
        """Unsubscribe from market data"""
        pass

    def register_callback(self, event_type: str, callback: Callable):
        """Register callback for specific events"""
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []
        self.callbacks[event_type].append(callback)

    def trigger_callback(self, event_type: str, *args, **kwargs):
        """Trigger registered callbacks for an event"""
        if event_type in self.callbacks:
            for callback in self.callbacks[event_type]:
                try:
                    callback(*args, **kwargs)
                except Exception as e:
                    print(f"Error in callback {callback.__name__}: {e}")