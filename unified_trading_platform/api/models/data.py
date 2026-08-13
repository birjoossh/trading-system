"""
Market data-related models.
Handles historical data, option chains, and market data subscriptions.
"""

from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel, Field, ConfigDict
from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.data_models import (
    OptionChain,
    SecurityType,
    OptionRight,
    Contract as DomainContract,
)


class HistoricalDataRequest(BaseModel):
    """Request for historical data"""

    @staticmethod
    def _get_example():
        """Get example values from config"""
        return {
            "symbol": "SPY",
            "exchange": "SMART",
            "duration": settings.get("defaults.data.duration", "1 D"),
            "bar_size": settings.get("defaults.data.bar_size", "1 hour"),
            "security_type": settings.get("defaults.contract.security_type", "STK"),
            "currency": settings.get("defaults.contract.currency", "USD"),
            "broker_name": None,
        }

    model_config = ConfigDict(json_schema_extra={"example": _get_example()})

    symbol: str = Field(..., description="Trading symbol", examples=["SPY", "AAPL"])
    exchange: str = Field(..., description="Exchange identifier", examples=["SMART", "NYSE"])
    duration: str = Field(
        default_factory=lambda: settings.get("defaults.data.duration", "1 D"),
        description="Duration string (e.g., '1 D', '1 M', '1 Y')",
        examples=["1 D", "1 M", "1 Y", "1 W"],
    )
    bar_size: str = Field(
        default_factory=lambda: settings.get("defaults.data.bar_size", "1 hour"),
        description="Bar size (e.g., '1 min', '5 min', '1 hour', '1 day')",
        examples=["1 min", "5 min", "1 hour", "1 day"],
    )
    security_type: str = Field(
        default_factory=lambda: settings.get("defaults.contract.security_type", "STK"),
        description="Security type",
        examples=["STK", "OPT", "FUT"],
    )
    currency: str = Field(
        default_factory=lambda: settings.get("defaults.contract.currency", "USD"),
        description="Currency code",
        examples=["USD", "INR"],
    )
    broker_name: Optional[str] = Field(
        default=None,
        description="Broker to use (defaults to first available)",
        examples=[None, "ib_paper"],
    )


class BarData(BaseModel):
    """Historical bar data"""

    model_config = ConfigDict(
        json_encoders={datetime: lambda v: v.isoformat()},
        json_schema_extra={
            "example": {
                "timestamp": "2024-01-01T10:00:00",
                "open": 450.50,
                "high": 451.20,
                "low": 450.10,
                "close": 450.90,
                "volume": 1000000,
            }
        },
    )
    timestamp: datetime = Field(..., description="Bar timestamp")
    open: float = Field(..., description="Opening price", gt=0)
    high: float = Field(..., description="High price", gt=0)
    low: float = Field(..., description="Low price", gt=0)
    close: float = Field(..., description="Closing price", gt=0)
    volume: int = Field(..., description="Trading volume", ge=0)

    @classmethod
    def from_domain(cls, domain_bar) -> "BarData":
        return cls(
            timestamp=domain_bar.timestamp,
            open=domain_bar.open,
            high=domain_bar.high,
            low=domain_bar.low,
            close=domain_bar.close,
            volume=domain_bar.volume,
        )


class HistoricalDataResponse(BaseModel):
    """Historical data response"""

    bars: List[BarData]

    @classmethod
    def from_domain(cls, domain_bars) -> "HistoricalDataResponse":
        if domain_bars is None:
            return cls(bars=[])
        return cls(bars=[BarData.from_domain(bar) for bar in domain_bars])


# Pydantic models for API
class Contract(BaseModel):
    """Pydantic model for Contract"""

    symbol: str
    exchange: str
    security_type: SecurityType = SecurityType.STOCK
    currency: Optional[str] = None
    local_symbol: Optional[str] = None
    expiry: Optional[str] = None
    strike: Optional[float] = None
    right: Optional[OptionRight] = None
    multiplier: Optional[str] = None
    trading_class: Optional[str] = None

    @classmethod
    def from_domain(cls, contract: DomainContract) -> "Contract":
        """Convert from domain Contract to API Contract"""
        return cls(
            symbol=contract.symbol,
            exchange=contract.exchange,
            security_type=contract.security_type,
            currency=contract.currency,
            local_symbol=contract.local_symbol,
            expiry=contract.expiry,
            strike=contract.strike,
            right=contract.right,
            multiplier=contract.multiplier,
            trading_class=contract.trading_class,
        )


class UnderlyingInfo(BaseModel):
    """Pydantic model for UnderlyingInfo"""

    underlying_symbol: str

    @classmethod
    def from_domain(cls, domain_contract) -> Optional["UnderlyingInfo"]:
        """Create UnderlyingInfo from domain model"""
        if domain_contract is None:
            return None

        return cls(underlying_symbol=domain_contract.underlying_symbol)


