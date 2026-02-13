"""
Market data models.

This module contains data models for market data such as ticks and bars.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from .security_type_enum import SecurityType
from .tick_type_enum import TickType
from .market_datatype_enum import MarketDataType


@dataclass
class TickData:
    """Enhanced real-time tick data with comprehensive market data support"""

    timestamp: datetime
    exchange: str
    security_type: SecurityType
    symbol: str
    currency: str
    # Basic price data
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    open: Optional[float] = None
    close: Optional[float] = None
    # Size data
    bid_size: Optional[int] = None
    ask_size: Optional[int] = None
    last_size: Optional[int] = None
    volume: Optional[int] = None
    # Options-specific data
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    option_price: Optional[float] = None
    # Additional market data
    open_interest: Optional[int] = None
    model_option: Optional[bool] = None  # Whether price is model-derived
    # Metadata
    tick_type: Optional[TickType] = None
    market_data_type: Optional[MarketDataType] = None
    raw_data: Optional[Dict[str, Any]] = None  # Store raw broker data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TickData":
        """Create a TickData instance from a dictionary."""
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the TickData to a dictionary."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "exchange": self.exchange,
            "security_type": self.security_type,
            "symbol": self.symbol,
            "currency": self.currency,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "high": self.high,
            "low": self.low,
            "open": self.open,
            "close": self.close,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_size": self.last_size,
            "volume": self.volume,
            "delta": self.delta,
            "gamma": self.gamma,
            "theta": self.theta,
            "vega": self.vega,
            "rho": self.rho,
            "implied_volatility": self.implied_volatility,
            "option_price": self.option_price,
            "open_interest": self.open_interest,
            "model_option": self.model_option,
            "tick_type": self.tick_type,
            "market_data_type": self.market_data_type,
            "raw_data": self.raw_data,
        }
