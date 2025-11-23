"""
API models module.
Provides consistent data structures for all API endpoints.
"""

from .common import ErrorResponse, SuccessResponse
from .broker import AddBrokerRequest, BrokerInfo, AccountInfo
from .contract import ContractRequest, ContractInfo
from .data import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    OptionChainRequest,
    OptionChainResponse,
    MarketDataSubscriptionRequest,
    MarketDataSubscriptionResponse,
)
from .order import (
    BaseOrderRequest,
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    OrderResponse,
    OrderInfo,
    PositionInfo,
    TradeInfo,
)
from .strategy import (
    StrategyInitializeRequest,
    StrategyStatusResponse,
    PortfolioSummaryResponse,
)

__all__ = [
    # Common models
    "ErrorResponse",
    "SuccessResponse",
    # Broker models
    "AddBrokerRequest",
    "BrokerInfo",
    "AccountInfo",
    # Contract models
    "ContractRequest",
    "ContractInfo",
    # Data models
    "HistoricalDataRequest",
    "HistoricalDataResponse",
    "OptionChainRequest",
    "OptionChainResponse",
    "OptionChainInfo",
    "MarketDataSubscriptionRequest",
    "MarketDataSubscriptionResponse",
    # Order models
    "BaseOrderRequest",
    "MarketOrderRequest",
    "LimitOrderRequest",
    "StopOrderRequest",
    "StopLimitOrderRequest",
    "OrderResponse",
    "OrderInfo",
    "PositionInfo",
    "TradeInfo",
    # Strategy models
    "StrategyInitializeRequest",
    "StrategyStatusResponse",
    "PortfolioSummaryResponse",
]
