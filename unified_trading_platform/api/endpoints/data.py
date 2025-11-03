"""
Market data endpoints.
Handles historical data, real-time data subscriptions, and option chains.
"""

from fastapi import APIRouter, HTTPException
from typing import List
from datetime import datetime
import pandas as pd
from unified_trading_platform.runtime import get_trading_system
from ..models import (
    HistoricalDataRequest,
    HistoricalDataResponse,
    BarData,
    OptionChainRequest,
    OptionChainInfo,
    MarketDataSubscriptionRequest,
    MarketDataSubscriptionResponse,
    ErrorResponse,
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

        if df.empty:
            return HistoricalDataResponse(
                symbol=req.symbol,
                exchange=req.exchange,
                bar_size=req.bar_size,
                rows=0,
                data=[],
                start_time=None,
                end_time=None,
            )

        # Convert DataFrame to list of BarData
        bars = []
        for idx, row in df.iterrows():
            timestamp = idx if isinstance(idx, datetime) else pd.to_datetime(idx)
            bars.append(
                BarData(
                    timestamp=timestamp,
                    open=float(row.get("open", 0)),
                    high=float(row.get("high", 0)),
                    low=float(row.get("low", 0)),
                    close=float(row.get("close", 0)),
                    volume=int(row.get("volume", 0)),
                )
            )

        start_time = df.index[0] if len(df) > 0 else None
        end_time = df.index[-1] if len(df) > 0 else None

        if not isinstance(start_time, datetime):
            start_time = pd.to_datetime(start_time) if start_time is not None else None
        if not isinstance(end_time, datetime):
            end_time = pd.to_datetime(end_time) if end_time is not None else None

        return HistoricalDataResponse(
            symbol=req.symbol,
            exchange=req.exchange,
            bar_size=req.bar_size,
            rows=len(df),
            data=bars,
            start_time=start_time,
            end_time=end_time,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/option-chain", response_model=OptionChainInfo)
def get_option_chain(req: OptionChainRequest):
    """Get option chain for an underlying symbol"""
    ts = get_trading_system()
    try:
        from unified_trading_platform.trading_core.brokers.base_broker import Contract

        contract = Contract(
            symbol=req.symbol,
            security_type=req.security_type,
            exchange=req.exchange,
            currency=req.currency,
        )

        option_chain = ts.get_option_chain(req.broker_name, contract)

        if hasattr(option_chain, "underlying_symbol"):
            # OptionChain dataclass
            from dataclasses import asdict

            chain_dict = asdict(option_chain)
            return OptionChainInfo(
                underlying_symbol=chain_dict.get("underlying_symbol", req.symbol),
                expiration_dates=chain_dict.get("expiration_dates", []),
                strikes=chain_dict.get("strikes", []),
                trading_class=chain_dict.get("trading_class"),
                tick_size=chain_dict.get("tick_size"),
                last_updated=chain_dict.get("last_updated"),
            )
        else:
            # DataFrame or other format
            return OptionChainInfo(
                underlying_symbol=req.symbol, expiration_dates=[], strikes=[]
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe", response_model=MarketDataSubscriptionResponse)
def subscribe_market_data(req: MarketDataSubscriptionRequest):
    """Subscribe to real-time market data"""
    ts = get_trading_system()
    try:
        from unified_trading_platform.trading_core.brokers.base_broker import (
            Contract,
            SecurityType,
        )

        # Convert security_type string to enum if needed
        sec_type = (
            SecurityType[req.security_type.upper()]
            if hasattr(SecurityType, req.security_type.upper())
            else SecurityType.STOCK
        )

        contract = Contract(
            symbol=req.symbol,
            security_type=sec_type,
            exchange=req.exchange,
            currency=req.currency,
        )

        # For now, subscription returns bool. In future, it should return subscription_id
        # This is a placeholder implementation
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
