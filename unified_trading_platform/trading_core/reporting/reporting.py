from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Tuple, Dict, List
import pandas as pd
import numpy as np
from .utils import ensure_dir

Scope = Literal["package", "leg"]

def _as_trades(df: pd.DataFrame, scope: Scope) -> pd.DataFrame:
    """
    Build a per-trade series of net PnL that we can use for summary metrics.

    package:  one trade per date (sum all legs). Best when square_off_mode='Complete'
    leg:      each leg is a trade (group by date, leg_id). Best when square_off_mode='Partial'
    """
    if scope == "leg":
        trades = (df.groupby(["date","leg_id"], as_index=False)["pnl_after_cost"]
                    .sum()
                    .rename(columns={"pnl_after_cost":"trade_pnl"}))
        # Keep a readable trade key
        trades["trade_key"] = trades["date"].astype(str) + f"::leg"
    else:
        trades = (df.groupby("date", as_index=False)["pnl_after_cost"]
                    .sum()
                    .rename(columns={"pnl_after_cost":"trade_pnl"}))
        trades["trade_key"] = trades["date"].astype(str)
    return trades

def _equity_and_drawdown(pnls: pd.Series) -> Tuple[pd.Series, pd.Series, float, int, int, int]:
    eq = pnls.cumsum()
    peak = eq.cummax()
    dd = eq - peak  # negative/zero
    # max DD stats
    max_dd = float(dd.min()) if len(dd) else 0.0
    if len(dd) == 0 or np.isclose(max_dd, 0):
        return eq, dd, 0.0, 0, 0, 0
    end_idx = int(dd.idxmin())
    # start is previous peak
    start_idx = int((eq.iloc[:end_idx+1]).idxmax())
    # recovery: first index after end_idx where dd == 0 (back to peak), else last
    after = dd.iloc[end_idx+1:]
    if (after == 0).any():
        rec_idx = int(after[after == 0].index[0])
    else:
        rec_idx = int(dd.index[-1])
    duration = rec_idx - start_idx + 1
    return eq, dd, max_dd, duration, start_idx, rec_idx

def _streaks(x: pd.Series) -> Tuple[int, int]:
    # x is boolean Series (True = win)
    max_win = max_loss = cur_win = cur_loss = 0
    for v in x.tolist():
        if v:
            cur_win += 1; max_win = max(max_win, cur_win)
            cur_loss = 0
        else:
            cur_loss += 1; max_loss = max(max_loss, cur_loss)
            cur_win = 0
    return max_win, max_loss

def _max_trades_in_drawdown(dd: pd.Series) -> int:
    # longest consecutive segment where dd < 0
    longest = cur = 0
    for v in dd.tolist():
        if v < 0:
            cur += 1; longest = max(longest, cur)
        else:
            cur = 0
    return longest

