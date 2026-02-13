from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any


@dataclass
class MarketDataError:
    """Represents market data subscription errors"""

    subscription_id: str
    error_code: int
    error_message: str
    timestamp: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketDataError":
        """Create a MarketDataError instance from a dictionary."""
        return cls(**data)

    @classmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert the MarketDataError to a dictionary."""
        return {
            "subscription_id": self.subscription_id,
            "error_code": self.error_code,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat(),
        }
