from fastapi import APIRouter
from pydantic import BaseModel
from unified_trading_platform.runtime import get_trading_system

router = APIRouter()

class MarketOrderRequest(BaseModel):
    symbol: str
    exchange: str
    action: str
    quantity: int
    broker_name: str
    security_type: str = "STK"
    currency: str = "USD"

@router.post("/market")
def submit_market_order(req: MarketOrderRequest):
    ts = get_trading_system()
    order_id = ts.submit_market_order(
        symbol=req.symbol,
        exchange=req.exchange,
        action=req.action,
        quantity=req.quantity,
        broker_name=req.broker_name,
        security_type=req.security_type,
        currency=req.currency,
    )
    return {"order_id": order_id}



