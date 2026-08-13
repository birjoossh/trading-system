from __future__ import annotations
import pandas as pd
from unified_trading_platform.trading_core.strategy_engine.config import StrikeCriteria
from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.strategy_engine.greeks_helper import ensure_delta
from unified_trading_platform.trading_core.utils import get_logger
from datetime import datetime

logger = get_logger(__name__)


# --- helpers ---
def _detect_step(strikes: pd.Series, default: float = 50.0) -> float:
    s = pd.Series(sorted(pd.Series(strikes).dropna().unique()))
    if len(s) >= 2:
        diffs = s.diff().dropna()
        try:
            step = float(diffs.mode().iloc[0])
            if step > 0:
                return step
        except Exception:
            pass
    return default


# Expiry inference (needed for delta computation)
def _infer_expiry_dt(chain: pd.DataFrame, params: dict, exchange: str) -> datetime:
    """Infer expiry datetime. Exchange must be provided explicitly."""
    
    # helper to get close time
    def _get_close_time():
        exch_config = settings.get_exchange_config(exchange)
        trading_hours = exch_config.get("trading_hours", {})
        end_time_str = trading_hours.get("end", "15:30") 
        return map(int, end_time_str.split(":"))

    # 1) Explicit from params (supports str/datetime-like)
    for k in ("expiry_dt", "expiry", "Expiry", "expiration", "Expiration"):
        if params and k in params and params[k] is not None:
            dt_obj = pd.to_datetime(params[k])
            if isinstance(dt_obj, pd.Series):
                dt_obj = dt_obj.iloc[0]
            
            end_h, end_m = _get_close_time()

            # If date-only, set exchange close time
            has_time = any(getattr(dt_obj, part, 0) for part in ("hour", "minute", "second"))
            if not has_time:
                dt_obj = dt_obj.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            
            return dt_obj.to_pydatetime() if hasattr(dt_obj, "to_pydatetime") else dt_obj

    # 2) From chain columns
    for col in ("Expiry", "expiry", "Expiration", "expiration"):
        if col in chain.columns and not chain[col].dropna().empty:
            ts = pd.to_datetime(chain[col].dropna())
            # Use the most common expiry or, if ambiguous, the max
            if not ts.mode().empty:
                dt_obj = ts.mode().iloc[0]
            else:
                dt_obj = ts.max()
            
            end_h, end_m = _get_close_time()

            dt_obj = dt_obj.replace(hour=end_h, minute=end_m, second=0, microsecond=0)
            return dt_obj.to_pydatetime() if hasattr(dt_obj, "to_pydatetime") else dt_obj
            
    raise ValueError("expiry_dt not provided and no expiry column found in chain")


