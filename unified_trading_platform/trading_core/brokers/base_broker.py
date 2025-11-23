"""
Base broker interface for the modular trading system.
All broker implementations should inherit from this abstract base class.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Callable

from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.data_models.contract import Contract
from unified_trading_platform.trading_core.data_models.order import Order
from unified_trading_platform.trading_core.data_models.bar_data import BarData
from unified_trading_platform.trading_core.data_models.market_datatype_enum import MarketDataType
from unified_trading_platform.trading_core.data_models.market_data_subscription import MarketDataSubscription
from unified_trading_platform.trading_core.data_models.option_chain import OptionChain
from unified_trading_platform.trading_core.data_models.greeks import Greeks

# Initialize logger
logger = get_logger(__name__)

class BrokerInterface(ABC):
    """Abstract base class for all broker implementations"""

    def __init__(self):
        self.is_connected = False
        self.callbacks = {}

    @abstractmethod
    def connect(self, **kwargs) -> bool:
        """Establish connection to broker"""
        logger.debug("Base broker connect method called")
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
    def get_option_chain(self, option_contract: Contract) -> OptionChain:
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
                    logger.error(f"Error in callback {callback.__name__}: {e}", exc_info=True)