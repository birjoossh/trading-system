"""
Option-related data models.

This module contains data models specific to options trading.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any

from .option_right_enum import OptionRight

@dataclass
class OptionContract:
    """Represents an option contract with pricing and greeks."""
    option_ticker: str
    ltp: float  # Last traded price
    option_right: OptionRight
    lot: int = 1
    last_updated: Optional[datetime] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    volume: Optional[float] = None
    open_interest: Optional[float] = None
    implied_volatility: Optional[float] = None
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    
    @classmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'option_ticker': self.option_ticker,
            'ltp': self.ltp,
            'option_right': self.option_right.value,
            'lot': self.lot,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'bid': self.bid,
            'ask': self.ask,
            'volume': self.volume,
            'open_interest': self.open_interest,
            'implied_volatility': self.implied_volatility,
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega,
            'rho': self.rho
        }
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OptionContract':
        """Create an OptionContract instance from a dictionary."""
        return cls(**data)


