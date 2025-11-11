"""
Strategy-related models.
Handles strategy initialization, execution status, and portfolio management.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from unified_trading_platform.api.config import get_config_value


class StrategyInitializeRequest(BaseModel):
    """Request to initialize a strategy"""

    venue: str = Field(..., description="Broker venue name")
    strategy_name: str = Field(..., description="Strategy configuration name")
    start_date: Optional[str] = Field(
        default=None, description="Start date for backtesting (YYYY-MM-DD)"
    )
    end_date: Optional[str] = Field(
        default=None, description="End date for backtesting (YYYY-MM-DD)"
    )
    db_path: str = Field(
        default_factory=lambda: get_config_value(
            "strategy.default_db_path", "trading_system.db"
        ),
        description="Database path",
    )


class StrategyStatusResponse(BaseModel):
    """Strategy status response"""

    run_id: Optional[str] = None
    is_running: bool
    is_initialized: bool
    venue: str
    strategy_name: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = Field(
        default_factory=lambda: get_config_value("strategy.default_status", "INITIAL"),
        description="INITIAL, RUNNING, FINISHED, ERROR",
    )


class PortfolioSummaryResponse(BaseModel):
    """Portfolio summary response"""

    total_pnl: float = Field(
        default_factory=lambda: get_config_value("portfolio.default_total_pnl", 0.0)
    )
    open_positions: int = Field(
        default_factory=lambda: get_config_value("portfolio.default_open_positions", 0)
    )
    closed_positions: int = Field(
        default_factory=lambda: get_config_value(
            "portfolio.default_closed_positions", 0
        )
    )
    total_positions: int = Field(
        default_factory=lambda: get_config_value("portfolio.default_total_positions", 0)
    )
    pending_reentries: int = Field(
        default_factory=lambda: get_config_value(
            "portfolio.default_pending_reentries", 0
        )
    )
    positions: Optional[List[Dict[str, Any]]] = None
    cash_balance: Optional[float] = None
    total_value: Optional[float] = None
