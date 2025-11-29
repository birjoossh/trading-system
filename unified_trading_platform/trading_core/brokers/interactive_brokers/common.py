from ibapi.contract import Contract as IBContract
from unified_trading_platform.trading_core.data_models import Contract
from unified_trading_platform.trading_core.data_models import MarketDataType
from unified_trading_platform.trading_core.data_models import TickType
from unified_trading_platform.trading_core.utils.utils import format_date

from unified_trading_platform.trading_core.utils.logger import get_logger
logger = get_logger(__name__)

class CommonMixin:
    def __init__(self):
        pass
    
    @staticmethod
    def create_ib_contract(contract: Contract) -> IBContract:
        ib_contract = IBContract()
        ib_contract.symbol = contract.symbol
        ib_contract.secType = contract.security_type.value
        ib_contract.exchange = contract.exchange
        ib_contract.currency = contract.currency

        if contract.local_symbol:
            ib_contract.localSymbol = contract.local_symbol
        if contract.expiry:
            logger.info(f"expiry: {contract.expiry}")
            ib_contract.lastTradeDateOrContractMonth = contract.expiry
        if contract.strike:
            ib_contract.strike = contract.strike
        if contract.option_right:
            ib_contract.right = contract.option_right.value
        if contract.multiplier:
            ib_contract.multiplier = contract.multiplier
        if contract.primary_exchange:
            ib_contract.primaryExchange = contract.primary_exchange
        if contract.include_expired:
            ib_contract.includeExpired = contract.include_expired
        return ib_contract
    
    @staticmethod
    def ib_tick_price_mapping():
        return {
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
    
    @staticmethod
    def ib_tick_size_mapping():
        return {
                # Live ticks
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
    
    @staticmethod
    def ib_market_data_type_mapping():  
        return {
            1: MarketDataType.LIVE,
            2: MarketDataType.FROZEN,
            3: MarketDataType.DELAYED,
            4: MarketDataType.DELAYED_FROZEN
        }
