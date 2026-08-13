"""
Market data endpoints.
Handles historical data, real-time data subscriptions, and option chains.
"""

from fastapi import APIRouter, HTTPException
from unified_trading_platform.api.runtime import get_trading_system
from unified_trading_platform.trading_core.data_models import Contract, SecurityType
from ..models import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    OptionChainRequest,
    MarketDataSubscriptionRequest,
    MarketDataSubscriptionResponse,
    OptionChainResponse,
)

router = APIRouter()


@router.post("/historical", response_model=HistoricalDataResponse)
def get_historical_data(req: HistoricalDataRequest):
    """Get historical bar data for a symbol"""
    ts = get_trading_system()
    try:
        df = ts.get_historical_data(
            symbol=req.symbol,
            exchange=req.exchange,
            security_type=req.security_type,
            currency=req.currency,
            duration=req.duration,
            bar_size=req.bar_size,
            broker_name=req.broker_name,
        )
        return HistoricalDataResponse.from_domain(df)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/option-chain", response_model=OptionChainResponse)
def get_option_chain(req: OptionChainRequest):
    """Get option chain for an underlying symbol"""
    ts = get_trading_system()
    try:
        contract = Contract(
            symbol=req.symbol, exchange=req.exchange, security_type=SecurityType.STOCK, expiry=req.expiry
        )
        option_chain = ts.get_option_chain(req.broker_name, contract)
        return OptionChainResponse.from_domain(option_chain)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe", response_model=MarketDataSubscriptionResponse)
def subscribe_market_data(req: MarketDataSubscriptionRequest):
    """Subscribe to real-time market data"""
    ts = get_trading_system()
    try:
        # Convert security_type string to enum if needed
        sec_type = (
            SecurityType[req.security_type.upper()]
            if hasattr(SecurityType, req.security_type.upper())
            else SecurityType.STOCK
        )

        subscription_id = ts.subscribe_market_data(
            symbol=req.symbol,
            exchange=req.exchange,
            callback=lambda x: None,  # Placeholder callback
            security_type=sec_type,
            currency=req.currency,
            broker_name=req.broker_name,
        )

        return MarketDataSubscriptionResponse(
            subscription_id=str(subscription_id) if subscription_id else "pending",
            symbol=req.symbol,
            exchange=req.exchange,
            status="subscribed" if subscription_id else "pending",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
