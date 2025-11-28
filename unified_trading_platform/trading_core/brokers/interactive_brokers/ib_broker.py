"""
Interactive Brokers broker implementation.
Implements the BrokerInterface for IB TWS/Gateway API.
"""

import threading
import time
from typing import Dict, List, Optional, Callable, Any, Set, Tuple
from datetime import datetime

import pandas as pd

try:
    from ibapi.client import EClient
    from ibapi.common import BarData, TickerId, OrderId, MarketDataTypeEnum
    from ibapi.contract import Contract as IBContract
    from ibapi.contract import ContractDetails
    from ibapi.order import Order as IBOrder
    from ibapi.wrapper import EWrapper
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False

from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.data_models import Contract
from unified_trading_platform.trading_core.data_models import (Order, OrderAction, OrderStatus, OrderType)
from unified_trading_platform.trading_core.data_models import OptionChain, StrikeGroup, ExpirationGroup
from unified_trading_platform.trading_core.data_models import OptionContract
from unified_trading_platform.trading_core.data_models import OptionRight
from unified_trading_platform.trading_core.data_models import MarketDataType
from unified_trading_platform.trading_core.data_models import TickData
from unified_trading_platform.trading_core.data_models import TickType
from unified_trading_platform.trading_core.data_models import UnderlyingInfo
from unified_trading_platform.trading_core.utils.utils import generate_unique_id
from unified_trading_platform.trading_core.utils.logger import get_logger

# Initialize logger
logger = get_logger(__name__)

