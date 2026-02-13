from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from .contract import Contract
from .market_datatype_enum import MarketDataType


@dataclass
class MarketDataSubscription:
    """Represents a market data subscription"""

    contract: Contract
    subscription_id: str
    market_data_type: MarketDataType = MarketDataType.DELAYED
    snapshot: bool = False
    regulatory_snapshot: bool = False
    generic_tick_list: Optional[List[str]] = None
    callback: Optional[Callable] = None
    is_active: bool = False
    created_at: datetime = field(default_factory=datetime.now)
    last_update: Optional[datetime] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketDataSubscription":
        """Create a MarketDataSubscription instance from a dictionary."""
        return cls(**data)

    @classmethod
    def to_dict(self) -> Dict[str, Any]:
        """Convert the MarketDataSubscription to a dictionary."""
        return {
            "contract": self.contract,
            "subscription_id": self.subscription_id,
            "market_data_type": self.market_data_type,
            "snapshot": self.snapshot,
            "regulatory_snapshot": self.regulatory_snapshot,
            "generic_tick_list": self.generic_tick_list,
            "callback": self.callback,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }
