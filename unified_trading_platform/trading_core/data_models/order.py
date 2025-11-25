"""
Order data models.

This module contains data models related to orders and trades.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from .contract import Contract

class OrderType(Enum):
    """Order types supported by the trading system."""
    MARKET = "MKT"
    LIMIT = "LMT"
    STOP = "STP"
    STOP_LIMIT = "STP_LMT"

class OrderAction(Enum):
    """Order actions (buy/sell)."""
    BUY = "BUY"
    SELL = "SELL"

class OrderStatus(Enum):
    """Possible statuses of an order."""
    PENDING = "Pending"
    SUBMITTED = "Submitted"
    FILLED = "Filled"
    CANCELLED = "Cancelled"
    REJECTED = "Rejected"

@dataclass
class Order:
    """Represents a trading order"""
    action: OrderAction
    quantity: int
    order_type: OrderType
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "DAY"  # DAY, GTC, IOC, FOK
    account: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Order':
        """Create an Order instance from a dictionary."""
        return cls(
            action=OrderAction(data['action']),
            quantity=data['quantity'],
            order_type=OrderType(data['order_type']),
            limit_price=data.get('limit_price'),
            stop_price=data.get('stop_price'),
            time_in_force=data.get('time_in_force', 'DAY'),
            account=data.get('account')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the order to a dictionary."""
        return {
            'action': self.action.value,
            'quantity': self.quantity,
            'order_type': self.order_type.value,
            'limit_price': self.limit_price,
            'stop_price': self.stop_price,
            'time_in_force': self.time_in_force,
            'account': self.account
        }

@dataclass
class ManagedOrder:
    """Enhanced order with additional tracking information"""
    order_id: str
    broker_order_id: Optional[str]
    contract: 'Contract'
    order: 'Order'
    broker_name: str
    status: 'OrderStatus'
    created_at: datetime
    updated_at: datetime = field(default_factory=datetime.now)
    filled_quantity: int = 0
    remaining_quantity: int = 0
    avg_fill_price: Optional[float] = None
    parent_id: Optional[str] = None
    client_id: Optional[str] = None
    tags: Dict[str, Any] = field(default_factory=dict)
    notes: Optional[str] = None
    commission: Optional[float] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ManagedOrder':
        """Create a ManagedOrder instance from a dictionary."""
        return cls(
            order_id=data['order_id'],
            broker_order_id=data.get('broker_order_id'),
            contract=Contract.from_dict(data['contract']),
            order=Order.from_dict(data['order']),
            broker_name=data['broker_name'],
            status=OrderStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            filled_quantity=data.get('filled_quantity', 0),
            remaining_quantity=data.get('remaining_quantity', 0),
            avg_fill_price=data.get('avg_fill_price')
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the managed order to a dictionary."""
        return {
            'order_id': self.order_id,
            'broker_order_id': self.broker_order_id,
            'contract': self.contract.to_dict(),
            'order': self.order.to_dict(),
            'broker_name': self.broker_name,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'filled_quantity': self.filled_quantity,
            'remaining_quantity': self.remaining_quantity,
            'avg_fill_price': self.avg_fill_price
        }