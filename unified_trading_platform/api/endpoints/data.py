from fastapi import APIRouter
from pydantic import BaseModel
from unified_trading_platform.runtime import get_trading_system

router = APIRouter()

class HistoricalRequest(BaseModel):
    symbol: str
    exchange: str
    duration: str = "1 D"
    bar_size: str = "1 hour"
    security_type: str = "STK"
    currency: str = "USD"
    broker_name: str | None = None

@router.post("/historical")
def historical(req: HistoricalRequest):
    ts = get_trading_system()
    df = ts.get_historical_data(
        symbol=req.symbol,
        exchange=req.exchange,
        security_type=req.security_type,
        currency=req.currency,
        duration=req.duration,
        bar_size=req.bar_size,
        broker_name=req.broker_name,
    )
    return {"rows": len(df), "data": df.reset_index().to_dict(orient="records")}



