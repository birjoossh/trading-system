from __future__ import annotations
from dataclasses import dataclass
import math

def _is_short(position: str) -> bool:
    return str(position).lower().startswith("sell")

def hit_target(rule, position: str, entry_px: float, entry_S: float, ltp: float, S: float) -> bool:
    if not rule or not rule.enabled: 
        return False
    b = rule.basis
    v = float(rule.value)
    short = _is_short(position)
    if b == "premium_pts":
        move = (entry_px - ltp) if short else (ltp - entry_px)
        return move >= v
    if b == "premium_pct":
        ref = entry_px if entry_px != 0 else 1.0
        ret = ((entry_px - ltp)/ref) if short else ((ltp - entry_px)/ref)
        return ret >= v/100.0
    if b == "underlying_pts":
        # Favorable dir: Short CE -> S down ; Short PE -> S up ; Long CE -> S up ; Long PE -> S down
        # Caller should pass option_type if you want per-type nuance; a simple heuristic:
        move_up = (S - entry_S)  # positive if underlying up
        return (move_up <= -v) if short else (move_up >= v)
    if b == "underlying_pct":
        refS = entry_S if entry_S != 0 else 1.0
        ret_up = (S - entry_S)/refS
        return (ret_up <= -v/100.0) if short else (ret_up >= v/100.0)
    return False

def hit_stop(rule, position: str, entry_px: float, entry_S: float, ltp: float, S: float) -> bool:
    if not rule or not rule.enabled:
        return False
    b = rule.basis
    v = float(rule.value)
    short = _is_short(position)
    if b == "premium_pts":
        loss = (ltp - entry_px) if short else (entry_px - ltp)
        return loss >= v
    if b == "premium_pct":
        ref = entry_px if entry_px != 0 else 1.0
        loss = ((ltp - entry_px)/ref) if short else ((entry_px - ltp)/ref)
        return loss >= v/100.0
    if b == "underlying_pts":
        move_up = (S - entry_S)
        return (move_up >= v) if short else (move_up <= -v)
    if b == "underlying_pct":
        refS = entry_S if entry_S != 0 else 1.0
        ret_up = (S - entry_S)/refS
        return (ret_up >= v/100.0) if short else (ret_up <= -v/100.0)
    return False

def trail_stop(trail_rule, position: str, best_fav_px: float, ltp: float) -> bool:
    # trailing on option premium only
    if not trail_rule or not trail_rule.enabled:
        return False
    short = _is_short(position)
    if trail_rule.basis == "points":
        if short:
            stop = best_fav_px + trail_rule.value  # best_fav_px is lowest seen
            return ltp >= stop
        else:
            stop = best_fav_px - trail_rule.value  # best_fav_px is highest seen
            return ltp <= stop
    if trail_rule.basis == "percent":
        if short:
            stop = best_fav_px * (1 + trail_rule.value/100.0)
            return ltp >= stop
        else:
            stop = best_fav_px * (1 - trail_rule.value/100.0)
            return ltp <= stop
    return False