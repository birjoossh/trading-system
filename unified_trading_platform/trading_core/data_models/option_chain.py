from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Optional, Dict, Any
from .contract import Contract
from .option_contract import OptionContract


@dataclass
class UnderlyingInfo:
    """Information about the underlying asset for options."""

    underlying_symbol: str
    underlying_price: Optional[float] = None
    underlying_contract: Optional[Contract] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "underlying_symbol": self.underlying_symbol,
            "underlying_price": self.underlying_price,
            "underlying_contract": self.underlying_contract.to_dict() if self.underlying_contract else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UnderlyingInfo":
        """Create an UnderlyingInfo instance from a dictionary."""
        return cls(**data)


@dataclass
class StrikeGroup:
    """A group of options at the same strike price."""

    strike_price: float
    call_option: Optional[OptionContract] = None
    put_option: Optional[OptionContract] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "strike_price": self.strike_price,
            "call_option": self.call_option.to_dict() if self.call_option else None,
            "put_option": self.put_option.to_dict() if self.put_option else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StrikeGroup":
        """Create a StrikeGroup instance from a dictionary."""
        return cls(**data)


@dataclass
class ExpirationGroup:
    """A group of options expiring on the same date."""

    expiry_date: date
    days_to_expiry: int
    strikes: List[StrikeGroup] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "expiry_date": self.expiry_date.isoformat(),
            "days_to_expiry": self.days_to_expiry,
            "strikes": [strike.to_dict() for strike in self.strikes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExpirationGroup":
        """Create an ExpirationGroup instance from a dictionary."""
        return cls(**data)


@dataclass
class OptionChain:
    """Complete option chain for an underlying asset."""

    contract: Contract
    underlying_info: UnderlyingInfo
    expiration_dates: List[ExpirationGroup]
    last_updated: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "contract": self.contract.to_dict(),
            "underlying_info": self.underlying_info.to_dict(),
            "expiration_dates": [exp.to_dict() for exp in self.expiration_dates],
            "last_updated": self.last_updated.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OptionChain":
        """Create an OptionChain instance from a dictionary."""
        return cls(**data)
