"""
Broker-related models.
Handles broker connection and account information.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from unified_trading_platform.api.config import get_config_value


class AddBrokerRequest(BaseModel):
    """Request to add a broker"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "ib_paper",
                "broker_type": "interactive_brokers",
                "host": "127.0.0.1",
                "port": 7497,
                "client_id": 1,
                "config": None,
            }
        }
    )

    name: str = Field(..., description="Unique broker name", examples=["ib_paper"])
    broker_type: str = Field(
        ...,
        description="Broker type (e.g., 'interactive_brokers', 'paper_broker')",
        examples=["interactive_brokers", "paper_broker"],
    )
    host: str = Field(
        default_factory=lambda: get_config_value("broker.default_host", "127.0.0.1"),
        description="Broker host address",
        examples=["127.0.0.1"],
    )
    port: int = Field(
        default_factory=lambda: get_config_value("broker.default_port", 7498),
        description="Broker port",
        examples=[7497, 7498, 4002],
    )
    client_id: int = Field(
        default_factory=lambda: get_config_value("broker.default_client_id", 1),
        description="Client ID for connection",
        examples=[1, 2, 3],
    )
    config: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional broker-specific config",
        examples=[None, {"timeout": 30}],
    )


class BrokerInfo(BaseModel):
    """Broker information response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "ib_paper",
                "broker_type": "IBBroker",
                "is_connected": True,
                "host": "127.0.0.1",
                "port": 7497,
                "client_id": 1,
            }
        }
    )

    name: str = Field(..., description="Broker name")
    broker_type: str = Field(..., description="Type of broker")
    is_connected: bool = Field(..., description="Whether the broker is connected")
    host: Optional[str] = Field(None, description="Broker host address")
    port: Optional[int] = Field(None, description="Broker port")
    client_id: Optional[int] = Field(None, description="Client ID")


class AccountInfo(BaseModel):
    """Account information response"""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "broker_name": "ib_paper",
                "account_id": "DU123456",
                "cash_balance": 100000.0,
                "buying_power": 200000.0,
                "total_value": 150000.0,
                "equity": 150000.0,
                "margin_available": 50000.0,
                "info": None,
            }
        }
    )

    broker_name: str = Field(..., description="Name of the broker")
    account_id: Optional[str] = Field(None, description="Account identifier")
    cash_balance: Optional[float] = Field(None, description="Cash balance in the account")
    buying_power: Optional[float] = Field(None, description="Buying power available")
    total_value: Optional[float] = Field(None, description="Total account value including positions")
    equity: Optional[float] = Field(None, description="Account equity")
    margin_available: Optional[float] = Field(None, description="Available margin for trading")
    info: Optional[Dict[str, Any]] = Field(None, description="Additional account details")