def summarize_trades(out_csv: Path, scope: Scope = "package") -> dict:
    """
    Reads the written out_csv (the trade-by-leg CSV from engine.flush),
    computes a summary similar to AlgoTest, and writes:
      - <out>.__metrics.json (this dict)
      - <out>.__equity.csv  (equity curve & drawdown per trade)
    """
    df = pd.read_csv(out_csv)
    trades = _as_trades(df, scope=scope)
    trades = trades.reset_index(drop=True)
    wins = trades["trade_pnl"] > 0
    losses = trades["trade_pnl"] < 0

    n = len(trades)
    overall_profit = float(trades["trade_pnl"].sum())
    avg_per_trade = float(trades["trade_pnl"].mean()) if n else 0.0
    avg_win = float(trades.loc[wins, "trade_pnl"].mean()) if wins.any() else 0.0
    avg_loss = float(trades.loc[losses, "trade_pnl"].mean()) if losses.any() else 0.0  # negative
    max_profit = float(trades["trade_pnl"].max()) if n else 0.0
    max_loss = float(trades["trade_pnl"].min()) if n else 0.0
    win_pct = float(wins.mean() * 100.0) if n else 0.0
    loss_pct = 100.0 - win_pct if n else 0.0

    # equity & dd on trade order (as listed)
    equity, dd, max_dd, dd_dur, dd_start, dd_recover = _equity_and_drawdown(trades["trade_pnl"])
    ret_maxdd = (overall_profit / abs(max_dd)) if max_dd != 0 else np.inf
    rr_ratio = (abs(avg_win) / abs(avg_loss)) if avg_loss != 0 else np.inf
    expectancy_ratio = (avg_per_trade / abs(avg_loss)) if avg_loss != 0 else np.inf

    max_win_streak, max_lose_streak = _streaks(wins)
    max_trades_in_dd = _max_trades_in_drawdown(dd)

    # decorate for dates
    dd_start_date = trades.loc[dd_start, "trade_key"] if n and dd_dur > 0 else None
    dd_recover_date = trades.loc[dd_recover, "trade_key"] if n and dd_dur > 0 else None

    metrics = {
        "scope": scope,
        "overall_profit": round(overall_profit, 2),
        "num_trades": int(n),
        "avg_profit_per_trade": round(avg_per_trade, 2),
        "avg_loss_on_losers": round(avg_loss, 2),         # keep the negative sign
        "avg_profit_on_winners": round(avg_win, 2),
        "max_profit_single_trade": round(max_profit, 2),
        "max_loss_single_trade": round(max_loss, 2),
        "win_pct": round(win_pct, 2),
        "loss_pct": round(loss_pct, 2),
        "max_drawdown": round(max_dd, 2),
        "duration_of_max_dd_trades": int(dd_dur),
        "duration_of_max_dd_span": [dd_start_date, dd_recover_date],
        "return_over_maxdd": (round(ret_maxdd, 2) if np.isfinite(ret_maxdd) else None),
        "reward_to_risk_ratio": (round(rr_ratio, 2) if np.isfinite(rr_ratio) else None),
        "expectancy_ratio": (round(expectancy_ratio, 2) if np.isfinite(expectancy_ratio) else None),
        "max_win_streak": int(max_win_streak),
        "max_losing_streak": int(max_lose_streak),
        "max_trades_in_any_drawdown": int(max_trades_in_dd),
    }

    # write sidecar files
    eq = pd.DataFrame({
        "trade_idx": np.arange(len(trades)),
        "trade_key": trades["trade_key"],
        "trade_pnl": trades["trade_pnl"],
        "equity": equity,
        "drawdown": dd,
    })
    eq_path = out_csv.with_name(out_csv.stem + ".__equity.csv")
    eq.to_csv(eq_path, index=False)

    metrics_path = out_csv.with_name(out_csv.stem + ".__metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2))

    return metrics


def flush_results(rows: List[Dict], out_csv: Path, square_off_mode: str) -> Dict:
    """Writes detail CSV + per-day summary, then computes AlgoTest-style metrics.
    Returns the metrics dict.
    """
    if not rows:
        return {}

    out = pd.DataFrame(rows)
    ensure_dir(out_csv)
    if out_csv.exists():
        prev = pd.read_csv(out_csv)
        out = pd.concat([prev, out], ignore_index=True)
    out.to_csv(out_csv, index=False)

    # Per-day accumulation (compat with existing summary output)
    s = (
        out.groupby("date")["pnl_after_cost"].sum().rename("day_pnl").to_frame()
        .assign(cum_pnl=lambda d: d["day_pnl"].cumsum())
    )
    s.loc["TOTAL"] = [out["pnl_after_cost"].sum(), np.nan]
    sm = out_csv.with_name(out_csv.stem + ".__summary.csv")
    ensure_dir(sm)
    s.to_csv(sm)

    # Rich summary (AlgoTest-style)
    scope = "package" if square_off_mode.lower().startswith("complete") else "leg"
    metrics = summarize_trades(out_csv, scope=scope)
    return metrics