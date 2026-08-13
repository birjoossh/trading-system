from unified_trading_platform.trading_core.utils.logger import get_logger
from datetime import datetime

try:
    from ibapi.client import EClient
    from ibapi.common import BarData, OrderId
    from ibapi.wrapper import EWrapper

    IB_AVAILABLE = True
except ImportError:
    IB_AVAILABLE = False
from unified_trading_platform.trading_core.data_models import MarketDataError
from unified_trading_platform.trading_core.data_models import Contract
from unified_trading_platform.trading_core.data_models import TickData
from unified_trading_platform.trading_core.data_models import OrderAction, OrderStatus, Trade

from unified_trading_platform.trading_core.brokers.interactive_brokers.common import CommonMixin
from concurrent.futures import Future

logger = get_logger(__name__)


class IBClient(EWrapper, EClient):
    """IB API client wrapper"""

    def __init__(self, broker):
        EClient.__init__(self, self)
        self.broker = broker
        from .ib_request_manager import IBRequestManager
        self.request_manager = IBRequestManager()
        self._accumulators = {}

    def get_contract_details_async(self, ib_contract) -> "Future":
        """Request contract details asynchronously"""
        req_id, future = self.request_manager.create_request()
        try:
            self.reqContractDetails(req_id, ib_contract)
        except Exception as e:
            self.request_manager.set_error(req_id, e)
        return future

    
    def get_option_chain_params_async(self, exchange: str, underlying_con_id: int, trading_class: str) -> "Future":
        """Request option chain params asynchronously"""
        req_id, future = self.request_manager.create_request()
        try:
            self.reqSecDefOptParams(req_id, underlying_con_id, "", exchange, trading_class)
        except Exception as e:
            self.request_manager.set_error(req_id, e)
        return future

    def get_historical_data_async(self, ib_contract, duration: str, bar_size: str, what_to_show: str) -> "Future":
        """Request historical data asynchronously"""
        req_id, future = self.request_manager.create_request()
        # Initialize accumulator
        self._accumulators[req_id] = []
        try:
            self.reqHistoricalData(req_id, ib_contract, "", duration, bar_size, what_to_show, 1, 1, False, [])
        except Exception as e:
            self.request_manager.set_error(req_id, e)
            del self._accumulators[req_id]
        return future

    def nextValidId(self, orderId: int):
        """Receive next valid order ID — signals the connection is ready."""
        self.broker.next_order_id = orderId
        try:
            self.broker._connected_event.set()
        except Exception:
            pass

    def historicalData(self, reqId: int, bar: BarData):
        """Receive historical data"""
        # New pattern: accumulate for RequestManager
        if reqId in self._accumulators:
            self._accumulators[reqId].append(bar)

    def historicalDataEnd(self, reqId: int, start: str, end: str):
        """Historical data complete"""
        if reqId in self._accumulators:
            result = self._accumulators.pop(reqId, [])
            self.request_manager.set_result(reqId, result)

    def tickPrice(self, reqId: int, tickType: int, value: float, attrib):
        """Receive tick price data with enhanced options support"""
        logger.info(f"Received tick price data for reqId: {reqId}, tickType: {tickType}, value: {value}")
        if reqId in self.broker.market_data_subscriptions:
            sub = self.broker.market_data_subscriptions[reqId]
            contract: Contract = sub["contract"]

            if "tick_data" not in sub:
                # Initialize TickData with basic contract info
                sub["tick_data"] = TickData(
                    timestamp=datetime.utcnow(),
                    exchange=contract.exchange,
                    security_type=contract.security_type,
                    currency=contract.currency,
                    symbol=contract.symbol,
                    bid=0.0,
                    ask=0.0,
                    last=0.0,
                    volume=0,
                    open_interest=0,
                )
            # Enhanced tick type mapping for options and stocks
            tick_mapping = CommonMixin.ib_tick_price_mapping()
            if tickType in tick_mapping:
                field_name, _ = tick_mapping[tickType]
                if hasattr(sub["tick_data"], field_name):
                    setattr(sub["tick_data"], field_name, value)
                    sub["tick_data"].timestamp = datetime.utcnow()
            if "callback" in sub:
                sub["callback"](sub["tick_data"])

    def tickSize(self, reqId: int, tickType: int, value: int):
        """Receive tick size data with enhanced support"""
        if reqId in self.broker.market_data_subscriptions:
            sub = self.broker.market_data_subscriptions[reqId]
            contract: Contract = sub["contract"]
            if "tick_data" not in sub:
                # Initialize TickData with basic contract info
                sub["tick_data"] = TickData(
                    timestamp=datetime.utcnow(),
                    exchange=contract.exchange,
                    security_type=contract.security_type,
                    currency=contract.currency,
                    symbol=contract.symbol,
                    bid=0.0,
                    ask=0.0,
                    last=0.0,
                    volume=0,
                    open_interest=0,
                )

            # Enhanced size tick mapping
            size_mapping = CommonMixin.ib_tick_size_mapping()
            if tickType in size_mapping:
                field_name, _ = size_mapping[tickType]
                if hasattr(sub["tick_data"], field_name):
                    setattr(sub["tick_data"], field_name, value)
                    sub["tick_data"].timestamp = datetime.utcnow()
            if "callback" in sub:
                sub["callback"](sub["tick_data"])

    def tickOptionComputation(
        self,
        reqId: int,
        tickType: int,
        tickAttrib: int,
        impliedVol: float,
        delta: float,
        optPrice: float,
        pvDividend: float,
        gamma: float,
        vega: float,
        theta: float,
        undPrice: float,
    ):
        """Receive option computation data (Greeks)"""
        if reqId in self.broker.market_data_subscriptions:
            sub = self.broker.market_data_subscriptions[reqId]
            contract: Contract = sub["contract"]
            
            if "tick_data" not in sub:
                sub["tick_data"] = TickData(
                    timestamp=datetime.utcnow(),
                    exchange=contract.exchange,
                    security_type=contract.security_type,
                    currency=contract.currency,
                    symbol=contract.symbol,
                    bid=0.0,
                    ask=0.0,
                    last=0.0,
                    volume=0,
                    open_interest=0,
                )
            
            tick_data = sub["tick_data"]
            
            # IB uses specific values to indicate "not computed" or error (e.g. -1, -2)
            # We filter those out. Valid values are usually non-negative for price/vol, but delta can be negative.
            # A common check is checking against 1.7976931348623157E308 (Double.MAX_VALUE) but logic varies.
            # Here we assume simpler checks or valid values if not None/Infinite.
            # Actually IBAPI passes floats.
            
            def is_valid(val):
                return val is not None and val != 1.7976931348623157E308 and val > -1e10 # Arbitrary simple validation
                
            if is_valid(impliedVol):
                tick_data.implied_volatility = impliedVol
            if is_valid(delta):
                tick_data.delta = delta
            if is_valid(optPrice):
                tick_data.option_price = optPrice
            if is_valid(gamma):
                tick_data.gamma = gamma
            if is_valid(vega):
                tick_data.vega = vega
            if is_valid(theta):
                tick_data.theta = theta
            
            tick_data.timestamp = datetime.utcnow()
            
            if "callback" in sub:
                sub["callback"](tick_data)

    def orderStatus(
        self,
        orderId: OrderId,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float,
    ):
        """Receive order status updates"""
        order_id = str(orderId)
        if order_id in self.broker.orders:
            # Map IB status strings to our OrderStatus enum
            status_mapping = {
                "PendingSubmit": OrderStatus.PENDING,
                "PendingCancel": OrderStatus.PENDING,
                "PreSubmitted": OrderStatus.PENDING,
                "Submitted": OrderStatus.SUBMITTED,
                "ApiPending": OrderStatus.PENDING,
                "ApiCancelled": OrderStatus.CANCELLED,
                "Cancelled": OrderStatus.CANCELLED,
                "Filled": OrderStatus.FILLED,
                "PartiallyFilled": OrderStatus.SUBMITTED,
                "Rejected": OrderStatus.REJECTED,
                "Inactive": OrderStatus.REJECTED,

            }
            # Convert IB status to our enum, default to PENDING if unknown
            mapped_status = status_mapping.get(status, OrderStatus.PENDING)
            self.broker.orders[order_id].update(
                {"status": mapped_status, "filled": filled, "remaining": remaining, "avg_fill_price": avgFillPrice}
            )
            # Trigger callback
            self.broker.trigger_callback("order_status", order_id, self.broker.orders[order_id])

    def openOrder(self, orderId: OrderId, contract, order, orderState):
        """Receive open order info"""
        pass

    def execDetails(self, reqId: int, contract, execution):
        """Receive execution details"""
        side_map = {"BOT": OrderAction.BUY, "SLD": OrderAction.SELL}
        trade = Trade(
            order_id=str(execution.orderId),
            contract=Contract(
                symbol=contract.symbol,
                security_type=contract.secType,
                exchange=contract.exchange,
                currency=contract.currency,
            ),
            execution_id=execution.execId,
            quantity=execution.shares,
            price=execution.price,
            timestamp=datetime.strptime(execution.time, "%Y%m%d %H:%M:%S"),
            side=OrderAction(side_map[execution.side]),
        )

        # Trigger callback
        self.broker.trigger_callback("trade_execution", trade)

    def position(self, account: str, contract, position: float, avgCost: float):
        """Receive position updates"""
        position_data = {
            "account": account,
            "symbol": contract.symbol,
            "security_type": contract.secType,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "position": position,
            "avg_cost": avgCost,
        }

        # Update positions list
        existing = False
        for i, pos in enumerate(self.broker.positions):
            if pos["symbol"] == contract.symbol and pos["account"] == account:
                self.broker.positions[i] = position_data
                existing = True
                break

        if not existing:
            self.broker.positions.append(position_data)

    def updateAccountValue(self, key: str, val: str, currency: str, accountName: str):
        """Receive account value updates"""
        self.broker.account_info[key] = {"value": val, "currency": currency, "account": accountName}

    def managedAccounts(self, accountsList: str):
        self.accounts = accountsList


    def securityDefinitionOptionParameter(
        self,
        reqId: int,
        exchange: str,
        underlyingConId: int,
        tradingClass: str,
        multiplier: str,
        expirations: set,
        strikes: set,
    ):
        """Receive option chain parameter data and buffer for the broker to process."""
        try:
            logger.info(
                "Received option params (exchange=%s, tradingClass=%s, expirations=%d, strikes=%d)",
                exchange,
                tradingClass,
                len(expirations),
                len(strikes),
            )

            if reqId not in self._accumulators:
                self._accumulators[reqId] = []

            self._accumulators[reqId].append(
                {
                    "exchange": exchange,
                    "underlyingConId": underlyingConId,
                    "tradingClass": tradingClass,
                    "multiplier": multiplier,
                    "expirations": list(expirations),
                    "strikes": list(strikes),
                }
            )
        except Exception as exc:
            self.request_manager.set_error(reqId, str(exc))


    def securityDefinitionOptionParameterEnd(self, reqId: int):
        """Option chain data complete"""
        logger.info("Received option chain data complete (reqId=%d)", reqId)
        result = self._accumulators.pop(reqId, [])
        self.request_manager.set_result(reqId, result)

    def contractDetails(self, reqId: int, contractDetails):
        """Handle contract details response"""
        try:
            details = {
                "symbol": contractDetails.contract.symbol,
                "security_type": contractDetails.contract.secType,
                "exchange": contractDetails.contract.exchange,
                "currency": contractDetails.contract.currency,
                "description": getattr(contractDetails, "longName", ""),
                "min_tick": getattr(contractDetails, "minTick", None),
                "order_types": getattr(contractDetails, "orderTypes", ""),
                "valid_exchanges": getattr(contractDetails, "validExchanges", ""),
                "price_magnifier": getattr(contractDetails, "priceMagnifier", 1),
                "under_conid": getattr(contractDetails, "underConId", None),
                "long_name": getattr(contractDetails, "longName", ""),
                "contract_month": getattr(contractDetails, "contractMonth", ""),
                "industry": getattr(contractDetails, "industry", ""),
                "category": getattr(contractDetails, "category", ""),
                "subcategory": getattr(contractDetails, "subcategory", ""),
                "time_zone_id": getattr(contractDetails, "timeZoneId", ""),
                "trading_hours": getattr(contractDetails, "tradingHours", ""),
                "liquid_hours": getattr(contractDetails, "liquidHours", ""),
                "ev_rule": getattr(contractDetails, "evRule", ""),
                "ev_multiplier": getattr(contractDetails, "evMultiplier", None),
                "md_size_multiplier": getattr(contractDetails, "mdSizeMultiplier", 1),
                "agg_group": getattr(contractDetails, "aggGroup", None),
                "market_rule_ids": getattr(contractDetails, "marketRuleIds", ""),
                "last_trade_date": getattr(contractDetails.contract, "lastTradeDateOrContractMonth", ""),
                "sector": getattr(contractDetails, "sector", ""),
                "sector_group": getattr(contractDetails, "sectorGroup", ""),
                "strike": getattr(contractDetails.contract, "strike", None),
                "right": getattr(contractDetails.contract, "right", ""),
                "multiplier": getattr(contractDetails.contract, "multiplier", ""),
                "primary_exchange": getattr(contractDetails.contract, "primaryExchange", ""),
                "contract_details": contractDetails,  # Raw contract details object
            }
            if reqId not in self._accumulators:
                self._accumulators[reqId] = []
            self._accumulators[reqId].append(details)
        except Exception as e:
            self.request_manager.set_error(reqId, str(e))

    def contractDetailsEnd(self, reqId: int):
        """Called when all contract details have been received"""
        result = self._accumulators.pop(reqId, [])
        # Return the last item if expecting single result? Or list?
        # Standardize: contractDetails returns a LIST of details
        self.request_manager.set_result(reqId, result)

    def error(self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str = ""):
        """Handle errors with enhanced market data error tracking"""
        # Handle request errors via RequestManager
        if reqId != -1:
            self.request_manager.set_error(reqId, f"{errorCode}: {errorString}")

        # Log non-harmless errors
        if errorCode not in [2104, 2106, 2158]:  # Ignore harmless messages
            logger.error(f"IB Error {errorCode}: {errorString}, req_id: {reqId}")

        # Track market data errors
        if reqId in self.broker.market_data_subscriptions:
            data = self.broker.market_data_subscriptions[reqId]
            subscription_id = data.get("subscription_id")

            if subscription_id:
                error = MarketDataError(
                    subscription_id=subscription_id, error_code=errorCode, error_message=errorString
                )

                # Trigger error callback
                self.broker.trigger_callback("market_data_error", error)
