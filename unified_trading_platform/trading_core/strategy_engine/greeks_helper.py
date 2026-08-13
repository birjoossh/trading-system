from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Union
from datetime import datetime
import pandas as pd
import numpy as np

# Standard Normal PDF/CDF constants
SQRT2PI = np.sqrt(2.0 * np.pi)

def _norm_pdf_np(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / SQRT2PI

def _norm_cdf_np(x: np.ndarray) -> np.ndarray:
    """Cumulative distribution function for the standard normal distribution
    using Abramowitz & Stegun 7.1.26 approximation (error < 1.5e-7)
    """
    # Protect against overflow/underflow
    # For large positive x, CDF -> 1. For large negative x, CDF -> 0.
    
    # We use the approximation for x >= 0. For x < 0, use 1 - CDF(-x).
    # t = 1 / (1 + p*x)
    # poly = t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))))
    # cdf = 1 - norm_pdf(x) * poly
    
    # Constants
    p = 0.2316419
    a1 = 0.319381530
    a2 = -0.356563782
    a3 = 1.781477937
    a4 = -1.821255978
    a5 = 1.330274429

    x_abs = np.abs(x)
    t = 1.0 / (1.0 + p * x_abs)
    
    # Polynomial term
    poly = t * (a1 + t * (a2 + t * (a3 + t * (a4 + t * a5))))
    
    # PDF term (recalculated here or we could pass it if we had it)
    pdf = np.exp(-0.5 * x_abs * x_abs) / SQRT2PI
    
    cdf_abs = 1.0 - pdf * poly
    
    # Handle signs
    return np.where(x >= 0, cdf_abs, 1.0 - cdf_abs)


def pricing_setting(key: str, fallback):
    """Pricing assumption from config.yaml (`pricing.*`)."""
    from unified_trading_platform.trading_core.config.config import settings

    value = settings.get(f"pricing.{key}")
    return fallback if value is None else value


def risk_free_rate() -> float:
    return float(pricing_setting("risk_free_rate", 0.06))


def dividend_yield() -> float:
    return float(pricing_setting("dividend_yield", 0.0))


def min_option_price() -> float:
    return float(pricing_setting("min_option_price", 0.01))


@dataclass
class BSParams:
    """Market assumptions for pricing; defaults come from config.yaml."""

    r: float = field(default_factory=risk_free_rate)  # annual risk-free rate (decimal)
    q: float = field(default_factory=dividend_yield)  # dividend yield (decimal)


def yearfrac(start: datetime, end: datetime) -> float:
    """ACT/365F year fraction with non-negative clamp."""
    delta = (end - start).total_seconds()
    return max(0.0, delta) / (365.0 * 24.0 * 3600.0)


def bs_price_vec(
    S: Union[float, np.ndarray],
    K: Union[float, np.ndarray],
    T: float,
    r: float,
    q: float,
    sigma: Union[float, np.ndarray],
    cp: Union[str, np.ndarray],
) -> Union[float, np.ndarray]:
    """Vectorized Black-Scholes price."""
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    
    # Handle cp: 'C' or 'P'. If string scalar, broadcast. If array, handle.
    # We will compute call price and put price relation: Put = Call - S*e^-qT + K*e^-rT
    # Or just compute both and select.
    
    # Filter valid inputs
    # T > 0, sigma > 0
    
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    
    call_price = S * np.exp(-q * T) * _norm_cdf_np(d1) - K * np.exp(-r * T) * _norm_cdf_np(d2)
    put_price = K * np.exp(-r * T) * _norm_cdf_np(-d2) - S * np.exp(-q * T) * _norm_cdf_np(-d1)
    
    # Return based on cp
    if isinstance(cp, str):
        return call_price if cp.upper().startswith("C") else put_price
    
    # Array of 'C'/'P' (or 'CE'/'PE')
    cp_arr = np.char.upper(np.asarray(cp, dtype=str))
    is_call = np.char.startswith(cp_arr, 'C')
    return np.where(is_call, call_price, put_price)


def bs_delta_vec(
    S: Union[float, np.ndarray],
    K: Union[float, np.ndarray],
    T: float,
    r: float,
    q: float,
    sigma: Union[float, np.ndarray],
    cp: Union[str, np.ndarray],
) -> Union[float, np.ndarray]:
    """Vectorized Black-Scholes delta."""
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    sigma = np.asarray(sigma, dtype=float)
    
    # Standard d1
    # Check for sigma > 0 and T > 0
    # We assume valid inputs or handled outside for simplicity in vectorization, 
    # but let's add safeguards for T=0 or sigma=0?
    
    # Just standard formula
    sqT = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqT)
    
    delta_call = np.exp(-q * T) * _norm_cdf_np(d1)
    delta_put = -np.exp(-q * T) * _norm_cdf_np(-d1)
    
    if isinstance(cp, str):
        return delta_call if cp.upper().startswith("C") else delta_put
    
    cp_arr = np.char.upper(np.asarray(cp, dtype=str))
    is_call = np.char.startswith(cp_arr, 'C')
    return np.where(is_call, delta_call, delta_put)

