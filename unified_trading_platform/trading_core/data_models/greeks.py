from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class Greeks:
    """Options Greeks data"""
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    underlying_price: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Greeks':
        """Create a Greeks instance from a dictionary."""
        return cls(**data)
    
    @classmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert the Greeks to a dictionary."""
        return {
            'delta': self.delta,
            'gamma': self.gamma,
            'theta': self.theta,
            'vega': self.vega,
            'rho': self.rho,
            'implied_volatility': self.implied_volatility,
            'underlying_price': self.underlying_price,
            'timestamp': self.timestamp.isoformat()
        }