class IBBroker(BrokerInterface):
    """Interactive Brokers implementation"""

    def __init__(self, host, port, client_id=1):
        logger.info("Initializing IBBroker...")
        super().__init__()
        if not IB_AVAILABLE:
            raise ImportError("IB API not available. Install with: pip install ibapi")

        self.client = IBClient(self)
        self.host = host
        self.port = port  # Paper trading port
        self.client_id = client_id
        self.next_order_id = None
        self.historical_data = {}
        self.market_data = {}
        self.market_data_subscriptions = {}  # Enhanced market data tracking
        self.orders = {}
        self.positions = []
        self.account_info = {}  # unimplemented
        self.accounts = []
        self.option_chains = {}  # Cache for option chains
        self.requestid_cachekey = {} # a dict map the req id to option cache key
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

        # Debug output for options
        # if contract.security_type == SecurityType.OPTION:
        #     logger.debug(f"Created IB option contract: Symbol={ib_contract.symbol}, SecType={ib_contract.secType}, "
        #                 f"Exchange={ib_contract.exchange}, Expiry={ib_contract.lastTradeDateOrContractMonth}, "
        #                 f"Strike={ib_contract.strike}, Right={ib_contract.right}, Multiplier={ib_contract.multiplier}")

        return ib_contract

    def _create_ib_order(self, order: Order) -> IBOrder:
        """Convert our Order to IB Order"""
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and (order.limit_price is None or order.limit_price <= 0):
            raise ValueError("limit_price must be positive for LIMIT/STOP_LIMIT orders")
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and (order.stop_price is None or order.stop_price <= 0):
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

    def get_historical_data(self, contract: Contract, duration: str,
                          bar_size: str, what_to_show: str = "TRADES") -> List[TickData]:
        """Get historical bar data"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        req_id = len(self.historical_data) + 1000
        self.historical_data[req_id] = []

        ib_contract = self._create_ib_contract(contract)

        try:
            # Request historical data
            self.client.reqHistoricalData(
                req_id, ib_contract, "", duration, bar_size, what_to_show, 1, 1, False, []
            )

            # Wait for data
            timeout = 30
            start_time = time.time()
            while len(self.historical_data[req_id]) == 0 and (time.time() - start_time) < timeout:
                time.sleep(1) # sleep 1 sec

            # Convert to our TickData format
            bars = []
            for bar in self.historical_data[req_id]:
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
                        volume=bar.volume
                    )
                    bars.append(bar_data)
                except (ValueError, AttributeError) as e:
                    logger.error(f"Error parsing bar data: {e}", exc_info=True)
                    continue
        finally:
            if req_id in self.historical_data:
                del self.historical_data[req_id]

        return bars

    def submit_order(self, contract: Contract, order: Order) -> str:
        """Submit an order"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        if self.next_order_id is None:
            raise Exception("No valid order ID available")

        order_id = str(self.next_order_id)
        self.next_order_id += 1

        ib_contract = self._create_ib_contract(contract)
        ib_order = self._create_ib_order(order)

        # Store order info
        self.orders[order_id] = {
            'contract': contract,
            'order': order,
            'status': OrderStatus.PENDING,
            'filled': 0,
            'remaining': order.quantity,
            'avg_fill_price': 0.0,
            'timestamp': datetime.now()
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
        """Subscribe to market data with enhanced options support"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        req_id, _ = generate_unique_id(prefix="sub_")

        market_data_type = kwargs.get('market_data_type', MarketDataType.DELAYED)
        snapshot = kwargs.get('snapshot', False)
        regulatory_snapshot = kwargs.get('regulatory_snapshot', False)
        generic_tick_list = kwargs.get('generic_tick_list', [])
        mdoff = "" if not generic_tick_list else "mdoff"  # Check if list is empty

        self.market_data_subscriptions[req_id] = {
            'contract': contract,
            'callback': callback,
            'is_active': False,
            'data': {}
        }

        logger.debug("Creating IB contract for market data subscription")
        ib_contract = self._create_ib_contract(contract)
        try:
            # Set market data type
            md_type_map = {
                MarketDataType.LIVE: 1,
                MarketDataType.FROZEN: 2,
                MarketDataType.DELAYED: 3,
                MarketDataType.DELAYED_FROZEN: 4
            }
            self.client.reqMarketDataType(md_type_map.get(market_data_type, 3))
            self.client.reqMktData(req_id, ib_contract, mdoff, snapshot, regulatory_snapshot, generic_tick_list)
            self.market_data_subscriptions[req_id]['is_active'] = True
            logger.info(f"Market data subscription completed: {req_id}")
            return req_id
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}", exc_info=True)
            if req_id in self.market_data_subscriptions:
                del self.market_data_subscriptions[req_id]
            raise e

    def unsubscribe_market_data(self, subscription_id: str) -> bool:
        """Unsubscribe from market data using subscription ID"""
        if subscription_id not in self.market_data_subscriptions:
            return False
        try:
            self.client.cancelMktData(subscription_id)
            del self.market_data_subscriptions[subscription_id]
        except Exception as e:
            logger.error(f"Error unsubscribing from market data: {e}", exc_info=True)
            return False
        return True

    def get_market_data_subscriptions(self) -> List[str]:
        """Get all active market data subscriptions"""
        return [sub for sub in self.market_data_subscriptions.values() if sub['is_active']]
    
    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        """
            Get detailed information about a specific contract using IB's reqContractDetails.
            
            Args:
                contract: The contract to get details for
                
            Returns:
                Dictionary containing contract details with fields like:
                - symbol: Contract symbol
                - security_type: Type of security (STK, OPT, FUT, etc.)
                - exchange: Primary exchange
                - currency: Currency
                - description: Full description
                - min_tick: Minimum price increment
                - order_types: Supported order types
                - valid_exchanges: List of valid exchanges
                - and more...
                
            Raises:
                Exception: If not connected or error fetching details
        """
        if not self.is_connected:
            raise Exception("Not connected to broker")
            
        req_id = len(self.client.pending_contract_details) + 5000
        response_received = threading.Event()
        self.client.pending_contract_details[req_id] = {
            'event': response_received,
            'details': None,
            'error': None
        }
        
        try:
            ib_contract = self._create_ib_contract(contract)
            self.client.reqContractDetails(req_id, ib_contract)
            
            # Wait for response with timeout (10 seconds)
            if not response_received.wait(timeout=10):
                raise TimeoutError("Timed out waiting for contract details")
                
            # Get the result
            if req_id in self.client.pending_contract_details:
                result = self.client.pending_contract_details[req_id]
                if result['error']:
                    raise Exception(f"Error getting contract details: {result['error']}")
                if not result['details']:
                    raise Exception("No contract details found")
                return result['details']
                
            raise Exception("Failed to get contract details")
            
        except Exception as e:
            if req_id in self.client.pending_contract_details:
                del self.client.pending_contract_details[req_id]
            raise Exception(f"Error in get_contract_details: {str(e)}")

    def get_option_chain(self, underlying_contract: Contract, 
                        expiration_dates: Optional[List[str]] = None,
                        strikes: Optional[List[float]] = None) -> OptionChain:
        """Get option chain for an underlying instrument"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        # Request option chain from IB
        req_id = len(self.option_chains) + 3000
        
        try:
            response_received = threading.Event()
            self.client.pending_option_chains[req_id] = {
                'event': response_received,
                'underlying_contract': underlying_contract,
                'result': None
            }
            logger.debug(f"underlying conId = {underlying_contract.conId if hasattr(underlying_contract, 'conId') else 0}")
            # Request option chaino
            logger.info(f"option exchange = {underlying_contract.exchange}")
            ib_option_contract = self._create_ib_contract(underlying_contract)
            self.client.reqContractDetails(req_id, ib_option_contract)

            # Wait for response till timeout
            if not response_received.wait(timeout=20):
                del self.client.pending_option_chains[req_id]
                raise TimeoutError("Timeout waiting for option chain")

            if req_id in self.client.pending_option_chains and self.client.pending_option_chains[req_id].get('result'):
                logger.debug("Received option chain results")
                option_chain = self.client.pending_option_chains[req_id].get('result')
                #self.option_chains[cache_key] = option_chain
                del self.client.pending_option_chains[req_id]
                return option_chain
        except Exception as e:
            logger.error(f"Error getting option chain: {e}", exc_info=True)
            if req_id in self.client.pending_option_chains:
                del self.client.pending_option_chains[req_id]
            raise e
        return None

    def get_option_chain2(self, underlying_contract: Contract, 
                        expiration_dates: Optional[List[str]] = None,
                        strikes: Optional[List[float]] = None) -> OptionChain:
        """Get option chain for an underlying instrument"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        # Request option chain from IB
        req_id = len(self.option_chains) + 3000
        
        try:
            response_received = threading.Event()
            self.client.pending_option_chains[req_id] = {
                'event': response_received,
                'underlying_contract': underlying_contract,
                'result': None
            }
            logger.debug(f"underlying conId = {underlying_contract.conId if hasattr(underlying_contract, 'conId') else 0}")
            # Request option chaino
            logger.info(f"option exchange = {underlying_contract.exchange}")
            self.client.reqSecDefOptParams(req_id, underlying_contract.symbol, underlying_contract.exchange, \
                    underlying_contract.security_type.value, underlying_contract.conId \
                        if hasattr(underlying_contract, 'conId') else 0)

            # Wait for response till timeout
            if not response_received.wait(timeout=20):
                del self.client.pending_option_chains[req_id]
                raise TimeoutError("Timeout waiting for option chain")

            if req_id in self.client.pending_option_chains and self.client.pending_option_chains[req_id].get('result'):
                logger.debug("Received option chain results")
                option_chain = self.client.pending_option_chains[req_id].get('result')
                #self.option_chains[cache_key] = option_chain
                del self.client.pending_option_chains[req_id]
                return option_chain
        except Exception as e:
            logger.error(f"Error getting option chain: {e}", exc_info=True)
            if req_id in self.client.pending_option_chains:
                del self.client.pending_option_chains[req_id]
            raise e
        return None

    def get_greeks(self, option_contract: Contract) -> Dict[str, Any]:
        pass
    #     """Get options Greeks for a specific option contract"""
    #     if not self.is_connected:
    #         raise Exception("Not connected to broker")
            
    #     # Check cache first
    #     cache_key = f"{option_contract.symbol}_{option_contract.strike}_{option_contract.right}_{option_contract.expiry}"
    #     if cache_key in self.greeks_data:
    #         cached_greeks = self.greeks_data[cache_key]
    #         if (datetime.now() - cached_greeks.timestamp).seconds < 60:  # 1 minute cache
    #             return cached_greeks
        
    #     # Request Greeks from market data
    #     # This would typically be done by subscribing to market data with Greeks
    #     # For now, return a placeholder
    #     greeks = Greeks()
    #     self.greeks_data[cache_key] = greeks
    #     return greeks

class IBClient(EWrapper, EClient):
    """IB API client wrapper"""

    def __init__(self, broker):
        EClient.__init__(self, self)
        self.broker = broker
        self.pending_option_chains = {}
        self.pending_contract_details = {}

    def nextValidId(self, orderId: OrderId):
        """Receive next valid order ID"""
        self.broker.next_order_id = orderId
        try:
            self.broker._connected_event.set()
        except Exception:
            pass

    def historicalData(self, reqId: int, bar: BarData):
        """Receive historical data"""
        if reqId in self.broker.historical_data:
            self.broker.historical_data[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Historical data complete"""
        pass

    def tickPrice(self, reqId: int, tickType: int, value: float, attrib):
        """Receive tick price data with enhanced options support"""
        if reqId in self.broker.market_data_subscriptions:
            contract: Contract = self.broker.market_data_subscriptions[reqId]['contract']

            # Enhanced tick type mapping for options and stocks
            tick_mapping = {
                # Live ticks
                1: ('bid', TickType.BID),
                2: ('ask', TickType.ASK),
                4: ('last', TickType.LAST),
                6: ('high', TickType.HIGH),
                7: ('low', TickType.LOW),
                9: ('close', TickType.CLOSE),
                14: ('open', TickType.OPEN),
                # Delayed ticks
                66: ('bid', TickType.BID),
                67: ('ask', TickType.ASK),
                68: ('last', TickType.LAST),
                70: ('high', TickType.HIGH),
                71: ('low', TickType.LOW),
                75: ('close', TickType.CLOSE),
                76: ('open', TickType.OPEN),
                # Options-specific ticks
                101: ('delta', TickType.DELTA),
                106: ('gamma', TickType.GAMMA),
                111: ('theta', TickType.THETA),
                115: ('vega', TickType.VEGA),
                117: ('rho', TickType.RHO),
                104: ('implied_volatility', TickType.IMPLIED_VOLATILITY),
                100: ('option_price', TickType.OPTION_PRICE)
            }
            if tickType not in tick_mapping:
                logger.error(f"Unknown tick type while receiving tick price data: {tickType}")
                return

            field_name, tick_type = tick_mapping[tickType]

            # Create enhanced tick data
            tick_data = T1ickData(
                timestamp=datetime.now(),
                exchange=contract.exchange,
                security_type=contract.security_type,
                currency=contract.currency,
                symbol=contract.symbol,
                bid=value if field_name == 'bid' else None,
                ask=value if field_name == 'ask' else None,
                last=value if field_name == 'last' else None,
                high=value if field_name == 'high' else None,
                low=value if field_name == 'low' else None,
                open=value if field_name == 'open' else None,
                close=value if field_name == 'close' else None,
                # Options-specific data
                delta=value if field_name == 'delta' else None,
                gamma=value if field_name == 'gamma' else None,
                theta=value if field_name == 'theta' else None,
                vega=value if field_name == 'vega' else None,
                rho=value if field_name == 'rho' else None,
                implied_volatility=value if field_name == 'implied_volatility' else None,
                option_price=value if field_name == 'option_price' else None,
            )

            if self.broker.market_data_subscriptions[reqId]['callback']:
                self.broker.market_data_subscriptions[reqId]['callback'](tick_data)

    def tickSize(self, reqId: int, tickType: int, value: int):
        """Receive tick size data with enhanced support"""
        if reqId in self.broker.market_data_subscriptions:
            subscription = self.broker.market_data_subscriptions[reqId]
            contract: Contract = subscription['contract']
            
            # Enhanced size tick mapping
            size_mapping = {
                # Live size ticks
                0: ('bid_size', TickType.BID_SIZE),
                3: ('ask_size', TickType.ASK_SIZE), 
                5: ('last_size', TickType.LAST_SIZE),
                8: ('volume', TickType.VOLUME),
                # Delayed size ticks
                69: ('bid_size', TickType.BID_SIZE),
                70: ('ask_size', TickType.ASK_SIZE),
                71: ('ask_size', TickType.LAST_SIZE),
                74: ('volume', TickType.VOLUME)
            }
            if tickType not in size_mapping:
                logger.error(f"Unknown tick type while receiving tick size data: {tickType}")
                return
            field_name, _ = size_mapping[tickType]

            # Create enhanced tick data
            tick_data = TickData(
                timestamp=datetime.now(),
                exchange=contract.exchange,
                security_type=contract.security_type,
                currency=contract.currency,
                symbol=contract.symbol,
                bid_size=value if field_name == 'bid_size' else None,
                ask_size=value if field_name == 'ask_size' else None,
                last_size=value if field_name == 'last_size' else None,
                volume=value if field_name == 'volume' else None,
                open_interest=value if field_name == 'open_interest' else None
            )
            if subscription['callback']:
                subscription['callback'](tick_data)

    def orderStatus(self, orderId: OrderId, status: str, filled: float,
                   remaining: float, avgFillPrice: float, permId: int,
                   parentId: int, lastFillPrice: float, clientId: int,
                   whyHeld: str, mktCapPrice: float):
        """Receive order status updates"""
        order_id = str(orderId)
        if order_id in self.broker.orders:
            # Map IB status strings to our OrderStatus enum
            status_mapping = {
                'PendingSubmit': OrderStatus.PENDING,
                'PendingCancel': OrderStatus.PENDING,
                'PreSubmitted': OrderStatus.PENDING,
                'Submitted': OrderStatus.SUBMITTED,
                'ApiPending': OrderStatus.PENDING,
                'ApiCancelled': OrderStatus.CANCELLED,
                'Cancelled': OrderStatus.CANCELLED,
                'Filled': OrderStatus.FILLED,
                'PartiallyFilled': OrderStatus.SUBMITTED,
                'Rejected': OrderStatus.REJECTED,
                'Inactive': OrderStatus.REJECTED,
                'Rejected': OrderStatus.REJECTED
            }
            # Convert IB status to our enum, default to PENDING if unknown
            mapped_status = status_mapping.get(status, OrderStatus.PENDING)
            self.broker.orders[order_id].update({
                'status': mapped_status,
                'filled': filled,
                'remaining': remaining,
                'avg_fill_price': avgFillPrice
            })
            # Trigger callback
            self.broker.trigger_callback('order_status', order_id, self.broker.orders[order_id])

    def openOrder(self, orderId: OrderId, contract, order, orderState):
        """Receive open order info"""
        pass

    def execDetails(self, reqId: int, contract, execution):
        """Receive execution details"""
        side_map = {
            "BOT" : OrderAction.BUY,
            "SLD" : OrderAction.SELL
        }
        trade = Trade(
            order_id=str(execution.orderId),
            contract=Contract(
                symbol=contract.symbol,
                security_type=contract.secType,
                exchange=contract.exchange,
                currency=contract.currency
            ),
            execution_id=execution.execId,
            quantity=execution.shares,
            price=execution.price,
            timestamp=datetime.strptime(execution.time, "%Y%m%d %H:%M:%S"),
            side=OrderAction(side_map[execution.side])
        )

        # Trigger callback
        self.broker.trigger_callback('trade_execution', trade)

    def position(self, account: str, contract, position: float, avgCost: float):
        """Receive position updates"""
        position_data = {
            'account': account,
            'symbol': contract.symbol,
            'security_type': contract.secType,
            'exchange': contract.exchange,
            'currency': contract.currency,
            'position': position,
            'avg_cost': avgCost
        }

        # Update positions list
        existing = False
        for i, pos in enumerate(self.broker.positions):
            if (pos['symbol'] == contract.symbol and
                pos['account'] == account):
                self.broker.positions[i] = position_data
                existing = True
                break

        if not existing:
            self.broker.positions.append(position_data)

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        """Receive account value updates"""
        self.broker.account_info[key] = {
            'value': val,
            'currency': currency,
            'account': accountName
        }

    def managedAccounts(self, accountsList:str):
        self.accounts = accountsList

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        return super().contractDetails(reqId, contractDetails)

    def securityDefinitionOptionParameter(self, reqId: int, exchange: str, underlyingConId: int, 
                                          tradingClass: str, multiplier: str, expirations: set, 
                                          strikes: set):
        """Receive option chain data"""
        if reqId in self.pending_option_chains:
            underlying_contract = self.pending_option_chains[reqId]['underlying_contract']
            # Convert to our OptionChain format
            expiration_dates = list(expirations)
            strike_prices = list(strikes)
            logger.info(f"Received option chain, expiration_dates: {expiration_dates}, strikes: {strike_prices}")
            logger.info(f"Received option chain, strikes: {strike_prices}")
            logger.info(f"Received option chain, exchange: {exchange}")
            logger.info(f"Received option chain, multiplier: {multiplier}")
            option_chain = OptionChain(
                underlying_symbol=underlying_contract.symbol, 
                underlying_contract=underlying_contract,
                expiration_dates=expiration_dates,
                strikes=strike_prices,
                tick_size=multiplier,
                options=[]  # Individual option contracts would be created separately
            )
            self.pending_option_chains[reqId]['result'] = option_chain

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """Option chain data complete"""
        if reqId in self.pending_option_chains:
            self.pending_option_chains[reqId]['event'].set()

    def contractDetails(self, reqId: int, contractDetails):

        """Handle contract details response"""
        if reqId in self.pending_contract_details:
            try:
                details = {
                    'symbol': contractDetails.contract.symbol,
                    'security_type': contractDetails.contract.secType,
                    'exchange': contractDetails.contract.exchange,
                    'currency': contractDetails.contract.currency,
                    'description': getattr(contractDetails, 'longName', ''),
                    'min_tick': getattr(contractDetails, 'minTick', None),
                    'order_types': getattr(contractDetails, 'orderTypes', ''),
                    'valid_exchanges': getattr(contractDetails, 'validExchanges', ''),
                    'price_magnifier': getattr(contractDetails, 'priceMagnifier', 1),
                    'under_conid': getattr(contractDetails, 'underConId', None),
                    'long_name': getattr(contractDetails, 'longName', ''),
                    'contract_month': getattr(contractDetails, 'contractMonth', ''),
                    'industry': getattr(contractDetails, 'industry', ''),
                    'category': getattr(contractDetails, 'category', ''),
                    'subcategory': getattr(contractDetails, 'subcategory', ''),
                    'time_zone_id': getattr(contractDetails, 'timeZoneId', ''),
                    'trading_hours': getattr(contractDetails, 'tradingHours', ''),
                    'liquid_hours': getattr(contractDetails, 'liquidHours', ''),
                    'ev_rule': getattr(contractDetails, 'evRule', ''),
                    'ev_multiplier': getattr(contractDetails, 'evMultiplier', None),
                    'md_size_multiplier': getattr(contractDetails, 'mdSizeMultiplier', 1),
                    'agg_group': getattr(contractDetails, 'aggGroup', None),
                    'market_rule_ids': getattr(contractDetails, 'marketRuleIds', ''),
                    'last_trade_date': getattr(contractDetails.contract, 'lastTradeDateOrContractMonth', ''),
                    'sector': getattr(contractDetails, 'sector', ''),
                    'sector_group': getattr(contractDetails, 'sectorGroup', ''),
                    'strike': getattr(contractDetails.contract, 'strike', None),
                    'right': getattr(contractDetails.contract, 'right', ''),
                    'multiplier': getattr(contractDetails.contract, 'multiplier', ''),
                    'primary_exchange': getattr(contractDetails.contract, 'primaryExchange', ''),
                    'contract_details': contractDetails  # Raw contract details object
                }
                self.pending_contract_details[reqId]['details'] = details
                self.pending_contract_details[reqId]['event'].set()
            except Exception as e:
                self.pending_contract_details[reqId]['error'] = str(e)
                self.pending_contract_details[reqId]['event'].set()

    def contractDetailsEnd(self, reqId: int):
        """Called when all contract details have been received"""
        if reqId in self.pending_contract_details:
            self.pending_contract_details[reqId]['event'].set()

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handle errors with enhanced market data error tracking"""
        # Handle contract details errors
        if reqId in self.pending_contract_details:
            self.pending_contract_details[reqId]['error'] = f"{errorCode}: {errorString}"
            self.pending_contract_details[reqId]['event'].set()
            return
            
        # Log non-harmless errors
        if errorCode not in [2104, 2106, 2158]:  # Ignore harmless messages
            logger.error(f"IB Error {errorCode}: {errorString}")
        
        # Track market data errors
        if reqId in self.broker.market_data:
            data = self.broker.market_data[reqId]
            subscription_id = data.get('subscription_id')
            
            if subscription_id:
                error = MarketDataError(
                    subscription_id=subscription_id,
                    error_code=errorCode,
                    error_message=errorString
                )
                
                # Trigger error callback
                self.broker.trigger_callback('market_data_error', error)