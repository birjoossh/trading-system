"""
Base broker interface for the modular trading system.
All broker implementations should inherit from this abstract base class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable, Union
from dataclasses import dataclass, field
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

class SecurityType(Enum):
    """Security types for different instruments"""
    STOCK = "STK"
    OPTION = "OPT"
    FUTURE = "FUT"
    CASH = "CASH"
    BOND = "BOND"
    CRYPTO = "CRYPTO"
    FOREX = "CASH"
    INDEX = "IND"
    CFD = "CFD"

class OptionRight(Enum):
    """Option right types"""
    CALL = "C"
    PUT = "P"

class MarketDataType(Enum):
    """Market data types"""
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    FROZEN = "FROZEN"
    DELAYED_FROZEN = "DELAYED_FROZEN"

class TickType(Enum):
    """Common tick types for market data"""
    BID = "BID"
    ASK = "ASK"
    LAST = "LAST"
    HIGH = "HIGH"
    LOW = "LOW"
    CLOSE = "CLOSE"
    VOLUME = "VOLUME"
    BID_SIZE = "BID_SIZE"
    ASK_SIZE = "ASK_SIZE"
    LAST_SIZE = "LAST_SIZE"
    OPEN = "OPEN"
    OPEN_INTEREST = "OPEN_INTEREST"
    DELTA = "DELTA"
    GAMMA = "GAMMA"
    THETA = "THETA"
    VEGA = "VEGA"
    RHO = "RHO"
    IMPLIED_VOLATILITY = "IMPLIED_VOLATILITY"
    OPTION_PRICE = "OPTION_PRICE"

@dataclass
class Contract:
    """Represents a tradeable instrument with enhanced support for options"""
    symbol: str
    security_type: SecurityType
    exchange: str
    currency: str
    local_symbol: Optional[str] = None
    expiry: Optional[str] = None  # Format: YYYYMMDD for options
    strike: Optional[float] = None  # Strike price for options
    right: Optional[OptionRight] = None  # Call or Put for options
    multiplier: Optional[str] = None  # Contract multiplier
    trading_class: Optional[str] = None  # Trading class for options
    primary_exchange: Optional[str] = None  # Primary exchange
    include_expired: bool = False  # Include expired contracts
    sec_id_type: Optional[str] = None  # Security ID type (ISIN, CUSIP, etc.)
    sec_id: Optional[str] = None  # Security ID
    combo_legs: Optional[List[Dict[str, Any]]] = None  # For combo contracts
    combo_legs_descrip: Optional[str] = None  # Description for combo legs
    conId: int = 0

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
    """Enhanced real-time tick data with comprehensive market data support"""
    timestamp: datetime
    exchange: str
    security_type: SecurityType
    symbol: str
    currency: str
    # Basic price data
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    close: Optional[float] = None
    # Size data
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    last_size: Optional[int] = None
    volume: Optional[int] = None
    # Options-specific data
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    option_price: Optional[float] = None
    # Additional market data
    open_interest: Optional[int] = None
    model_option: Optional[bool] = None  # Whether price is model-derived
    # Metadata
    tick_type: Optional[TickType] = None
    market_data_type: Optional[MarketDataType] = None
    raw_data: Optional[Dict[str, Any]] = None  # Store raw broker data

@dataclass
class MarketDataSubscription:
    """Represents a market data subscription"""
    contract: Contract
    subscription_id: str
    market_data_type: MarketDataType = MarketDataType.DELAYED
    snapshot: bool = False
    regulatory_snapshot: bool = False
    generic_tick_list: Optional[List[str]] = None
    callback: Optional[Callable] = None
    is_active: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    last_update: Optional[datetime] = None

@dataclass
class MarketDataError:
    """Represents market data subscription errors"""
    subscription_id: str
    error_code: int
    error_message: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class OptionChain:
    """Represents option chain data for a given underlying"""
    underlying_symbol: str
    underlying_contract: Contract
    expiration_dates: List[str]
    strikes: List[float]
    options: List[Contract]  # List of option contracts
    last_updated: datetime = field(default_factory=datetime.now)

@dataclass
class Greeks:
    """Options Greeks data"""
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    underlying_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

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
    def subscribe_market_data(self, contract: Contract, callback: Callable, 
                             market_data_type: MarketDataType = MarketDataType.DELAYED,
                             snapshot: bool = False, regulatory_snapshot: bool = False,
                             generic_tick_list: Optional[List[str]] = None) -> str:
        """Subscribe to real-time market data and return subscription ID"""
        pass

    @abstractmethod
    def unsubscribe_market_data(self, subscription_id: str) -> bool:
        """Unsubscribe from market data using subscription ID"""
        pass

    @abstractmethod
    def get_market_data_subscriptions(self) -> List[MarketDataSubscription]:
        """Get all active market data subscriptions"""
        pass

    @abstractmethod
    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        """Get detailed information about a specific contract"""
        pass

    @abstractmethod
    def get_option_chain(self, underlying_contract: Contract, 
                        expiration_dates: Optional[List[str]] = None,
                        strikes: Optional[List[float]] = None) -> OptionChain:
        """Get option chain for an underlying instrument"""
        pass

    @abstractmethod
    def get_greeks(self, option_contract: Contract) -> Greeks:
        """Get options Greeks for a specific option contract"""
        pass

    @abstractmethod
    def set_market_data_type(self, market_data_type: MarketDataType) -> bool:
        """Set the market data type (live, delayed, etc.)"""
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