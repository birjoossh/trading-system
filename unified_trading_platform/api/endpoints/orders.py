"""
Order management endpoints.
Handles order submission, cancellation, status checking, and position management.
"""

from fastapi import APIRouter, HTTPException
from typing import List, Optional
from datetime import datetime
from unified_trading_platform.api.runtime import get_trading_system
from ..models import (
    MarketOrderRequest,
    LimitOrderRequest,
    StopOrderRequest,
    StopLimitOrderRequest,
    OrderResponse,
    OrderInfo,
    PositionInfo,
    TradeInfo,
    SuccessResponse,
)

router = APIRouter()


@router.post("/market", response_model=OrderResponse)
def submit_market_order(req: MarketOrderRequest):
    """Submit a market order"""
    ts = get_trading_system()
    try:
        order_id = ts.submit_market_order(
            symbol=req.symbol,
            exchange=req.exchange,
            action=req.action,
            quantity=req.quantity,
            broker_name=req.broker_name,
            security_type=req.security_type,
            currency=req.currency,
            account=req.account,
        )
        return OrderResponse(
            order_id=order_id,
            status="submitted",
            message="Market order submitted successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/limit", response_model=OrderResponse)
def submit_limit_order(req: LimitOrderRequest):
    """Submit a limit order"""
    ts = get_trading_system()
    try:
        order_id = ts.submit_limit_order(
            symbol=req.symbol,
            exchange=req.exchange,
            action=req.action,
            quantity=req.quantity,
            limit_price=req.limit_price,
            broker_name=req.broker_name,
            security_type=req.security_type,
            currency=req.currency,
            time_in_force=req.time_in_force,
            account=req.account,
        )
        return OrderResponse(
            order_id=order_id,
            status="submitted",
            message="Limit order submitted successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=OrderResponse)
def submit_stop_order(req: StopOrderRequest):
    """Submit a stop order"""
    ts = get_trading_system()
    try:
        order_id = ts.submit_stop_order(
            symbol=req.symbol,
            exchange=req.exchange,
            action=req.action,
            quantity=req.quantity,
            stop_price=req.stop_price,
            broker_name=req.broker_name,
            security_type=req.security_type,
            currency=req.currency,
            time_in_force=req.time_in_force,
            account=req.account,
        )
        return OrderResponse(
            order_id=order_id,
            status="submitted",
            message="Stop order submitted successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop-limit", response_model=OrderResponse)
def submit_stop_limit_order(req: StopLimitOrderRequest):
    """Submit a stop-limit order"""
    raise HTTPException(status_code=501, detail="Stop-limit orders not yet implemented")


@router.delete("/{order_id}", response_model=SuccessResponse)
def cancel_order(order_id: str):
    """Cancel an order"""
    ts = get_trading_system()
    try:
        success = ts.cancel_order(order_id)
        if success:
            return SuccessResponse(message=f"Order '{order_id}' cancelled successfully")
        else:
            raise HTTPException(status_code=400, detail=f"Failed to cancel order '{order_id}'")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{order_id}", response_model=OrderInfo)
def get_order_status(order_id: str):
    """Get status of a specific order"""
    ts = get_trading_system()
    try:
        order_data = ts.get_order_status(order_id)
        if not order_data:
            raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found")

        return OrderInfo(**order_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[OrderInfo])
def get_all_orders():
    """Get all orders"""
    ts = get_trading_system()
    try:
        orders = ts.get_all_orders()
        return [OrderInfo(**order) for order in orders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/orders", response_model=List[OrderInfo])
def get_order_history(
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get order history with optional filtering"""
    ts = get_trading_system()
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        orders = ts.get_order_history(symbol, start_dt, end_dt)
        return [OrderInfo(**order) for order in orders]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/trades", response_model=List[TradeInfo])
def get_trade_history(
    symbol: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    """Get trade history with optional filtering"""
    ts = get_trading_system()
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None

        trades = ts.get_trade_history(symbol, start_dt, end_dt)
        return [TradeInfo(**trade) for trade in trades]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=List[PositionInfo])
def get_positions(broker_name: Optional[str] = None):
    """Get current positions"""
    ts = get_trading_system()
    try:
        positions = ts.get_positions(broker_name)
        return [PositionInfo(**pos) for pos in positions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