# We keep legacy scalar scalar functions for compatibility if needed, 
# but they can just map to the vectorized ones.
def bs_price(S: float, K: float, T: float, r: float, q: float, sigma: float, cp: str) -> float:
    return float(bs_price_vec(S, K, T, r, q, sigma, cp))

def bs_delta(S: float, K: float, T: float, r: float, q: float, sigma: float, cp: str) -> float:
    return float(bs_delta_vec(S, K, T, r, q, sigma, cp))

def iv_from_price_scalar(S: float, K: float, T: float, r: float, q: float, cp: str, price: float) -> float:
    """Scalar IV calculation using bisection (kept for robustness)."""
    lo = float(pricing_setting("implied_vol.lower_bound", 1e-6))
    hi = float(pricing_setting("implied_vol.upper_bound", 5.0))
    tol = float(pricing_setting("implied_vol.tolerance", 1e-6))
    max_iter = int(pricing_setting("implied_vol.max_iterations", 100))
    
    p = max(float(price), 0.0)
    cp_code = 'C' if cp.upper().startswith('C') else 'P'
    
    # Use scalar bs_price for speed in loop
    def _price(sig):
        return bs_price(S, K, T, r, q, sig, cp_code)
        
    plo = _price(lo)
    phi = _price(hi)
    if p <= plo:
        return lo
    if p >= phi:
        return hi
    
    a, b = lo, hi
    for _ in range(max_iter):
        m = 0.5 * (a + b)
        pm = _price(m)
        if abs(pm - p) < tol:
            return m
        if pm > p:
            b = m
        else:
            a = m
    return m

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
    r: Optional[float] = None,
    q: Optional[float] = None,
    now_dt: Optional[datetime] = None,
    min_price: Optional[float] = None,
) -> pd.DataFrame:
    """Vectorized calculation of IV and Delta."""
    r = risk_free_rate() if r is None else r
    q = dividend_yield() if q is None else q
    min_price = min_option_price() if min_price is None else min_price
    df = chain.copy()
    if df.empty:
        return df.assign(IV=pd.Series(dtype=float), Delta=pd.Series(dtype=float))

    # Pre-processing
    if "strike" in df.columns:
        df["Strike"] = df["strike"]
    elif "Strike" not in df.columns:
        # If neither exists
        return df
    
    df["option_type"] = df["option_type"].astype(str).str.upper()
    df["Strike"] = df["Strike"].astype(float)
    df["Close"] = df["Close"].astype(float)
    
    now = now_dt or _detect_snapshot_time(df)
    T = max(1e-5, yearfrac(now, expiry_dt)) # Avoid T=0 division
    
    # 1. Calculate IV
    # We still iterate for IV because bisection is hard to vectorize efficiently without SciPy
    # But we can use apply which is cleaner (though not necessarily much faster than loop)
    # However, we can filter out deep OTM/garbage first
    
    def _calc_row_iv(row):
        P = row.Close
        if P < min_price:
            return 1e-4
        return iv_from_price_scalar(S, row.Strike, T, r, q, row.option_type, P)
    
    # Using list comprehension which is often faster than apply for simple scalar ops
    iv_values = [
        _calc_row_iv(row) for row in df.itertuples()
    ]
    df["IV"] = iv_values
    
    # 2. Vectorized Delta
    df["Delta"] = bs_delta_vec(
        S=S,
        K=df["Strike"].values,
        T=T,
        r=r,
        q=q,
        sigma=df["IV"].values,
        cp=df["option_type"].values
    )
    
    return df

def ensure_delta(
    chain: pd.DataFrame,
    S: float,
    expiry_dt: datetime,
    *,
    r: Optional[float] = None,
    q: Optional[float] = None,
    now_dt: Optional[datetime] = None,
    min_price: Optional[float] = None,
) -> pd.DataFrame:
    needs = ("Delta" not in chain.columns) or chain["Delta"].isna().mean() > 0.1
    if needs:
        return compute_iv_delta_for_chain(chain, S, expiry_dt, r=r, q=q, now_dt=now_dt, min_price=min_price)
    return chain.copy()
