"""
Builders for synthetic market data used across the test suite.

Kept separate from conftest.py so tests can import them directly, and so the
shapes they produce (chain columns, tick fields) are defined in exactly one
place — if the engine's expected input shape changes, it changes here.
"""

import datetime as dt

import pandas as pd

# Ground-truth facts about the bundled sample session.
SESSION_DATE = dt.date(2024, 1, 2)
SESSION_EXPIRY = dt.date(2024, 1, 4)
NIFTY_SYMBOL = "NIFTY 50"
STRIKE_STEP = 50.0


def make_chain(
    premiums: dict,
    expiry: dt.date = SESSION_EXPIRY,
    symbol: str = NIFTY_SYMBOL,
    lot: int = 75,
) -> pd.DataFrame:
    """Build an option-chain snapshot in the shape the engine consumes.

    `premiums` maps (strike, option_type) -> premium, e.g. {(21600, "CE"): 120.0}.
    """
    rows = []
    for (strike, option_type), price in sorted(premiums.items()):
        rows.append(
            {
                "underlying_symbol": symbol,
                "expiry": expiry,
                "strike": float(strike),
                "option_type": option_type.upper(),
                "price": float(price),
                "lot": lot,
                "last_updated": None,
            }
        )
    return pd.DataFrame(rows)


def straddle_chain(
    center: float = 21600.0,
    ce_atm: float = 120.0,
    pe_atm: float = 80.0,
    width: int = 4,
    step: float = STRIKE_STEP,
    expiry: dt.date = SESSION_EXPIRY,
) -> pd.DataFrame:
    """A symmetric chain around `center` with monotone premiums.

    Calls get cheaper as strikes rise and puts get richer — the usual shape — so
    premium-based strike selection has a single well-defined answer.
    """
    premiums = {}
    for i in range(-width, width + 1):
        strike = center + i * step
        premiums[(strike, "CE")] = max(1.0, ce_atm - i * 20.0)
        premiums[(strike, "PE")] = max(1.0, pe_atm + i * 20.0)
    return make_chain(premiums, expiry=expiry)


def repriced(chain: pd.DataFrame, updates: dict) -> pd.DataFrame:
    """Copy a chain with some premiums replaced.

    `updates` maps (strike, option_type) -> new premium.
    """
    out = chain.copy()
    for (strike, option_type), price in updates.items():
        mask = (out["strike"] == float(strike)) & (out["option_type"] == option_type.upper())
        out.loc[mask, "price"] = float(price)
    return out


def make_tick(
    timestamp,
    price: float,
    symbol: str = NIFTY_SYMBOL,
    exchange: str = "NSE",
    currency: str = "INR",
):
    """A TickData carrying the underlying price the way replayed backtest bars do.

    Backtest bars populate open/high/low/close but not `last`, so the engine's
    `_get_underlying_price` falls through to `close`; mirror that here.
    """
    from unified_trading_platform.trading_core.data_models import SecurityType, TickData

    return TickData(
        timestamp=pd.Timestamp(timestamp),
        exchange=exchange,
        security_type=SecurityType.STOCK,
        symbol=symbol,
        currency=currency,
        open=price,
        high=price,
        low=price,
        close=price,
        volume=0,
    )


def at(time_str: str, date: dt.date = SESSION_DATE) -> pd.Timestamp:
    """`at("11:00")` -> Timestamp at that time on the sample session date."""
    return pd.Timestamp(f"{date.isoformat()} {time_str}")