def select_strike(
    chain: pd.DataFrame,
    option_type: str,
    atm_price: float,
    criteria: StrikeCriteria,
    exchange: str | None = None,
) -> float:
    """
    Select a strike from the provided option chain.

    Supported modes (criteria.mode, case-insensitive):
      - STRIKE_TYPE: params {strike_type: "ATM"|"OTM{n}"|"ITM{n}", otm_steps?: int}
      - PREMIUM_RANGE: params {lower: float, upper: float}
      - CLOSEST_PREMIUM: params {premium|target: float}
      - PREMIUM_LE: params {value|limit: float}
      - PREMIUM_GE: params {value|limit: float}
      - STRADDLE_WIDTH: params {sign: "+"|"-", multiplier|k|value: float}
      - PCT_OF_ATM (alias %_OF_ATM): params {pct|percent: float, sign?: "+"|"-"}
      - SYNTHETIC_FUTURE: params {strike_type: "ATM"|"OTM{n}"|"ITM{n}", otm_steps?: int}
      - ATM_PREMIUM_PCT: params {pct|percent: float}
      - CLOSEST_DELTA: params {delta|target: float in [0,100] or [0,1]}
      - DELTA_RANGE: params {lower: float, upper: float, position?: "BUY"|"SELL"}

    DataFrame requirements:
      - columns: ["option_type", "strike", "Close", ...]
      - for delta modes, column: ["Delta"] must be present
    """
    mode = (criteria.mode or "").upper()
    params = criteria.params or {}

    # Chains may carry the option premium as "Close" (broker chains) or "price"
    # (backtest/manager chains) — normalize to "Close", which the modes below use.
    if "Close" not in chain.columns and "price" in chain.columns:
        chain = chain.assign(Close=chain["price"])

    df = chain[chain["option_type"].str.upper() == option_type.upper()].copy()
    logger.debug("Option chain data: %s, option_type: %s", df.to_string(), option_type)
    if df.empty:
        raise ValueError(f"No {option_type} rows")

    # common helpers
    step = _detect_step(df["strike"], default=50.0)
    base = round(float(atm_price) / step) * step  # ATM strike from underlying

    def nearest_strike(target: float) -> float:
        # Use simple abs difference minimization
        idx = (df["strike"] - target).abs().idxmin()
        return float(df.loc[idx, "strike"])

    def ce_pe_atm_prices() -> tuple[float, float, float]:
        ce = chain[chain["option_type"].str.upper() == "CE"].copy()
        pe = chain[chain["option_type"].str.upper() == "PE"].copy()
        if ce.empty or pe.empty:
            raise ValueError("Both CE and PE chains are required for this selection mode")
        ce_strike = float(ce.loc[(ce["strike"] - base).abs().idxmin(), "strike"])
        pe_strike = float(pe.loc[(pe["strike"] - base).abs().idxmin(), "strike"])
        ce_px = float(ce[ce["strike"] == ce_strike].iloc[0]["Close"])
        pe_px = float(pe[pe["strike"] == pe_strike].iloc[0]["Close"])
        return ce_px, pe_px, base

    # --- STRIKE_TYPE (ATM/ITM/OTM with steps) ---
    if mode == "STRIKE_TYPE":
        stype = str(params.get("strike_type", "ATM")).upper()
        steps = int(params.get("otm_steps", 0))
        n = int("".join(filter(str.isdigit, stype)) or steps or 0)
        if "OTM" in stype:
            target = base + (step * n if option_type.upper() == "CE" else -step * n)
        elif "ITM" in stype:
            target = base - (step * n if option_type.upper() == "CE" else -step * n)
        else:
            target = base
        return nearest_strike(target)

    # --- PREMIUM_RANGE ---
    if mode == "PREMIUM_RANGE":
        lower = float(params.get("lower"))
        upper = float(params.get("upper"))
        if lower > upper:
            lower, upper = upper, lower
        cand = df[(df["Close"] >= lower) & (df["Close"] <= upper)].copy()
        mid = (lower + upper) / 2.0
        if cand.empty:
            # fallback: closest to mid even if out of bounds
            return float(df.assign(_diff=(df["Close"] - mid).abs()).sort_values("_diff").iloc[0]["strike"])
        return float(cand.assign(_diff=(cand["Close"] - mid).abs()).sort_values("_diff").iloc[0]["strike"])

    # --- CLOSEST_PREMIUM ---
    if mode == "CLOSEST_PREMIUM":
        tgt = float(params.get("premium", params.get("target", 100)))
        return float(df.loc[(df["Close"] - tgt).abs().idxmin(), "strike"])

    # --- PREMIUM_LE ---
    if mode == "PREMIUM_LE":
        lim = float(params.get("value", params.get("limit", 100)))
        cand = df[df["Close"] <= lim]
        if cand.empty:
            # choose smallest premium available
            return float(df.sort_values("Close").iloc[0]["strike"])
        # choose maximum premium <= lim
        return float(cand.sort_values("Close", ascending=False).iloc[0]["strike"])

    # --- PREMIUM_GE ---
    if mode == "PREMIUM_GE":
        lim = float(params.get("value", params.get("limit", 100)))
        cand = df[df["Close"] >= lim]
        if cand.empty:
            # choose largest premium available
            return float(df.sort_values("Close", ascending=False).iloc[0]["strike"])
        # choose minimum premium >= lim
        return float(cand.sort_values("Close").iloc[0]["strike"])

    # --- STRADDLE_WIDTH ---
    if mode == "STRADDLE_WIDTH":
        # params: sign ('+' or '-') and multiplier (float)
        sign = str(params.get("sign", "+")).strip()
        mul = float(params.get("multiplier", params.get("k", params.get("value", 1.0))))
        ce_px, pe_px, base_strike = ce_pe_atm_prices()
        straddle = ce_px + pe_px
        direction = 1.0 if sign == "+" or sign.upper() == "PLUS" else -1.0
        target = base_strike + direction * (mul * straddle)
        # snap to nearest tradable strike
        target = round(target / step) * step
        return nearest_strike(target)

    # --- % OF ATM (percentage of ATM *strike*) ---
    if mode == "%_OF_ATM" or mode == "PCT_OF_ATM":
        sign = str(params.get("sign", "+")).strip()
        pct = float(params.get("pct", params.get("percent", 0)))
        direction = 1.0 if sign == "+" or (pct >= 0 and params.get("sign") is None) else -1.0
        pct = abs(pct)
        target = base * (1.0 + direction * pct / 100.0)
        target = round(target / step) * step
        return nearest_strike(target)

    # --- SYNTHETIC_FUTURE (use synthetic underlying instead of spot) ---
    if mode == "SYNTHETIC_FUTURE":
        stype = str(params.get("strike_type", "ATM")).upper()
        steps = int(params.get("otm_steps", 0))
        ce_px, pe_px, base_strike = ce_pe_atm_prices()
        synth = base_strike - pe_px + ce_px
        synth_base = round(synth / step) * step
        n = int("".join(filter(str.isdigit, stype)) or steps or 0)
        if "OTM" in stype:
            target = synth_base + (step * n if option_type.upper() == "CE" else -step * n)
        elif "ITM" in stype:
            target = synth_base - (step * n if option_type.upper() == "CE" else -step * n)
        else:
            target = synth_base
        return nearest_strike(target)

    # --- ATM_PREMIUM_PCT (percentage of ATM straddle premium) ---
    if mode == "ATM_PREMIUM_PCT":
        pct = float(params.get("pct", params.get("percent", 0)))
        ce_px, pe_px, _ = ce_pe_atm_prices()
        straddle = ce_px + pe_px
        tgt_prem = (pct / 100.0) * straddle
        return float(df.loc[(df["Close"] - tgt_prem).abs().idxmin(), "strike"])

    # --- CLOSEST DELTA ---
    if mode == "CLOSEST_DELTA":
        # Ensure Delta is available by computing IV/Delta if missing
        try:
            if not exchange:
                raise ValueError("CLOSEST_DELTA mode requires 'exchange' to be passed to select_strike()")
            expiry_dt = _infer_expiry_dt(chain, params, exchange)
        except Exception as e:
            raise ValueError(f"CLOSEST_DELTA requires expiry: {e}")
        full = ensure_delta(
            chain,
            S=float(atm_price),
            expiry_dt=expiry_dt,
            r=float(params.get("risk_free", params.get("r", 0.06))),
            q=float(params.get("div_yield", params.get("q", 0.0))),
            now_dt=pd.to_datetime(params["now_dt"]).to_pydatetime() if params.get("now_dt") is not None else None,
            min_price=float(params.get("min_price", 0.01)),
        )
        df = full[full["option_type"].str.upper() == option_type.upper()].copy()
        if "Delta" not in df.columns or df["Delta"].isna().all():
            raise ValueError("Unable to compute Delta for CLOSEST_DELTA mode")
        target = float(params.get("delta", params.get("target", 50)))
        d = df["Delta"].astype(float).abs()
        if d.max() > 1.0:
            d = d / 100.0  # accept 0-100 inputs
        t = target / 100.0 if abs(target) > 1 else abs(target)
        diff = (d - t).abs()
        return float(df.loc[diff.idxmin(), "strike"])

    # --- DELTA_RANGE ---
    if mode == "DELTA_RANGE":
        # Ensure Delta is available by computing IV/Delta if missing
        try:
            if not exchange:
                raise ValueError("DELTA_RANGE mode requires 'exchange' to be passed to select_strike()")
            expiry_dt = _infer_expiry_dt(chain, params, exchange)
        except Exception as e:
            raise ValueError(f"DELTA_RANGE requires expiry: {e}")
        full = ensure_delta(
            chain,
            S=float(atm_price),
            expiry_dt=expiry_dt,
            r=float(params.get("risk_free", params.get("r", 0.06))),
            q=float(params.get("div_yield", params.get("q", 0.0))),
            now_dt=pd.to_datetime(params["now_dt"]).to_pydatetime() if params.get("now_dt") is not None else None,
            min_price=float(params.get("min_price", 0.01)),
        )
        df = full[full["option_type"].str.upper() == option_type.upper()].copy()
        if "Delta" not in df.columns or df["Delta"].isna().all():
            raise ValueError("Unable to compute Delta for DELTA_RANGE mode")
        lo = float(params.get("lower", 0))
        hi = float(params.get("upper", 100))
        position = str(params.get("position", "BUY")).upper()
        d = df["Delta"].astype(float).abs()
        if d.max() > 1.0:
            d = d / 100.0
        lo = lo / 100.0 if lo > 1 else lo
        hi = hi / 100.0 if hi > 1 else hi
        mask = (d >= lo) & (d <= hi)
        cand = df.loc[mask].copy()
        if cand.empty:
            raise ValueError("No strikes fall within the specified delta range")
        cand = cand.assign(abs_delta=d.loc[mask])
        if position == "SELL":
            sel = cand.sort_values("abs_delta", ascending=False).iloc[0]
        else:  # BUY
            sel = cand.sort_values("abs_delta", ascending=True).iloc[0]
        return float(sel["strike"])

    raise NotImplementedError(f"Unsupported strike mode: {mode}")
