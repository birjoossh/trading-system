"""
Contract data model.

This module defines the Contract class which represents a financial instrument.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

from .security_type_enum import SecurityType

@dataclass
class Contract:
    """Represents a financial instrument contract."""
    symbol: str
    exchange: str
    security_type: SecurityType
    currency: str = ""
    local_symbol: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None  # 'CALL', 'PUT', or None for non-options
    multiplier: Optional[float] = None
    trading_class: Optional[str] = None
    primary_exchange: Optional[str] = None
    include_expired: bool = False
    sec_id_type: Optional[str] = None
    sec_id: Optional[str] = None
    combo_legs: List[Dict[str, Any]] = field(default_factory=list)
    combo_legs_descrip: Optional[str] = None
    conId: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert the contract to a dictionary."""
        return {
            'symbol': self.symbol,
            'exchange': self.exchange,
            'security_type': self.security_type.value,
            'currency': self.currency,
            'local_symbol': self.local_symbol,
            'expiry': self.expiry,
            'strike': self.strike,
            'right': self.right,
            'multiplier': self.multiplier,
            'trading_class': self.trading_class,
            'primary_exchange': self.primary_exchange,
            'include_expired': self.include_expired,
            'sec_id_type': self.sec_id_type,
            'sec_id': self.sec_id,
            'combo_legs': self.combo_legs,
            'combo_legs_descrip': self.combo_legs_descrip,
            'conId': self.conId
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Contract':
        """Create a Contract instance from a dictionary."""
        return cls(**data)
