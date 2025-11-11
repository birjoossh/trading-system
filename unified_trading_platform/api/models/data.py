"""
Market data-related models.
Handles historical data, option chains, and market data subscriptions.
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from unified_trading_platform.api.config import get_config_value


class HistoricalDataRequest(BaseModel):
    """Request for historical data"""

    @staticmethod
    def _get_example():
        """Get example values from config"""
        return {
            "symbol": "SPY",
            "exchange": "SMART",
            "duration": get_config_value("data.default_duration", "1 D"),
            "bar_size": get_config_value("data.default_bar_size", "1 hour"),
            "security_type": get_config_value("contract.default_security_type", "STK"),
            "currency": get_config_value("contract.default_currency", "USD"),
            "broker_name": None,
        }

    model_config = ConfigDict(json_schema_extra={"example": _get_example()})

    symbol: str = Field(..., description="Trading symbol", examples=["SPY", "AAPL"])
    exchange: str = Field(
        ..., description="Exchange identifier", examples=["SMART", "NYSE"]
    )
    duration: str = Field(
        default_factory=lambda: get_config_value("data.default_duration", "1 D"),
        description="Duration string (e.g., '1 D', '1 M', '1 Y')",
        examples=["1 D", "1 M", "1 Y", "1 W"],
    )
    bar_size: str = Field(
        default_factory=lambda: get_config_value("data.default_bar_size", "1 hour"),
        description="Bar size (e.g., '1 min', '5 min', '1 hour', '1 day')",
        examples=["1 min", "5 min", "1 hour", "1 day"],
    )
    security_type: str = Field(
        default_factory=lambda: get_config_value(
            "contract.default_security_type", "STK"
        ),
        description="Security type",
        examples=["STK", "OPT", "FUT"],
    )
    currency: str = Field(
        default_factory=lambda: get_config_value("contract.default_currency", "USD"),
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
        json_schema_extra={
            "example": {
                "timestamp": "2024-01-01T10:00:00",
                "open": 450.50,
                "high": 451.20,
                "low": 450.10,
                "close": 450.90,
                "volume": 1000000,
            }
        }
    )

    timestamp: datetime = Field(..., description="Bar timestamp")
    open: float = Field(..., description="Opening price", gt=0)
    high: float = Field(..., description="High price", gt=0)
    low: float = Field(..., description="Low price", gt=0)
    close: float = Field(..., description="Closing price", gt=0)
    volume: int = Field(..., description="Trading volume", ge=0)


class HistoricalDataResponse(BaseModel):
    """Historical data response"""

    symbol: str
    exchange: str
    bar_size: str
    rows: int
    data: List[BarData]
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class OptionChainRequest(BaseModel):
    """Request for option chain data"""

    symbol: str
    exchange: str = Field(
        default_factory=lambda: get_config_value("contract.default_exchange", "")
    )
    security_type: str = Field(
        default_factory=lambda: get_config_value(
            "contract.default_security_type", "STK"
        ),
        description="Underlying security type",
    )
    currency: str = Field(
        default_factory=lambda: get_config_value("contract.default_currency", "USD"),
        description="Currency code",
    )
    broker_name: Optional[str] = Field(default=None, description="Broker to use")


class OptionChainInfo(BaseModel):
    """Option chain information"""

    underlying_symbol: str
    expiration_dates: List[str]
    strikes: List[float]
    trading_class: Optional[str] = None
    tick_size: Optional[float] = None
    last_updated: Optional[datetime] = None


class MarketDataSubscriptionRequest(BaseModel):
    """Request to subscribe to market data"""

    symbol: str
    exchange: str
    security_type: str = Field(
        default_factory=lambda: get_config_value(
            "contract.default_security_type", "STK"
        )
    )
    currency: str = Field(
        default_factory=lambda: get_config_value("contract.default_currency", "USD")
    )
    broker_name: Optional[str] = None
    market_data_type: str = Field(
        default_factory=lambda: get_config_value(
            "data.default_market_data_type", "DELAYED"
        ),
        description="DELAYED, REALTIME, etc.",
    )
    snapshot: bool = Field(
        default_factory=lambda: get_config_value("data.default_snapshot", False),
        description="Request snapshot data",
    )


class MarketDataSubscriptionResponse(BaseModel):
    """Market data subscription response"""

    subscription_id: str
    symbol: str
    exchange: str
    status: str
