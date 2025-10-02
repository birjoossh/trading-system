"""
Interactive Brokers broker implementation.
Implements the BrokerInterface for IB TWS/Gateway API.
"""

import threading
import time
from typing import List, Dict, Any, Callable
from datetime import datetime

try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract as IBContract
    from ibapi.order import Order as IBOrder
    from ibapi.common import OrderId
    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
    print("IB API not available. Install with: pip install ibapi")

from ..base_broker import (
    BrokerInterface, Contract, Order, Trade, BarData, TickData,
    OrderType, OrderAction, OrderStatus
)

class IBBroker(BrokerInterface):
    """Interactive Brokers implementation"""

    def __init__(self, host="127.0.0.1", port=7498, client_id=1):
        print("Initializing...")
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
        self.orders = {}
        self.positions = []
        self.account_info = {}
        self._api_thread = None
        self._connected_event = threading.Event()
        self._lock = threading.RLock()
        print("done initialization....")

    def connect(self, host: str = "127.0.0.1", port: int = 7498, client_id: int = 1) -> bool:
        """Connect to IB TWS/Gateway"""
        print("here at ib_broker ...")
        self.host = host
        self.port = port
        self.client_id = client_id

        if self.is_connected:
            return True
        
        self._connected_event.clear()
        try:
            self.client.connect(host, port, client_id)
            print("connection done")
            # Start API thread
            self._api_thread = threading.Thread(target=self.client.run, daemon=True)
            self._api_thread.start()
            if not self._connected_event.wait(timeout=10):
                try:
                    self.client.disconnect()
                except Exception as e:
                   pass
                return False
            self.is_connected = True
            print(f"Connected to IB at {host}:{port} with client ID {client_id}")

            # nextValidId will signal _connected_event; we've already waited above
            return True

        except Exception as e:
            print(f"Connection error: {e}")
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
            print("Disconnected from IB")
            return True
        except Exception as e:
            print(f"Disconnect error: {e}")
            return False

    def _create_ib_contract(self, contract: Contract) -> IBContract:
        """Convert our Contract to IB Contract"""
        ib_contract = IBContract()
        ib_contract.symbol = contract.symbol
        ib_contract.secType = contract.security_type
        ib_contract.exchange = contract.exchange
        ib_contract.currency = contract.currency

        if contract.local_symbol:
            ib_contract.localSymbol = contract.local_symbol
        if contract.expiry:
            ib_contract.lastTradeDateOrContractMonth = contract.expiry
        if contract.strike:
            ib_contract.strike = contract.strike
        if contract.right:
            ib_contract.right = contract.right
        if contract.multiplier:
            ib_contract.multiplier = contract.multiplier

        return ib_contract

    def _create_ib_order(self, order: Order) -> IBOrder:
        """Convert our Order to IB Order"""
        if order.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) and (order.limit_price is None or order.limit_price <= 0):
            raise ValueError("limit_price must be positive for LIMIT/STOP_LIMIT orders")
        if order.order_type in (OrderType.STOP, OrderType.STOP_LIMIT) and (order.stop_price is None or order.stop_price <= 0):
            raise ValueError("stop_price must be positive for STOP/STOP_LIMIT orders")
        ib_order = IBOrder()
        ib_order.action = order.action.value
        ib_order.totalQuantity = order.quantity
        ib_order.orderType = order.order_type.value

        ib_order.eTradeOnly = False
        ib_order.firmQuoteOnly = False

        if order.limit_price:
            ib_order.lmtPrice = order.limit_price
        if order.stop_price:
            ib_order.auxPrice = order.stop_price
        if order.time_in_force:
            ib_order.tif = order.time_in_force
        if order.account:
            ib_order.account = order.account
        ib_order.eTradeOnly = False
        return ib_order

    def get_historical_data(self, contract: Contract, duration: str,
                          bar_size: str, what_to_show: str = "TRADES") -> List[BarData]:
        """Get historical bar data"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        req_id = len(self.historical_data) + 1000
        self.historical_data[req_id] = []

        ib_contract = self._create_ib_contract(contract)

        # Request historical data
        self.client.reqHistoricalData(
            req_id, ib_contract, "", duration, bar_size, what_to_show, 1, 1, False, []
        )

        # Wait for data
        timeout = 30
        start_time = time.time()
        while len(self.historical_data[req_id]) == 0 and (time.time() - start_time) < timeout:
            time.sleep(1) # sleep 1 sec

        # Convert to our BarData format
        bars = []
        for bar in self.historical_data[req_id]:
            bar_data = BarData(
                timestamp=datetime.strptime(bar.date, "%Y%m%d %H:%M:%S"),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume
            )
            bars.append(bar_data)

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

        # Submit order
        self.client.placeOrder(int(order_id), ib_contract, ib_order)

        return order_id

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        try:
            self.client.cancelOrder(int(order_id))
            return True
        except Exception as e:
            print(f"Error cancelling order {order_id}: {e}")
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

    def subscribe_market_data(self, contract: Contract, callback: Callable) -> bool:
        """Subscribe to market data"""
        if not self.is_connected:
            raise Exception("Not connected to broker")

        req_id = len(self.market_data) + 2000
        self.market_data[req_id] = {
            'contract': contract,
            'callback': callback,
            'data': {}
        }

        ib_contract = self._create_ib_contract(contract)
        try:
            self.client.reqMarketDataType(3) # 1=live, 2=frozen, 3=delayed, 4=delayed-frozen # realtime is not free
        except Exception as e:
            print(f"Error setting market data type: {e}")
            return False
        snapshot = False
        regulatorySnapshot = False # not free
        self.client.reqMktData(req_id, ib_contract, "", snapshot, regulatorySnapshot, [])
        return True

    def unsubscribe_market_data(self, contract: Contract) -> bool:
        """Unsubscribe from market data"""
        # Find and cancel subscription
        for req_id, data in self.market_data.items():
            if data['contract'].symbol == contract.symbol:
                self.client.cancelMktData(req_id)
                del self.market_data[req_id]
                return True
        return False


class IBClient(EWrapper, EClient):
    """IB API client wrapper"""

    def __init__(self, broker):
        EClient.__init__(self, self)
        self.broker = broker

    def nextValidId(self, orderId: OrderId):
        """Receive next valid order ID"""
        self.broker.next_order_id = orderId
        try:
            self.broker._connected_event.set()
        except Exception:
            pass

    def historicalData(self, reqId: int, bar):
        """Receive historical data"""
        if reqId in self.broker.historical_data:
            self.broker.historical_data[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Historical data complete"""
        pass

    def tickPrice(self, reqId: int, tickType: int, price: float, attrib):
        """Receive tick price data"""
        if reqId in self.broker.market_data:
            data = self.broker.market_data[reqId]

            # Map tick types to our format
            ## live ticks
            if tickType == 1:  # Bid
                data['data']['bid'] = price
            elif tickType == 2:  # Ask
                data['data']['ask'] = price
            elif tickType == 4:  # Last
                data['data']['last'] = price
            ## delayed ticks
            if tickType == 66:  # Delayed Bid
                data['data']['bid'] = price
            elif tickType == 67:  # Delayed Ask
                data['data']['ask'] = price
            elif tickType == 68:  # Delayed Last
                data['data']['last'] = price

            bid = data['data'].get('bid')
            ask = data['data'].get('ask')
            last = data['data'].get('last')

            if (bid is not None) or (ask is not None) or (last is not None):
                # Create tick data and call callback
                tick_data = TickData(
                    timestamp=datetime.now(),
                    exchange=data['contract'].exchange,
                    security_type=data['contract'].security_type,
                    currency=data['contract'].currency,
                    symbol=data['contract'].symbol,
                    bid=bid,
                    ask=ask,
                    last=last
                )

                if data['callback']:
                    data['callback'](tick_data)

    def tickSize(self, reqId: int, tickType: int, size: int):
        """Receive tick size data"""
        if reqId in self.broker.market_data :
            data = self.broker.market_data[reqId]
            if tickType == 8 or tickType == 74: # Volume (8 = live last size updates, 74 = delayed volume)
                data['data']['volume'] = size

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

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handle errors"""
        if errorCode not in [2104, 2106, 2158]:  # Ignore harmless messages
            print(f"IB Error {errorCode}: {errorString}")