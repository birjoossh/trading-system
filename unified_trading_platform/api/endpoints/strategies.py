"""
Strategy management endpoints.
Handles strategy initialization, execution, status, and portfolio management.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict
from unified_trading_platform.trading_core.strategy_engine.strategy_manager import (
    StrategyManager as StrategyManagerImpl,
)
from ..models import (
    StrategyInitializeRequest,
    StrategyStatusResponse,
    PortfolioSummaryResponse,
    SuccessResponse,
)

router = APIRouter()

# Store active strategy managers by run_id
_strategy_managers: Dict[str, StrategyManagerImpl] = {}


def _get_strategy_manager(run_id: str) -> StrategyManagerImpl:
    """Get strategy manager by run_id"""
    if run_id not in _strategy_managers:
        raise HTTPException(status_code=404, detail=f"Strategy run '{run_id}' not found")
    return _strategy_managers[run_id]


@router.post("/initialize", response_model=StrategyStatusResponse)
def initialize_strategy(req: StrategyInitializeRequest):
    """Initialize a strategy for execution"""
    try:
        manager = StrategyManagerImpl(
            venue=req.venue,
            strategy_name=req.strategy_name,
            start_date=req.start_date,
            end_date=req.end_date,
            db_path=req.db_path,
        )

        success = manager.initialize()
        if not success:
            raise HTTPException(status_code=500, detail="Failed to initialize strategy")

        run_id = manager.run_id
        _strategy_managers[run_id] = manager

        status = manager.get_status()
        return StrategyStatusResponse(
            run_id=status.get("run_id"),
            is_running=status.get("is_running", False),
            is_initialized=status.get("is_initialized", False),
            venue=status.get("venue"),
            strategy_name=status.get("strategy_name"),
            start_date=status.get("start_date"),
            end_date=status.get("end_date"),
            status="INITIAL" if status.get("is_initialized") else "ERROR",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{run_id}/start", response_model=SuccessResponse)
def start_strategy(run_id: str):
    """Start strategy execution"""
    try:
        manager = _get_strategy_manager(run_id)
        success = manager.start()
        if success:
            return SuccessResponse(message=f"Strategy '{run_id}' started successfully")
        else:
            raise HTTPException(status_code=400, detail=f"Failed to start strategy '{run_id}'")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{run_id}/stop", response_model=SuccessResponse)
def stop_strategy(run_id: str):
    """Stop strategy execution"""
    try:
        manager = _get_strategy_manager(run_id)
        manager.stop()
        return SuccessResponse(message=f"Strategy '{run_id}' stopped successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}/status", response_model=StrategyStatusResponse)
def get_strategy_status(run_id: str):
    """Get current strategy status"""
    try:
        manager = _get_strategy_manager(run_id)
        status = manager.get_status()

        # Determine status string
        status_str = "ERROR"
        if status.get("is_initialized"):
            if status.get("is_running"):
                status_str = "RUNNING"
            else:
                status_str = "INITIAL"

        return StrategyStatusResponse(
            run_id=status.get("run_id"),
            is_running=status.get("is_running", False),
            is_initialized=status.get("is_initialized", False),
            venue=status.get("venue"),
            strategy_name=status.get("strategy_name"),
            start_date=status.get("start_date"),
            end_date=status.get("end_date"),
            status=status_str,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{run_id}/portfolio", response_model=PortfolioSummaryResponse)
def get_portfolio_summary(run_id: str):
    """Get portfolio summary for a strategy"""
    try:
        manager = _get_strategy_manager(run_id)
        summary = manager.get_portfolio_summary()

        # Get current positions
        positions = None
        if manager.strategy_engine:
            positions_data = manager.strategy_engine.get_current_positions()
            positions = []
            for leg in positions_data:
                positions.append(
                    {
                        "leg_id": leg.leg_id,
                        "strike": leg.strike,
                        "qty": leg.qty,
                        "pnl": leg.pnl,
                        "entry_price": leg.entry_px,
                        "entry_timestamp": (leg.entry_ts.isoformat() if leg.entry_ts else None),
                    }
                )

        return PortfolioSummaryResponse(
            total_pnl=summary.get("total_pnl", 0.0),
            open_positions=summary.get("open_positions", 0),
            closed_positions=summary.get("closed_positions", 0),
            total_positions=summary.get("total_positions", 0),
            pending_reentries=summary.get("pending_reentries", 0),
            positions=positions,
            cash_balance=manager.current_portfolio.get("cash_balance"),
            total_value=manager.current_portfolio.get("total_value"),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{run_id}", response_model=SuccessResponse)
def delete_strategy(run_id: str):
    """Stop and remove a strategy"""
    try:
        manager = _get_strategy_manager(run_id)
        manager.stop()
        del _strategy_managers[run_id]
        return SuccessResponse(message=f"Strategy '{run_id}' removed successfully")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