class OptionContract(BaseModel):
    """Pydantic model for OptionContract"""

    option_ticker: str
    ltp: float
    type: OptionRight
    lot: int
    last_updated: datetime
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    @classmethod
    def from_domain(cls, domain_contract) -> Optional["OptionContract"]:
        """Create OptionContract from domain model"""
        if domain_contract is None:
            return None

        return cls(
            option_ticker=domain_contract.option_ticker,
            ltp=domain_contract.ltp,
            type=domain_contract.type,
            lot=domain_contract.lot,
            last_updated=domain_contract.last_updated,
        )


class StrikeGroup(BaseModel):
    """Pydantic model for StrikeGroup"""

    strike_price: float
    call_option: Optional[OptionContract] = None
    put_option: Optional[OptionContract] = None

    @classmethod
    def from_domain(cls, domain_strike) -> "StrikeGroup":
        """Create StrikeGroup from domain model"""
        return cls(
            strike_price=domain_strike.strike_price,
            call_option=OptionContract.from_domain(domain_strike.call_option),
            put_option=OptionContract.from_domain(domain_strike.put_option),
        )


class ExpirationGroup(BaseModel):
    """Pydantic model for ExpirationGroup"""

    expiry_date: date
    days_to_expiry: int
    strikes: List[StrikeGroup]
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    @classmethod
    def from_domain(cls, domain_expiry) -> "ExpirationGroup":
        """Create ExpirationGroup from domain model"""
        return cls(
            expiry_date=domain_expiry.expiry_date,
            days_to_expiry=domain_expiry.days_to_expiry,
            strikes=[StrikeGroup.from_domain(strike) for strike in domain_expiry.strikes],
        )


class OptionChainResponse(BaseModel):
    """Pydantic model for OptionChain response"""

    contract: Contract
    underlying_info: UnderlyingInfo
    expirationGroup: List[ExpirationGroup]

    @classmethod
    def from_domain(cls, option_chain: OptionChain) -> "OptionChainResponse":
        """Convert from domain OptionChain to API response"""
        if not option_chain:
            return None
        return cls(
            contract=Contract.from_domain(option_chain.contract),
            underlying_info=UnderlyingInfo.from_domain(option_chain.underlying_info),
            expirationGroup=[ExpirationGroup.from_domain(expiry) for expiry in option_chain.expiration_dates],
        )


# Request model for the API endpoint
class OptionChainRequest(BaseModel):
    """Request model for option chain endpoint"""

    symbol: str
    exchange: str
    expiry: Optional[str] = None
    security_type: SecurityType = SecurityType.OPTION
    currency: str = "USD"
    broker_name: Optional[str] = None

    def to_contract(self) -> DomainContract:
        """Convert to domain Contract"""
        return DomainContract(
            symbol=self.symbol,
            exchange=self.exchange,
            security_type=self.security_type,
            currency=self.currency,
            expiry=self.expiry,
        )


# class OptionChainResponse(OptionChain):
#     """Pydantic model for option chain response that extends the base OptionChain"""

#     model_config = ConfigDict(
#         arbitrary_types_allowed=True,
#         from_attributes=True,  # For ORM mode
#         json_encoders={
#             datetime: lambda v: v.isoformat(),
#         }
#     )

#     # Override any fields that need special handling
#     expiration_dates: List[str] = Field(..., description="List of expiration dates as strings")

#     def model_dump(self, *args, **kwargs) -> dict[str, any]:
#         """Custom model dump to handle non-serializable fields"""
#         data = super().model_dump(*args, **kwargs)
#         # Convert any non-serializable fields here if needed
#         if 'expiration_dates' in data and data['expiration_dates']:
#             data['expiration_dates'] = [str(d) for d in data['expiration_dates']]
#         return data

# class OptionChainInfo(BaseModel):
#     """Option chain information"""

#     underlying_symbol: str
#     expiration_dates: List[str]
#     strikes: List[float]
#     trading_class: Optional[str] = None
#     tick_size: Optional[float] = None
#     last_updated: Optional[datetime] = None


class MarketDataSubscriptionRequest(BaseModel):
    """Request to subscribe to market data"""

    symbol: str
    exchange: str
    security_type: str = Field(default_factory=lambda: settings.get("defaults.contract.security_type", "STK"))
    currency: str = Field(default_factory=lambda: settings.get("defaults.contract.currency", "USD"))
    broker_name: Optional[str] = None
    market_data_type: str = Field(
        default_factory=lambda: settings.get("defaults.data.market_data_type", "DELAYED"),
        description="DELAYED, REALTIME, etc.",
    )
    snapshot: bool = Field(
        default_factory=lambda: settings.get("defaults.data.snapshot", False),
        description="Request snapshot data",
    )


class MarketDataSubscriptionResponse(BaseModel):
    """Market data subscription response"""

    subscription_id: str
    symbol: str
    exchange: str
    status: str
