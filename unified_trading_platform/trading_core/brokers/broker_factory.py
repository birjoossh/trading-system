"""
Broker factory for creating broker instances.
Supports multiple brokers through a unified interface.
"""

from typing import Dict, Type
from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)


class BrokerFactory:
    """Factory for creating broker instances"""

    _brokers: Dict[str, Type[BrokerInterface]] = {}

    @classmethod
    def register_broker(cls, name: str, broker_class: Type[BrokerInterface]):
        """Register a broker implementation"""
        cls._brokers[name] = broker_class

    @classmethod
    def create_broker(cls, name: str, **kwargs) -> BrokerInterface:
        """Create a broker instance"""
        logger.debug(f"Available brokers: {list(cls._brokers)}, requested: {name}")
        if name not in cls._brokers:
            available = ", ".join(cls._brokers.keys())
            error_msg = f"Broker '{name}' not found. Available: {available}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        broker_class = cls._brokers[name]
        logger.debug(f"Creating broker instance of type: {broker_class.__name__}")
        return broker_class(**kwargs)

    @classmethod
    def list_brokers(cls) -> list:
        """List available brokers"""
        return list(cls._brokers.keys())


# Register Interactive Brokers
# try:
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker

logger.info("Registering Interactive Brokers ...")
BrokerFactory.register_broker("ib", IBBroker)
BrokerFactory.register_broker("interactive_brokers", IBBroker)
# except ImportError:
#     logger.warning("Interactive Brokers not available")

# TODO: Add other brokers here
# BrokerFactory.register_broker('alpaca', AlpacaBroker)
# BrokerFactory.register_broker('td_ameritrade', TDBroker)
# BrokerFactory.register_broker('binance', BinanceBroker)

# Register Paper broker
try:
    from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

    logger.info("Registering Paper broker ...")
    BrokerFactory.register_broker("paper", PaperBroker)
except ImportError:
    logger.warning("Paper broker not available")
