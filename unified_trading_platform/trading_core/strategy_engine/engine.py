from __future__ import annotations
import datetime as dt
from dataclasses import dataclass
import pandas as pd

from unified_trading_platform.trading_core.data_models import TickData
from unified_trading_platform.trading_core.utils import get_logger

from .config import LegSpec, RiskConfig, RiskRule, TrailRule, ReEntryRule

logger = get_logger(__name__)


def weekly_expiry_for(date: dt.date) -> dt.date:
    switch = dt.date(2025, 9, 1)
    wd = 1 if date >= switch else 3  # Tue else Thu
    d = date
    while d.weekday() != wd:
        d += dt.timedelta(days=1)
    return d


def monthly_expiry_for(date: dt.date) -> dt.date:
    switch = dt.date(2025, 9, 1)
    wd = 1 if date >= switch else 3
    y, m = date.year, date.month
    nxt = dt.date(y + 1, 1, 1) if m == 12 else dt.date(y, m + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() != wd:
        d -= dt.timedelta(days=1)
    return d


def next_weekly_expiry_for(date: dt.date) -> dt.date:
    this = weekly_expiry_for(date)
    nxt = weekly_expiry_for(this + dt.timedelta(days=1))
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
    "RE_ASAP",
    "RE_ASAP_REV",
    "RE_COST",
    "RE_COST_REV",
    "RE_MOMENTUM",
    "RE_MOMENTUM_REV",
    "LAZY_LEG",
}


def _reverse_position(pos: str) -> str:
    return "Buy" if str(pos).lower().startswith("sell") else "Sell"


@dataclass
class PendingReEntry:
    parent_leg_id: int
    trigger: str  # "SL" or "TARGET"
    mode: str
    created_ts: pd.Timestamp
    spec: LegSpec
    watch_strike: float | None = None  # for RE_COST
    watch_price: float | None = None  # for RE_COST / RE_MOMENTUM


# ---- coercion helpers (accept dicts or dataclasses) ----
def _risk_from_any(obj):
    if isinstance(obj, RiskConfig):
        return obj
    if isinstance(obj, dict):
        t = obj.get("target", {})
        s = obj.get("sl", {})
        tr = obj.get("trail", {})

        def rr(d, default_basis="premium_pct"):
            if not isinstance(d, dict):
                return RiskRule(enabled=False, basis=default_basis, value=0.0)
            return RiskRule(
                enabled=bool(d.get("enabled", True)),
                basis=str(d.get("basis", default_basis)),
                value=float(d.get("value", 0.0)),
            )

        trail = TrailRule(
            enabled=bool(tr.get("enabled", False)),
            basis=str(tr.get("basis", "points")),
            value=float(tr.get("value", 0.0)),
        )
        return RiskConfig(target=rr(t), sl=rr(s), trail=trail)
    # default empty (all disabled)
    return RiskConfig()


def _reentry_from_any(obj):
    if isinstance(obj, ReEntryRule):
        return obj
    if isinstance(obj, dict):
        return ReEntryRule(
            enabled=bool(obj.get("enabled", False)),
            mode=str(obj.get("mode", "RE_ASAP")).upper(),
            max_count=int(obj.get("max_count", 0)),
            lazy_leg=obj.get("lazy_leg"),
        )
    return ReEntryRule()


@dataclass
class LiveLeg:
    def __init__(self, leg_id: int, spec: LegSpec, strike: float, qty: int):
        self.leg_id = leg_id
        self.spec = spec
        self.strike = strike
        self.qty = qty
        self.entry_ts = self.exit_ts = None  ## entry/exit timestamps
        self.entry_px = self.exit_px = None  ## entry/exit prices
        self.entry_S = None  ## entry underlying price
        self.best_fav_px = None  ## best favorite price
        self.pnl = 0.0  ## profit/loss
        self.hit_sl = False  ## hit stop loss
        self.hit_target = False  ## hit target
        self.hit_trail = False  ## hit trail
        self.exit_reason = None  ## exit reason
        self.reentry_id = 0  ## re-entry id
        self.expiry_date = None  ## expiry date
        # re-entry counters
        self.re_sl_count = 0  ## re-entry stop loss count
        self.re_tgt_count = 0  ## re-entry target count

    # def __str__(self):
    #     return (
    #         f"LiveLeg(id={self.leg_id}, "
    #         f"{self.spec.position} {self.spec.option_type} @ {self.strike}, "
    #         f"Qty: {self.qty}, "
    #         f"Entry S: {self.entry_S if self.entry_S is not None else 'None'}, "
    #         f"Entry: {self.entry_px if self.entry_px is not None else 'None'}, "
    #         f"Exit: {self.exit_px if self.exit_px is not None else 'None'}, "
    #         f"Entry TS: {self.entry_ts if self.entry_ts is not None else 'None'}, "
    #         f"Exit TS: {self.exit_ts if self.exit_ts is not None else 'None'}, "
    #         f"Expiry Date: {self.expiry_date if self.expiry_date is not None else 'None'}, "
    #         f"Hit SL: {self.hit_sl}, "
    #         f"Hit Target: {self.hit_target}, "
    #         f"Hit Trail: {self.hit_trail}, "
    #         f"Best Fav PX: {self.best_fav_px if self.best_fav_px is not None else 'None'}, "
    #         f"Re-entry ID: {self.reentry_id}, "
    #         f"Re-entry SL Count: {self.re_sl_count}, "
    #         f"Re-entry TGT Count: {self.re_tgt_count}, "
    #         f"PnL: {self.pnl:.2f}, "
    #         f"Status: {'Open' if self.entry_ts and not self.exit_ts else 'Closed' if self.exit_ts else 'Pending'}, "
    #         f"Exit Reason: {self.exit_reason or 'N/A'})"
    #         f"Spec: {self.spec}")

    # def __repr__(self):
    #     return self.__str__()


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
        ret = ((entry_px - ltp) / ref) if short else ((ltp - entry_px) / ref)
        return ret >= v / 100.0
    if b == "underlying_pts":
        move_up = S - entry_S
        return (move_up <= -v) if short else (move_up >= v)
    if b == "underlying_pct":
        refS = entry_S if entry_S else 1.0
        ret_up = (S - entry_S) / refS
        return (ret_up <= -v / 100.0) if short else (ret_up >= v / 100.0)
    return False


def _hist_eod_ts(tick_data: TickData, exit_time: str):
    logger.debug("tick_data.timestamp.time() = %s", tick_data.timestamp.time())
    logger.debug("exit_time = %s", exit_time)
    if tick_data.timestamp.time() >= dt.time.fromisoformat(exit_time):
        return True
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
        loss = ((ltp - entry_px) / ref) if short else ((entry_px - ltp) / ref)
        return loss >= v / 100.0
    if b == "underlying_pts":
        move_up = S - entry_S
        return (move_up >= v) if short else (move_up <= -v)
    if b == "underlying_pct":
        refS = entry_S if entry_S else 1.0
        ret_up = (S - entry_S) / refS
        return (ret_up >= v / 100.0) if short else (ret_up <= -v / 100.0)
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
        stop = (best_fav_px * (1 + val / 100.0)) if short else (best_fav_px * (1 - val / 100.0))
        return ltp >= stop if short else ltp <= stop
    return False
