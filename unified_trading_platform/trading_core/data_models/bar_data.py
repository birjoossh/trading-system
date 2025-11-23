from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any

@dataclass
class BarData:
    """Represents OHLC bar data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BarData':
        """Create a BarData instance from a dictionary."""
        return cls(**data)
    
    @classmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert the BarData to a dictionary."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }