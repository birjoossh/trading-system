"""
Interactive Brokers broker implementation.
Implements the BrokerInterface for IB TWS/Gateway API.
"""

import threading
import time
from typing import Dict, List, Callable, Any
from datetime import datetime

try:
    from ibapi.common import MarketDataTypeEnum
    from ibapi.contract import Contract as IBContract
    from ibapi.order import Order as IBOrder

    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.data_models import Contract
from unified_trading_platform.trading_core.data_models import Order, OrderStatus, OrderType
from unified_trading_platform.trading_core.data_models import OptionChain
from unified_trading_platform.trading_core.data_models import TickData

from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker_options import IBOptionsMixin
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_client import IBClient
from unified_trading_platform.trading_core.brokers.interactive_brokers.common import CommonMixin
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_market_data import IBMarketDataMixin
from unified_trading_platform.trading_core.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)


class IBBroker(BrokerInterface):
    """Interactive Brokers implementation"""

    def __init__(self, host="127.0.0.1", port=7497, client_id=1):
        logger.info("Initializing IBBroker...")
        super().__init__()
        if not IB_AVAILABLE:
            raise ImportError("IB API not available. Install with: pip install ibapi")

        self.client = IBClient(self)
        self.market_data_subscriptions = {}  # Enhanced market data tracking
        self.market_data = IBMarketDataMixin(self.client, self.market_data_subscriptions)
        self.options = IBOptionsMixin(self.client, self.market_data)
        self.host = host
        self.host = host
        self.port = port  # Paper trading port
        self.client_id = client_id
        self.next_order_id = None
        self.orders = {}
        self.positions = []
        self.account_info = {}  # unimplemented
        self.accounts = []
        self.option_chains = {}  # Cache for option chains
        self.requestid_cachekey = {}  # a dict map the req id to option cache key
        self.greeks_data = {}  # Cache for Greeks data
        self.market_data_type = MarketDataTypeEnum.DELAYED  # Default to delayed
        self._api_thread = None
        self._connected_event = threading.Event()
        self._lock = threading.RLock()
        logger.info("IBBroker initialization complete")

    def connect(self) -> bool:
        """Connect to IB TWS/Gateway ..."""
        logger.info(f"Attempting to connect to IB at {self.host}:{self.port} with client ID {self.client_id}")

        if self.is_connected:
            logger.info("Already connected to IB")
            return True

        self._connected_event.clear()
        try:
            self.client.connect(self.host, self.port, self.client_id)
            logger.debug("Connection request sent to IB...")

            # Start API thread
            self._api_thread = threading.Thread(target=self.client.run, daemon=True)
            self._api_thread.start()

            # Wait for connection with timeout
            if not self._connected_event.wait(timeout=20):
                logger.error("Connection timeout - IB did not respond within 20 seconds")
                try:
                    self.client.disconnect()
                except Exception:
                    pass
                return False

            self.is_connected = True
            logger.info(f"Successfully connected to IB at {self.host}:{self.port} with client ID {self.client_id}")

            # Update account info
            self._req_account_updates()
            return True

        except Exception as e:
            logger.error(f"Connection error: {e}", exc_info=True)
            if "502" in str(e):
                logger.error("Make sure TWS or IB Gateway is running 4002: IB Gateway Simulated Trading")
            return False

    def disconnect(self) -> bool:
        """Disconnect from IB"""
        try:
            if self.client:
                self.client.disconnect()
            self.is_connected = False
            self._connected_event.clear()
            if self._api_thread and self._api_thread.is_alive():
                self._api_thread.join(timeout=2.0)
            logger.info("Disconnected from IB")
            return True
        except Exception as e:
            logger.error(f"Disconnect error: {e}", exc_info=True)
            return False

    def _req_account_updates(self):
        accounts = self.client.reqManagedAccts()

    def _create_ib_contract(self, contract: Contract) -> IBContract:
        """Convert our Contract to IB Contract with enhanced options support"""
        ib_contract = IBContract()
        ib_contract.symbol = contract.symbol
        ib_contract.secType = contract.security_type.value
        ib_contract.exchange = contract.exchange
        ib_contract.currency = contract.currency

        # Enhanced options support
        if contract.local_symbol:
            ib_contract.localSymbol = contract.local_symbol
        if contract.expiry:
            ib_contract.lastTradeDateOrContractMonth = contract.expiry
        if contract.strike:
            ib_contract.strike = contract.strike
        if contract.option_right:
            ib_contract.option_right = contract.option_right
        if contract.multiplier:
            ib_contract.multiplier = contract.multiplier
        if contract.primary_exchange:
            ib_contract.primaryExchange = contract.primary_exchange
        if contract.include_expired:
            ib_contract.includeExpired = contract.include_expired
        return ib_contract

    def _create_ib_order(self, order: Order) -> IBOrder:
        """Convert our Order to IB Order"""
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and (
            order.limit_price is None or order.limit_price <= 0
        ):
            raise ValueError("limit_price must be positive for LIMIT/STOP_LIMIT orders")
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and (
            order.stop_price is None or order.stop_price <= 0
        ):
            raise ValueError("stop_price must be positive for STOP/STOP_LIMIT orders")
        ib_order = IBOrder()
        ib_order.action = order.action.value
        ib_order.totalQuantity = int(order.quantity)
        ib_order.orderType = order.order_type.value

        ib_order.eTradeOnly = False
        ib_order.firmQuoteOnly = False

        if order.limit_price is not None:
            ib_order.lmtPrice = float(order.limit_price)
        if order.stop_price:
            ib_order.auxPrice = float(order.stop_price)
        if order.time_in_force is not None:
            ib_order.tif = str(order.time_in_force)
        if order.account is not None:
            ib_order.account = str(order.account)
        ib_order.eTradeOnly = False
        return ib_order

    def get_historical_data(
        self, contract: Contract, duration: str, bar_size: str, what_to_show: str = "TRADES"
    ) -> List[TickData]:
        """Get historical bar data"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

    def get_historical_data(
        self, contract: Contract, duration: str, bar_size: str, what_to_show: str = "TRADES"
    ) -> List[TickData]:
        """Get historical bar data"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        ib_contract = CommonMixin.create_ib_contract(contract)
        try:
            # Request historical data via async client
            future = self.client.get_historical_data_async(ib_contract, duration, bar_size, what_to_show)
            
            # Wait for data (30 seconds timeout)
            try:
                ib_bars = future.result(timeout=30)
            except TimeoutError:
                raise TimeoutError("Timeout waiting for historical data")

            # Convert to our TickData format
            bars = []
            for bar in ib_bars:
                try:
                    bar_data = TickData(
                        timestamp=datetime.strptime(bar.date, "%Y%m%d %H:%M:%S"),
                        exchange=contract.exchange,
                        symbol=contract.symbol,
                        security_type=contract.security_type,
                        currency=contract.currency,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
                    bars.append(bar_data)
                except (ValueError, AttributeError) as e:
                    logger.error(f"Error parsing bar data: {e}", exc_info=True)
                    continue
            return bars

        except Exception as e:
            logger.error(f"Error getting historical data: {e}", exc_info=True)
            raise

    def submit_order(self, contract: Contract, order: Order) -> str:
        """Submit an order"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        if self.next_order_id is None:
            raise Exception("No valid order ID available")

        order_id = str(self.next_order_id)
        self.next_order_id += 1

        ib_contract = CommonMixin.create_ib_contract(contract)
        ib_order = self._create_ib_order(order)

        # Store order info
        self.orders[order_id] = {
            "contract": contract,
            "order": order,
            "status": OrderStatus.PENDING,
            "filled": 0,
            "remaining": order.quantity,
            "avg_fill_price": 0.0,
            "timestamp": datetime.now(),
        }

        try:
            # Submit order
            self.client.placeOrder(int(order_id), ib_contract, ib_order)
            return order_id
        except Exception as e:
            logger.error(f"Error submitting order {order_id}: {e}", exc_info=True)
            del self.orders[order_id]
            raise e

        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        try:
            self.client.cancelOrder(int(order_id))
            return True
        except Exception as e:
            logger.error(f"Error cancelling order {order_id}: {e}", exc_info=True)
            return False

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """Get order status"""
        return self.orders.get(order_id, {})

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Get all orders"""
        return list(self.orders.values())

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get positions"""
        return self.positions

    def get_account_info(self) -> Dict[str, Any]:
        """Get account information"""
        return self.account_info

    def set_market_data_type(self, market_data_type: str) -> bool:
        raise NotImplementedError

    def subscribe_market_data(self, contract: Contract, callback: Callable, **kwargs):
        self.market_data.subscribe_market_data(contract, callback, **kwargs)

    def unsubscribe_market_data(self, subscription_id: str) -> bool:
        self.market_data.unsubscribe_market_data(subscription_id)

    def get_market_data_subscriptions(self) -> List[str]:
        return self.market_data.get_market_data_subscriptions()

    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        if not self.is_connected:
            raise Exception("Not connected to broker")

    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        if not self.is_connected:
            raise Exception("Not connected to broker")

        try:
            ib_contract = self._create_ib_contract(contract)
            future = self.client.get_contract_details_async(ib_contract)

            # Wait for response with timeout (10 seconds)
            # note: request manager creates a future that resolves when contractDetailsEnd is called
            # this means we wait for ALL details to arrive, not just the first one.
            try:
                results = future.result(timeout=10)
            except TimeoutError:
                raise TimeoutError("Timed out waiting for contract details")
            except Exception as e:
                raise Exception(f"Error getting contract details: {e}")

            if not results:
                raise Exception("No contract details found")
            
            # Return the first detail to match previous behavior
            return results[0]

        except Exception as e:
            logger.error(f"Error in get_contract_details: {e}", exc_info=True)
            raise Exception(f"Error in get_contract_details: {str(e)}")

    def get_option_chain(self, underlying_contract: Contract) -> OptionChain:
        """
        Backward compatible wrapper that uses the enhanced get_option_chain2 implementation.
        """
        expiration_dates = None
        strikes = None
        ib_option_chain = IBOptionsMixin(self.client, self)
        return ib_option_chain.get_option_chain(underlying_contract, expiration_dates, strikes)

    def get_greeks(self, option_contract: Contract) -> Dict[str, Any]:
        pass
