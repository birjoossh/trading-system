from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .contract import Contract
from .order import OrderAction

@dataclass
class Trade:
    """Represents an executed trade"""
    trade_id: str
    order_id: str
    contract: Contract
    execution_id: str
    quantity: int
    price: float
    timestamp: datetime
    side: OrderAction
    commission: Optional[float] = None