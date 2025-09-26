"""
Broker factory for creating broker instances.
Supports multiple brokers through a unified interface.
"""

from typing import Dict, Type
from trading_system.brokers.base_broker import BrokerInterface

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
        print("Available brokers ", cls._brokers, name)
        if name not in cls._brokers:
            available = ', '.join(cls._brokers.keys())
            raise ValueError(f"Broker '{name}' not found. Available: {available}")

        broker_class = cls._brokers[name]
        print("broker_class = ", broker_class)
        return broker_class(**kwargs)

    @classmethod
    def list_brokers(cls) -> list:
        """List available brokers"""
        return list(cls._brokers.keys())

# Register Interactive Brokers
try:
    from .interactive_brokers.ib_broker import IBBroker
    BrokerFactory.register_broker('ib', IBBroker)
    BrokerFactory.register_broker('interactive_brokers', IBBroker)
except ImportError:
    print("Interactive Brokers not available")

# TODO: Add other brokers here
# BrokerFactory.register_broker('alpaca', AlpacaBroker)
# BrokerFactory.register_broker('td_ameritrade', TDBroker)
# BrokerFactory.register_broker('binance', BinanceBroker)