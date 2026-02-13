"""
Contract-related models.
Handles contract specifications for trading instruments.
"""

from typing import Optional
from pydantic import BaseModel, Field
from unified_trading_platform.api.config import get_config_value


class ContractRequest(BaseModel):
    """Contract specification for requests"""

    symbol: str
    exchange: str = Field(default_factory=lambda: get_config_value("contract.default_exchange", ""))
    security_type: str = Field(
        default_factory=lambda: get_config_value("contract.default_security_type", "STK"),
        description="STK, OPT, FUT, etc.",
    )
    currency: str = Field(
        default_factory=lambda: get_config_value("contract.default_currency", "USD"),
        description="Currency code",
    )
    expiry: Optional[str] = Field(default=None, description="Expiry date for options/futures (YYYYMMDD)")
    strike: Optional[float] = Field(default=None, description="Strike price for options")
    right: Optional[str] = Field(default=None, description="PUT or CALL for options")
    multiplier: Optional[str] = Field(default=None, description="Contract multiplier")


class ContractInfo(BaseModel):
    """Contract information response"""

    symbol: str
    exchange: str
    security_type: str
    currency: str
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[str] = None
    multiplier: Optional[str] = None
    con_id: Optional[int] = Field(default=None, alias="conId")
