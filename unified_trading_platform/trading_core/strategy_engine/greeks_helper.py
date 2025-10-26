
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math
from datetime import datetime
import pandas as pd

SQRT2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / SQRT2PI


def _norm_cdf(x: float) -> float:
    # Abramowitz & Stegun via erf
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class BSParams:
    r: float = 0.06  # annual risk-free rate (decimal)
    q: float = 0.00  # dividend yield (decimal)


def _positive(x: float, default: float) -> float:
    try:
        x = float(x)
        if x > 0:
            return x
    except Exception:
        pass
    return default


def yearfrac(start: datetime, end: datetime) -> float:
    """ACT/365F year fraction with non-negative clamp."""
    delta = (end - start).total_seconds()
    return max(0.0, delta) / (365.0 * 24.0 * 3600.0)


def bs_price(S: float, K: float, T: float, r: float, q: float, sigma: float, cp: str) -> float:
    """Black–Scholes price with continuous dividend yield.
    cp: 'C' or 'P'
    """
    cp = cp.upper()
    if T <= 0.0 or sigma <= 0.0:
        # discounted intrinsic as a conservative fallback
        if cp == 'C':
            return max(0.0, S * math.exp(-q * T) - K * math.exp(-r * T))
        else:
            return max(0.0, K * math.exp(-r * T) - S * math.exp(-q * T))
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if cp == 'C':
        return S * math.exp(-q * T) * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    else:
        return K * math.exp(-r * T) * _norm_cdf(-d2) - S * math.exp(-q * T) * _norm_cdf(-d1)


def bs_delta(S: float, K: float, T: float, r: float, q: float, sigma: float, cp: str) -> float:
    """Black–Scholes delta with continuous dividend yield.
    - Call delta in [0, 1]
    - Put delta in [-1, 0]
    """
    cp = cp.upper()
    if T <= 0.0 or sigma <= 0.0:
        # heuristic intrinsic-limit delta when close to expiry or zero vol
        if cp == 'C':
            return 1.0 if S > K else 0.0
        else:
            return -1.0 if S < K else 0.0
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    if cp == 'C':
        return math.exp(-q * T) * _norm_cdf(d1)
    else:
        return -math.exp(-q * T) * _norm_cdf(-d1)


def iv_from_price(
    S: float,
    K: float,
    T: float,
    r: float,
    q: float,
    cp: str,
    price: float,
    lo: float = 1e-6,
    hi: float = 5.0,
    tol: float = 1e-6,
    max_iter: int = 100,
) -> float:
    """Implied volatility by **bisection**. Robust to noisy quotes.
    If the target price is outside the modelable price band, we clamp.
    """
    cp = cp.upper()
    p = max(float(price), 0.0)
    # Bounds prices
    plo = bs_price(S, K, T, r, q, lo, cp)
    phi = bs_price(S, K, T, r, q, hi, cp)
    if p <= plo:
        return lo
    if p >= phi:
        return hi
    a, b = lo, hi
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        pm = bs_price(S, K, T, r, q, m, cp)
        if abs(pm - p) < tol:
            return max(lo, min(m, hi))
        if pm > p:
            b = m
        else:
            a = m
    return max(lo, min(0.5 * (a + b), hi))


def _detect_snapshot_time(chain: pd.DataFrame, default_now: Optional[datetime] = None) -> datetime:
    if "timestamp" in chain.columns and not chain["timestamp"].dropna().empty:
        try:
            return pd.to_datetime(chain["timestamp"]).max().to_pydatetime()
        except Exception:
            pass
    return default_now or datetime.now()


def compute_iv_delta_for_chain(
    chain: pd.DataFrame,
    S: float,
    expiry_dt: datetime,
    *,
    r: float = 0.06,
    q: float = 0.0,
    now_dt: Optional[datetime] = None,
    min_price: float = 0.01,
) -> pd.DataFrame:
    """Return a copy of `chain` with **IV** and **Delta** columns populated.

    Requirements:
      - chain has columns: [OptionType (CE/PE), Strike, Close]
      - S: underlying level at `now_dt` (your chosen snapshot/decision time)
      - expiry_dt: datetime of option expiration (use 15:30 IST on the expiry day for NSE)

    Behavior:
      - If Close < `min_price`, we use a tiny sigma and near-zero delta heuristic.
      - Computation is per-row (pure Python); keep chains reasonably sized.
    """
    df = chain.copy()
    if df.empty:
        return df.assign(IV=pd.Series(dtype=float), Delta=pd.Series(dtype=float))

    # Normalize column names/types
    df["OptionType"] = df["OptionType"].astype(str).str.upper()
    df["Strike"] = df["Strike"].astype(float)
    df["Close"] = df["Close"].astype(float)

    now = now_dt or _detect_snapshot_time(df)
    T = yearfrac(now, expiry_dt)
    r = float(r)
    q = float(q)

    iv_out = []
    delta_out = []
    for _, row in df.iterrows():
        cp = 'C' if row["OptionType"] == 'CE' else 'P'
        K = float(row["Strike"])
        P = float(row["Close"])
        if P < min_price:
            # Deep OTM or stale price: tiny vol, delta ~ 0 with sign heuristic
            sigma = 1e-4
            delta = bs_delta(S, K, T, r, q, sigma, cp)
        else:
            sigma = iv_from_price(S, K, T, r, q, cp, P)
            delta = bs_delta(S, K, T, r, q, sigma, cp)
        iv_out.append(sigma)
        delta_out.append(delta)

    df["IV"] = iv_out
    df["Delta"] = delta_out
    return df


def ensure_delta(
    chain: pd.DataFrame,
    S: float,
    expiry_dt: datetime,
    *,
    r: float = 0.06,
    q: float = 0.0,
    now_dt: Optional[datetime] = None,
    min_price: float = 0.01,
) -> pd.DataFrame:
    """Return chain with a **Delta** column, computing IV/Delta if missing or null.
    If a non-null Delta already exists for most rows, we just return a copy.
    """
    needs = ("Delta" not in chain.columns) or chain["Delta"].isna().mean() > 0.1
    if needs:
        return compute_iv_delta_for_chain(
            chain, S, expiry_dt, r=r, q=q, now_dt=now_dt, min_price=min_price
        )
    return chain.copy()
