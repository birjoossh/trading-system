"""
Order-related models.
Handles order submission, cancellation, status, and position management.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from unified_trading_platform.trading_core.config.config import settings


class BaseOrderRequest(BaseModel):
    """Base order request with common fields"""

    symbol: str = Field(..., description="Trading symbol", examples=["AAPL", "SPY"])
    exchange: str = Field(..., description="Exchange identifier", examples=["SMART", "NYSE"])
    action: str = Field(..., description="BUY or SELL", examples=["BUY", "SELL"])
    quantity: int = Field(..., gt=0, description="Order quantity", examples=[100, 1000])
    broker_name: str = Field(..., description="Broker to use", examples=["ib_paper"])
    security_type: str = Field(
        default_factory=lambda: settings.get("defaults.contract.security_type", "STK"),
        description="Security type",
        examples=["STK", "OPT"],
    )
    currency: str = Field(
        default_factory=lambda: settings.get("defaults.contract.currency", "USD"),
        description="Currency code",
        examples=["USD"],
    )
    account: Optional[str] = Field(default=None, description="Account ID", examples=[None, "DU123456"])
    time_in_force: str = Field(
        default_factory=lambda: settings.get("defaults.contract.time_in_force", "DAY"),
        description="DAY, GTC, IOC, FOK, etc.",
        examples=["DAY", "GTC", "IOC", "FOK"],
    )
    order_type: str = Field(
        default_factory=lambda: settings.get("defaults.contract.order_type", "MARKET"),
        description="Order type",
        examples=["MARKET", "LIMIT", "STOP", "STOP_LIMIT"],
    )
    limit_price: Optional[float] = Field(default=None, description="Limit price", examples=[None, 150.00])
    account: Optional[str] = Field(default=None, description="Account ID", examples=[None, "DU123456"])


class MarketOrderRequest(BaseOrderRequest):
    """Market order request"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "exchange": "SMART",
                "action": "BUY",
                "quantity": 100,
                "broker_name": "ib_paper",
                "security_type": "STK",
                "currency": "USD",
                "account": None,
                "time_in_force": "DAY",
            }
        }
    )

    pass


class LimitOrderRequest(BaseOrderRequest):
    """Limit order request"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "exchange": "SMART",
                "action": "BUY",
                "quantity": 100,
                "broker_name": "ib_paper",
                "security_type": "STK",
                "currency": "USD",
                "account": None,
                "time_in_force": "DAY",
                "limit_price": 150.00,
            }
        }
    )

    limit_price: float = Field(..., gt=0, description="Limit price", examples=[150.00, 450.50])


class StopOrderRequest(BaseOrderRequest):
    """Stop order request"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "symbol": "AAPL",
                "exchange": "SMART",
                "action": "SELL",
                "quantity": 100,
                "broker_name": "ib_paper",
                "security_type": "STK",
                "currency": "USD",
                "account": None,
                "time_in_force": "DAY",
                "stop_price": 145.00,
            }
        }
    )

    stop_price: float = Field(..., gt=0, description="Stop price", examples=[145.00, 440.00])


class StopLimitOrderRequest(BaseOrderRequest):
    """Stop-limit order request"""

    stop_price: float = Field(..., gt=0, description="Stop price")
    limit_price: float = Field(..., gt=0, description="Limit price")


class OrderResponse(BaseModel):
    """Order submission response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "order_id": "550e8400-e29b-41d4-a716-446655440000",
                "broker_order_id": "12345",
                "status": "submitted",
                "message": "Market order submitted successfully",
            }
        }
    )

    order_id: str = Field(..., description="Internal order identifier")
    broker_order_id: Optional[str] = Field(None, description="Broker-assigned order ID")
    status: str = Field(..., description="Order status", examples=["submitted", "pending", "filled"])
    message: Optional[str] = Field(None, description="Optional status message")


"""
 return [
            {
                'order_id': order.order_id,
                'broker_order_id': order.broker_order_id,
                'symbol': order.contract.symbol,
                'action': order.order.action.value,
                'quantity': order.order.quantity,
                'order_type': order.order.order_type.value,
                'status': order.status.value,
                'filled_quantity': order.filled_quantity,
                'remaining_quantity': order.remaining_quantity,
                'avg_fill_price': order.avg_fill_price,
                'created_at': order.created_at,
                'updated_at': order.updated_at
            }
            for order in orders
        ]

"""


class OrderInfo(BaseModel):
    """Order information"""

    order_id: str
    broker_order_id: Optional[str] = None
    broker_name: str
    symbol: str
    exchange: str
    security_type: str
    currency: str
    action: str
    order_type: str
    quantity: int
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: Optional[str] = None
    status: str
    filled_quantity: int = 0
    remaining_quantity: int = 0
    avg_fill_price: Optional[float] = None
    commission: Optional[float] = None
    created_at: datetime
    updated_at: datetime
    account: Optional[str] = None


class PositionInfo(BaseModel):
    """Position information"""

    symbol: str
    exchange: str
    security_type: str
    currency: str
    quantity: int = Field(..., description="Positive for long, negative for short")
    avg_price: Optional[float] = None
    current_price: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    broker_name: Optional[str] = None


class TradeInfo(BaseModel):
    """Trade execution information"""

    trade_id: str
    order_id: str
    broker_trade_id: Optional[str] = None
    execution_id: Optional[str] = None
    symbol: str
    quantity: int
    price: float
    commission: Optional[float] = None
    timestamp: datetime
    side: str
    exchange: Optional[str] = None
