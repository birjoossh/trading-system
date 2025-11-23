"""
Position data model.

This module defines the Position class which represents a trading position.
"""
from dataclasses import dataclass
from typing import Optional

from .contract import Contract


@dataclass
class Position:
    """Represents a trading position in the market."""
    contract: Contract
    position: float  # Positive for long, negative for short
    average_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    account: Optional[str] = None
    exchange: Optional[str] = None
    multiplier: float = 1.0
    cost_basis: Optional[float] = None
    prev_close_price: Optional[float] = None
    prev_avg_cost: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert the position to a dictionary."""
        return {
            'contract': self.contract.to_dict(),
            'position': self.position,
            'average_cost': self.average_cost,
            'market_price': self.market_price,
            'market_value': self.market_value,
            'unrealized_pnl': self.unrealized_pnl,
            'realized_pnl': self.realized_pnl,
            'account': self.account,
            'exchange': self.exchange,
            'multiplier': self.multiplier,
            'cost_basis': self.cost_basis,
            'prev_close_price': self.prev_close_price,
            'prev_avg_cost': self.prev_avg_cost
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        """Create a Position instance from a dictionary."""
        return cls(
            contract=Contract.from_dict(data['contract']),
            position=data['position'],
            average_cost=data['average_cost'],
            market_price=data['market_price'],
            market_value=data['market_value'],
            unrealized_pnl=data['unrealized_pnl'],
            realized_pnl=data['realized_pnl'],
            account=data.get('account'),
            exchange=data.get('exchange'),
            multiplier=data.get('multiplier', 1.0),
            cost_basis=data.get('cost_basis'),
            prev_close_price=data.get('prev_close_price'),
            prev_avg_cost=data.get('prev_avg_cost')
        )
