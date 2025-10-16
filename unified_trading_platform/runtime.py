from unified_trading_platform.trading_core import TradingSystem

_singleton_ts: TradingSystem | None = None

def get_trading_system() -> TradingSystem:
    global _singleton_ts
    if _singleton_ts is None:
        _singleton_ts = TradingSystem()
    return _singleton_ts


