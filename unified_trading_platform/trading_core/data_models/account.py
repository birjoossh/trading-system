"""
Account-related data models.

This module contains data models related to trading accounts and their summaries.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any


@dataclass
class AccountSummary:
    """Represents a summary of an account's status."""

    account_id: str
    total_cash_value: Decimal
    equity_with_loan: Decimal
    previous_equity: Decimal
    previous_equity_date: datetime
    gross_position_value: Decimal
    regt_equity: Decimal
    regt_equity_percent: Decimal
    sma: Decimal
    init_margin_req: Decimal
    maint_margin_req: Decimal
    available_funds: Decimal
    excess_liquidity: Decimal
    cushion: Decimal
    full_init_margin_req: Decimal
    full_maint_margin_req: Decimal
    full_available_funds: Decimal
    full_excess_liquidity: Decimal
    look_ahead_next_change: datetime
    look_ahead_init_margin_req: Decimal
    look_ahead_maint_margin_req: Decimal
    look_ahead_available_funds: Decimal
    look_ahead_excess_liquidity: Decimal
    currency: str = "USD"
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the account summary to a dictionary."""
        return {
            "account_id": self.account_id,
            "total_cash_value": float(self.total_cash_value),
            "equity_with_loan": float(self.equity_with_loan),
            "previous_equity": float(self.previous_equity),
            "previous_equity_date": self.previous_equity_date.isoformat(),
            "gross_position_value": float(self.gross_position_value),
            "regt_equity": float(self.regt_equity),
            "regt_equity_percent": float(self.regt_equity_percent),
            "sma": float(self.sma),
            "init_margin_req": float(self.init_margin_req),
            "maint_margin_req": float(self.maint_margin_req),
            "available_funds": float(self.available_funds),
            "excess_liquidity": float(self.excess_liquidity),
            "cushion": float(self.cushion),
            "full_init_margin_req": float(self.full_init_margin_req),
            "full_maint_margin_req": float(self.full_maint_margin_req),
            "full_available_funds": float(self.full_available_funds),
            "full_excess_liquidity": float(self.full_excess_liquidity),
            "look_ahead_next_change": self.look_ahead_next_change.isoformat() if self.look_ahead_next_change else None,
            "look_ahead_init_margin_req": float(self.look_ahead_init_margin_req),
            "look_ahead_maint_margin_req": float(self.look_ahead_maint_margin_req),
            "look_ahead_available_funds": float(self.look_ahead_available_funds),
            "look_ahead_excess_liquidity": float(self.look_ahead_excess_liquidity),
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccountSummary":
        """Create an AccountSummary instance from a dictionary."""
        return cls(
            account_id=data["account_id"],
            total_cash_value=Decimal(str(data["total_cash_value"])),
            equity_with_loan=Decimal(str(data["equity_with_loan"])),
            previous_equity=Decimal(str(data["previous_equity"])),
            previous_equity_date=datetime.fromisoformat(data["previous_equity_date"]),
            gross_position_value=Decimal(str(data["gross_position_value"])),
            regt_equity=Decimal(str(data["regt_equity"])),
            regt_equity_percent=Decimal(str(data["regt_equity_percent"])),
            sma=Decimal(str(data["sma"])),
            init_margin_req=Decimal(str(data["init_margin_req"])),
            maint_margin_req=Decimal(str(data["maint_margin_req"])),
            available_funds=Decimal(str(data["available_funds"])),
            excess_liquidity=Decimal(str(data["excess_liquidity"])),
            cushion=Decimal(str(data.get("cushion", 0))),
            full_init_margin_req=Decimal(str(data.get("full_init_margin_req", 0))),
            full_maint_margin_req=Decimal(str(data.get("full_maint_margin_req", 0))),
            full_available_funds=Decimal(str(data.get("full_available_funds", 0))),
            full_excess_liquidity=Decimal(str(data.get("full_excess_liquidity", 0))),
            look_ahead_next_change=datetime.fromisoformat(data["look_ahead_next_change"])
            if data.get("look_ahead_next_change")
            else None,
            look_ahead_init_margin_req=Decimal(str(data.get("look_ahead_init_margin_req", 0))),
            look_ahead_maint_margin_req=Decimal(str(data.get("look_ahead_maint_margin_req", 0))),
            look_ahead_available_funds=Decimal(str(data.get("look_ahead_available_funds", 0))),
            look_ahead_excess_liquidity=Decimal(str(data.get("look_ahead_excess_liquidity", 0))),
            currency=data.get("currency", "USD"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.utcnow(),
        )
