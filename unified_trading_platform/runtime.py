"""
Runtime module to manage singleton TradingSystem instance.
Provides global access to the trading system for API endpoints.
"""

from typing import Optional
from unified_trading_platform.trading_core.main import TradingSystem

_trading_system: Optional[TradingSystem] = None


def get_trading_system(db_path: str = "trading_system2.db") -> TradingSystem:
    """
    Get or create the global TradingSystem instance.

    Args:
        db_path: Path to the database file

    Returns:
        TradingSystem instance
    """
    global _trading_system

    if _trading_system is None:
        _trading_system = TradingSystem(db_path)

    return _trading_system


def reset_trading_system():
    """Reset the global TradingSystem instance (mainly for testing)"""
    global _trading_system

    if _trading_system is not None:
        _trading_system.shutdown()
        _trading_system = None
