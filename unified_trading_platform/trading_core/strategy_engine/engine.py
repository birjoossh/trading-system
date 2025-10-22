from __future__ import annotations
import math, datetime as dt
import copy
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass
import numpy as np, pandas as pd

from config import StrategyConfig, LegSpec, StrikeCriteria, RiskConfig, RiskRule, TrailRule, ReEntryRule
from utils import parse_time, ensure_dir, nearest_ts
# from .adapters.jio import JioH5Adapter
from strikes import select_strike
from reporting import flush_results

def weekly_expiry_for(date: dt.date) -> dt.date:
    switch = dt.date(2025,9,1); wd = 1 if date >= switch else 3  # Tue else Thu
    d = date
    while d.weekday() != wd: d += dt.timedelta(days=1)
    return d

def monthly_expiry_for(date: dt.date) -> dt.date:
    switch = dt.date(2025,9,1); wd = 1 if date >= switch else 3
    y,m = date.year, date.month
    nxt = dt.date(y+1,1,1) if m==12 else dt.date(y,m+1,1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() != wd: d -= dt.timedelta(days=1)
    return d


def next_weekly_expiry_for(date: dt.date) -> dt.date:
    this = weekly_expiry_for(date)
    nxt  = weekly_expiry_for(this + dt.timedelta(days=1))
    return nxt


def next_monthly_expiry_for(date: dt.date) -> dt.date:
    this = monthly_expiry_for(date)
    nm = (this.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    return monthly_expiry_for(nm)


def resolve_expiry_keyword(date: dt.date, keyword: str) -> dt.date:
    key = (keyword or "Weekly").replace(" ", "").lower()
    if key == "weekly":
        return weekly_expiry_for(date)
    if key == "nextweekly":
        return next_weekly_expiry_for(date)
    if key == "monthly":
        return monthly_expiry_for(date)
    if key == "nextmonthly":
        return next_monthly_expiry_for(date)
    return weekly_expiry_for(date)

# ---------------- Re-entry helpers ----------------
REENTRY_MODES = {
    "RE_ASAP", "RE_ASAP_REV",
    "RE_COST", "RE_COST_REV",
    "RE_MOMENTUM", "RE_MOMENTUM_REV",
    "LAZY_LEG",
}

def _reverse_position(pos: str) -> str:
    return "Buy" if str(pos).lower().startswith("sell") else "Sell"


@dataclass
class PendingReEntry:
    parent_leg_id: int
    trigger: str                  # "SL" or "TARGET"
    mode: str
    created_ts: pd.Timestamp
    spec: LegSpec
    watch_strike: float | None = None   # for RE_COST
    watch_price: float | None = None    # for RE_COST / RE_MOMENTUM

# ---- coercion helpers (accept dicts or dataclasses) ----

def _risk_from_any(obj):
    if isinstance(obj, RiskConfig):
        return obj
    if isinstance(obj, dict):
        t = obj.get('target', {})
        s = obj.get('sl', {})
        tr = obj.get('trail', {})
        def rr(d, default_basis='premium_pct'):
            if not isinstance(d, dict):
                return RiskRule(enabled=False, basis=default_basis, value=0.0)
            return RiskRule(
                enabled=bool(d.get('enabled', True)),
                basis=str(d.get('basis', default_basis)),
                value=float(d.get('value', 0.0))
            )
        trail = TrailRule(
            enabled=bool(tr.get('enabled', False)),
            basis=str(tr.get('basis', 'points')),
            value=float(tr.get('value', 0.0))
        )
        return RiskConfig(target=rr(t), sl=rr(s), trail=trail)
    # default empty (all disabled)
    return RiskConfig()


def _reentry_from_any(obj):
    if isinstance(obj, ReEntryRule):
        return obj
    if isinstance(obj, dict):
        return ReEntryRule(
            enabled=bool(obj.get('enabled', False)),
            mode=str(obj.get('mode', 'RE_ASAP')).upper(),
            max_count=int(obj.get('max_count', 0)),
            lazy_leg=obj.get('lazy_leg')
        )
    return ReEntryRule()

class LiveLeg:
    def __init__(self, leg_id:int, spec:LegSpec, strike:float, qty:int):
        self.leg_id=leg_id; self.spec=spec; self.strike=strike; self.qty=qty
        self.entry_ts=self.exit_ts=None; self.entry_px=self.exit_px=None
        self.entry_S=None; self.best_fav_px=None
        self.pnl=0.0; self.hit_sl=False; self.hit_target=False; self.hit_trail=False; self.exit_reason=None
        self.reentry_id=0; self.expiry_date=None
        # re-entry counters
        self.re_sl_count=0
        self.re_tgt_count=0


def _is_short(position: str) -> bool:
    return str(position).lower().startswith("sell")


def _hit_target(rule, position: str, entry_px: float, entry_S: float, ltp: float, S: float) -> bool:
    if not rule or not getattr(rule, "enabled", False):
        return False
    b = str(getattr(rule, "basis", "premium_pct")).lower()
    v = float(getattr(rule, "value", 0.0))
    short = _is_short(position)
    if b == "premium_pts":
        move = (entry_px - ltp) if short else (ltp - entry_px)
        return move >= v
    if b == "premium_pct":
        ref = entry_px if entry_px else 1.0
        ret = ((entry_px - ltp)/ref) if short else ((ltp - entry_px)/ref)
        return ret >= v/100.0
    if b == "underlying_pts":
        move_up = S - entry_S
        return (move_up <= -v) if short else (move_up >= v)
    if b == "underlying_pct":
        refS = entry_S if entry_S else 1.0
        ret_up = (S - entry_S)/refS
        return (ret_up <= -v/100.0) if short else (ret_up >= v/100.0)
    return False


def _hit_stop(rule, position: str, entry_px: float, entry_S: float, ltp: float, S: float) -> bool:
    if not rule or not getattr(rule, "enabled", False):
        return False
    b = str(getattr(rule, "basis", "premium_pct")).lower()
    v = float(getattr(rule, "value", 0.0))
    short = _is_short(position)
    if b == "premium_pts":
        loss = (ltp - entry_px) if short else (entry_px - ltp)
        return loss >= v
    if b == "premium_pct":
        ref = entry_px if entry_px else 1.0
        loss = ((ltp - entry_px)/ref) if short else ((entry_px - ltp)/ref)
        return loss >= v/100.0
    if b == "underlying_pts":
        move_up = S - entry_S
        return (move_up >= v) if short else (move_up <= -v)
    if b == "underlying_pct":
        refS = entry_S if entry_S else 1.0
        ret_up = (S - entry_S)/refS
        return (ret_up >= v/100.0) if short else (ret_up <= -v/100.0)
    return False


def _trail_stop(trail_rule, position: str, best_fav_px: float, ltp: float) -> bool:
    if not trail_rule or not getattr(trail_rule, "enabled", False):
        return False
    basis = str(getattr(trail_rule, "basis", "points")).lower()
    val = float(getattr(trail_rule, "value", 0.0))
    short = _is_short(position)
    if best_fav_px is None:
        return False
    if basis == "points":
        stop = (best_fav_px + val) if short else (best_fav_px - val)
        return ltp >= stop if short else ltp <= stop
    if basis == "percent":
        stop = (best_fav_px * (1 + val/100.0)) if short else (best_fav_px * (1 - val/100.0))
        return ltp >= stop if short else ltp <= stop
    return False

# class Backtester:
#     def __init__(self, cfg: StrategyConfig, out_csv: Path):
#         self.cfg = cfg; self.out_csv = out_csv; self.rows: List[Dict] = []

#     def run_day(self, date: dt.date, adapter: JioH5Adapter, index_name: str="NIFTY"):
#         spot = adapter.spot_series(); fut = adapter.futures_series()
#         under = fut if (self.cfg.underlying_from.lower().startswith("fut") and fut is not None) else spot
#         opt = adapter.options_table()

#         e_ts = pd.Timestamp.combine(date, parse_time(self.cfg.entry_time))
#         x_ts = pd.Timestamp.combine(date, parse_time(self.cfg.exit_time))
#         e_ts = nearest_ts(under, e_ts); x_ts = nearest_ts(under, x_ts)

#         # Build an options snapshot ("chain") at entry time and get ATM underlying
#         snap_ts = nearest_ts(opt, e_ts)
#         chain = opt.loc[opt.index == snap_ts].copy()
#         atm_px = float(under.loc[e_ts])

#         # --- helpers bound to this day's data ---
#         def chain_at(ts: pd.Timestamp):
#             st = nearest_ts(opt, ts)
#             return opt.loc[opt.index == st].copy()

#         def atm_px_at(ts: pd.Timestamp) -> float:
#             return float(under.loc[nearest_ts(under, ts)])

#         def filter_expiry(df: pd.DataFrame, exp_date: dt.date) -> pd.DataFrame:
#             if "Expiry" in df.columns:
#                 d2 = df[df["Expiry"] == exp_date]
#                 if not d2.empty:
#                     return d2
#             return df

#         # Build LegSpec from dict (used by LAZY_LEG)
#         def leg_from_dict(d: Dict) -> LegSpec:
#             scd = d.get("strike_criteria", {})
#             sc = StrikeCriteria(mode=scd.get("mode", "STRIKE_TYPE"), params=scd.get("params", {}))
#             rd = d.get("risk", {})
#             def rr(x, default_basis="premium_pct"):
#                 if not isinstance(x, dict):
#                     return RiskRule(enabled=False, basis=default_basis, value=0.0)
#                 return RiskRule(enabled=bool(x.get("enabled", True)), basis=str(x.get("basis", default_basis)), value=float(x.get("value", 0.0)))
#             trd = rd.get("trail", {})
#             trail = TrailRule(enabled=bool(trd.get("enabled", False)), basis=str(trd.get("basis", "points")), value=float(trd.get("value", 0.0)))
#             risk = RiskConfig(target=rr(rd.get("target")), sl=rr(rd.get("sl")), trail=trail)
#             return LegSpec(
#                 segment=d.get("segment", "Options"),
#                 position=d.get("position", "Sell"),
#                 option_type=d.get("option_type", "CE"),
#                 expiry=d.get("expiry", "Weekly"),
#                 qty_lots=int(d.get("qty_lots", 1)),
#                 strike_criteria=sc,
#                 risk=risk,
#             )

#         pending: List[PendingReEntry] = []

#         def _spawn_or_queue_reentry(ts: pd.Timestamp, leg: LiveLeg, reason: str):
#             rule = _reentry_from_any(leg.spec.reentry_on_sl if reason == "SL" else leg.spec.reentry_on_target)
#             if not (rule and getattr(rule, "enabled", False)):
#                 return
#             if rule.max_count <= 0:
#                 return
#             # enforce caps (max 20 per trigger)
#             if reason == "SL" and leg.re_sl_count >= min(20, rule.max_count):
#                 return
#             if reason == "TARGET" and leg.re_tgt_count >= min(20, rule.max_count):
#                 return

#             # respect no_reentry_after, if set
#             if self.cfg.no_reentry_after:
#                 cutoff = pd.Timestamp.combine(date, parse_time(self.cfg.no_reentry_after))
#                 if ts >= nearest_ts(under, cutoff):
#                     return

#             mode = str(rule.mode).upper()
#             if mode.endswith("_REV"):
#                 new_pos = _reverse_position(leg.spec.position)
#             else:
#                 new_pos = leg.spec.position

#             # base spec (clone) or lazy_leg
#             spec = copy.deepcopy(leg.spec)
#             spec.position = new_pos
#             if mode == "LAZY_LEG" and isinstance(rule.lazy_leg, dict):
#                 spec = leg_from_dict(rule.lazy_leg)

#             if mode.startswith("RE_ASAP") or mode == "LAZY_LEG":
#                 exp_date = resolve_expiry_keyword(date, spec.expiry)
#                 snap = filter_expiry(chain_at(ts), exp_date)
#                 k = select_strike(snap, spec.option_type.upper(), atm_px_at(ts), spec.strike_criteria)
#                 row = snap[(snap["OptionType"]==spec.option_type.upper()) & (snap["Strike"]==k)]
#                 if row.empty:
#                     return
#                 qty = int(spec.qty_lots) * int(self.cfg.lot_size)
#                 new_leg = LiveLeg(len(live)+1, spec, k, qty)
#                 new_leg.expiry_date = exp_date
#                 new_leg.entry_ts = ts
#                 new_leg.entry_px = float(row["Close"].iloc[0])
#                 new_leg.entry_S  = float(under.loc[ts])
#                 new_leg.best_fav_px = new_leg.entry_px
#                 live.append(new_leg)
#                 if reason == "SL": leg.re_sl_count += 1
#                 else: leg.re_tgt_count += 1
#                 return

#             # COST / MOMENTUM watchers queue
#             pen = PendingReEntry(
#                 parent_leg_id=leg.leg_id,
#                 trigger=reason,
#                 mode=mode,
#                 created_ts=ts,
#                 spec=spec,
#                 watch_strike=(leg.strike if mode.startswith("RE_COST") else None),
#                 watch_price=leg.entry_px,
#             )
#             pending.append(pen)
#             if reason == "SL": leg.re_sl_count += 1
#             else: leg.re_tgt_count += 1

#         live: List[LiveLeg] = []
#         for i, ls in enumerate(self.cfg.legs, 1):
#             exp_date = resolve_expiry_keyword(date, ls.expiry)
#             snap = chain[chain["OptionType"].str.upper() == ls.option_type.upper()].copy()
#             if "Expiry" in snap.columns:
#                 s2 = snap[snap["Expiry"] == exp_date]
#                 if not s2.empty:
#                     snap = s2
#             strike = select_strike(snap, ls.option_type.upper(), atm_px, ls.strike_criteria)
#             qty = int(ls.qty_lots) * int(self.cfg.lot_size)
#             leg = LiveLeg(i, ls, strike, qty)
#             leg.expiry_date = exp_date
#             live.append(leg)

#         for leg in live:
#             s = chain[(chain["OptionType"]==leg.spec.option_type.upper()) & (chain["Strike"]==leg.strike)]
#             if s.empty:
#                 s = chain[chain["OptionType"]==leg.spec.option_type.upper()] \
#                         .iloc[(chain[chain["OptionType"]==leg.spec.option_type.upper()]["Strike"]-leg.strike).abs().argsort()].head(1)
#             leg.entry_ts=e_ts; leg.entry_px=float(s["Close"].iloc[0])
#             leg.entry_S = float(under.loc[e_ts])
#             leg.best_fav_px = leg.entry_px

#         window = opt.loc[(opt.index>=e_ts) & (opt.index<=x_ts)]
#         for ts, _ in window.groupby(level=0):
#             for leg in list(live):
#                 row = opt.loc[(opt.index==ts) & (opt["OptionType"]==leg.spec.option_type.upper()) & (opt["Strike"]==leg.strike)]
#                 if row.empty: continue
#                 px=float(row["Close"].iloc[0])
#                 mult = -1 if leg.spec.position.lower().startswith("sell") else 1
#                 leg.pnl = ((px - leg.entry_px) * mult * -1) * leg.qty

#                 # Maintain best favorable option price (for trailing)
#                 if leg.best_fav_px is None:
#                     leg.best_fav_px = leg.entry_px
#                 if mult == -1:  # short: favorable is price down
#                     leg.best_fav_px = min(leg.best_fav_px, px)
#                 else:           # long: favorable is price up
#                     leg.best_fav_px = max(leg.best_fav_px, px)

#                 # Underlying at this timestamp (nearest if exact not present)
#                 S_ts = float(under.loc[nearest_ts(under, ts)])

#                 rc = _risk_from_any(leg.spec.risk)
#                 # Evaluate exits only if not already closed
#                 if leg.exit_ts is None:
#                     if _hit_target(rc.target, leg.spec.position, leg.entry_px, leg.entry_S, px, S_ts):
#                         leg.hit_target=True; leg.exit_ts=ts; leg.exit_px=px; leg.exit_reason="TARGET"
#                     elif _hit_stop(rc.sl, leg.spec.position, leg.entry_px, leg.entry_S, px, S_ts):
#                         leg.hit_sl=True; leg.exit_ts=ts; leg.exit_px=px; leg.exit_reason="SL"
#                     elif _trail_stop(rc.trail, leg.spec.position, leg.best_fav_px, px):
#                         leg.hit_trail=True; leg.exit_ts=ts; leg.exit_px=px; leg.exit_reason="TRAIL"

#                     if leg.exit_ts is not None and leg.exit_reason in ("SL", "TARGET"):
#                         _spawn_or_queue_reentry(ts, leg, leg.exit_reason)

#             # Evaluate pending re-entries
#             new_pending: List[PendingReEntry] = []
#             for pen in pending:
#                 mode = pen.mode
#                 if mode.startswith("RE_MOMENTUM"):
#                     pts = float(self.cfg.overall_momentum.get("points", 0.0)) if self.cfg.overall_momentum else 0.0
#                     if pts <= 0:
#                         new_pending.append(pen); continue
#                     exp_date = resolve_expiry_keyword(date, pen.spec.expiry)
#                     snap = filter_expiry(chain_at(ts), exp_date)
#                     k = select_strike(snap, pen.spec.option_type.upper(), atm_px_at(ts), pen.spec.strike_criteria)
#                     row = snap[(snap["OptionType"]==pen.spec.option_type.upper()) & (snap["Strike"]==k)]
#                     if row.empty:
#                         new_pending.append(pen); continue
#                     ltp = float(row["Close"].iloc[0])
#                     if ltp >= (pen.watch_price + pts):
#                         qty = int(pen.spec.qty_lots) * int(self.cfg.lot_size)
#                         new_leg = LiveLeg(len(live)+1, pen.spec, k, qty)
#                         new_leg.expiry_date = exp_date
#                         new_leg.entry_ts = ts
#                         new_leg.entry_px = ltp
#                         new_leg.entry_S  = float(under.loc[ts])
#                         new_leg.best_fav_px = ltp
#                         live.append(new_leg)
#                     else:
#                         new_pending.append(pen)
#                     continue

#                 if mode.startswith("RE_COST"):
#                     snap = chain_at(ts)
#                     row = snap[(snap["OptionType"]==pen.spec.option_type.upper()) & (snap["Strike"]==pen.watch_strike)]
#                     if row.empty:
#                         new_pending.append(pen); continue
#                     ltp = float(row["Close"].iloc[0])
#                     ok = (ltp >= pen.watch_price) if pen.spec.position=="Buy" else (ltp <= pen.watch_price)
#                     if ok:
#                         qty = int(pen.spec.qty_lots) * int(self.cfg.lot_size)
#                         new_leg = LiveLeg(len(live)+1, pen.spec, pen.watch_strike, qty)
#                         new_leg.expiry_date = resolve_expiry_keyword(date, pen.spec.expiry)
#                         new_leg.entry_ts = ts
#                         new_leg.entry_px = ltp
#                         new_leg.entry_S  = float(under.loc[ts])
#                         new_leg.best_fav_px = ltp
#                         live.append(new_leg)
#                     else:
#                         new_pending.append(pen)
#                     continue

#                 # Unknown mode -> keep pending
#                 new_pending.append(pen)

#             pending = new_pending

#             if self.cfg.square_off_mode.lower().startswith("complete"):
#                 if any(l.hit_sl or l.hit_target for l in live):
#                     for leg in live:
#                         if leg.exit_ts is None:
#                             row = opt.loc[(opt.index==ts) & (opt["OptionType"]==leg.spec.option_type.upper()) & (opt["Strike"]==leg.strike)]
#                             if not row.empty:
#                                 leg.exit_ts=ts; leg.exit_px=float(row["Close"].iloc[0])
#                                 if leg.exit_reason is None:
#                                     leg.exit_reason = "TIME"
#                     break

#         for leg in live:
#             if leg.exit_ts is None:
#                 xts = nearest_ts(opt, x_ts)
#                 row = opt.loc[(opt.index==xts) & (opt["OptionType"]==leg.spec.option_type.upper()) & (opt["Strike"]==leg.strike)]
#                 if not row.empty: leg.exit_ts=xts; leg.exit_px=float(row["Close"].iloc[0])

#         for leg in live:
#             mult = -1 if leg.spec.position.lower().startswith("sell") else 1
#             pnl_per_unit = (leg.exit_px - leg.entry_px) * mult * -1
#             pnl = pnl_per_unit * leg.qty
#             costs = (self.cfg.costs.get("per_lot_roundtrip",0.0) * (leg.qty/self.cfg.lot_size)) + self.cfg.costs.get("slippage_per_fill",0.0)
#             pnl_net = pnl - costs
#             self.rows.append({
#                 "date": str(date), "index": index_name, "leg_id": leg.leg_id,
#                 "position": leg.spec.position, "option_type": leg.spec.option_type,
#                 "expiry": str(leg.expiry_date), "strike": leg.strike, "qty": leg.qty,
#                 "lotsize": self.cfg.lot_size, "entry_ts": leg.entry_ts, "exit_ts": leg.exit_ts,
#                 "entry_price": leg.entry_px, "exit_price": leg.exit_px,
#                 "pnl": round(pnl,2), "pnl_after_cost": round(pnl_net,2),
#                 "hit:sl": leg.hit_sl, "hit:target": leg.hit_target,
#                 "exit_reason": (leg.exit_reason or ("SL" if leg.hit_sl else ("TARGET" if leg.hit_target else "TIME"))),
#             })

#     def flush(self):
#         if not self.rows:
#             return
#         # Delegate file writing + summaries to reporting.flush_results
#         metrics = flush_results(self.rows, self.out_csv, self.cfg.square_off_mode)
#         # Optional: pretty print a compact summary to the terminal
#         if metrics:
#             print("[SUMMARY]")
#             order = [
#                 "overall_profit", "num_trades", "avg_profit_per_trade",
#                 "avg_loss_on_losers", "avg_profit_on_winners",
#                 "max_profit_single_trade", "max_loss_single_trade",
#                 "win_pct", "loss_pct",
#                 "max_drawdown", "duration_of_max_dd_trades", "duration_of_max_dd_span",
#                 "return_over_maxdd", "reward_to_risk_ratio", "expectancy_ratio",
#                 "max_win_streak", "max_losing_streak", "max_trades_in_any_drawdown",
#             ]
#             for k in order:
#                 if k in metrics:
#                     print(f"  {k}: {metrics[k]}")