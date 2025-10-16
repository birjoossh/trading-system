from __future__ import annotations
import dataclasses as dc
from typing import Dict, List, Optional

# ---------------------------
# Strike selection spec
# ---------------------------
@dc.dataclass
class StrikeCriteria:
    mode: str
    params: Dict

# ---------------------------
# Risk / Exit specs (per-leg)
# ---------------------------
@dc.dataclass
class RiskRule:
    """Generic rule for Target / Stop-Loss.

    basis options:
      - "premium_pts"    : compare option LTP vs entry (points)
      - "premium_pct"    : compare option LTP vs entry (percent)
      - "underlying_pts" : compare underlying vs entry (points)
      - "underlying_pct" : compare underlying vs entry (percent)
    """
    enabled: bool = True
    basis: str = "premium_pct"
    value: float = 0.0

@dc.dataclass
class TrailRule:
    """Trailing stop on option premium.

    basis options: "points" | "percent"
    """
    enabled: bool = False
    basis: str = "points"
    value: float = 0.0

@dc.dataclass
class RiskConfig:
    """Container for all leg-level exits."""
    target: RiskRule = dc.field(
        default_factory=lambda: RiskRule(enabled=True, basis="premium_pct", value=25.0)
    )
    sl: RiskRule = dc.field(
        default_factory=lambda: RiskRule(enabled=True, basis="premium_pct", value=20.0)
    )
    trail: TrailRule = dc.field(default_factory=TrailRule)

@dc.dataclass
class ReEntryRule:
    enabled: bool = False
    mode: str = "RE_ASAP"       # RE_ASAP | RE_ASAP_REV | RE_COST | RE_COST_REV | RE_MOMENTUM | RE_MOMENTUM_REV | LAZY_LEG
    max_count: int = 0           # capped at 20 in engine
    lazy_leg: Optional[Dict] = None  # only for LAZY_LEG: mini leg-spec dict

# ---------------------------
# Leg / Strategy specs
# ---------------------------
@dc.dataclass
class LegSpec:
    segment: str
    position: str            # "Sell" | "Buy"
    option_type: str         # "CE" | "PE"
    # Expiry keyword chosen per leg in UI/JSON:
    #   "Weekly" | "NextWeekly" | "Monthly" | "NextMonthly"
    expiry: str
    qty_lots: int
    strike_criteria: StrikeCriteria
    # New structured risk config (backward compatible in engine by accepting dict too)
    risk: RiskConfig = dc.field(default_factory=RiskConfig)
    reentry_on_sl: ReEntryRule = dc.field(default_factory=ReEntryRule)
    reentry_on_target: ReEntryRule = dc.field(default_factory=ReEntryRule)

@dc.dataclass
class TrailToBE:
    enabled: bool = False
    scope: str = "All"
    trigger: Dict = dc.field(default_factory=lambda: {"mode": "percent", "value": 30})

@dc.dataclass
class StrategyConfig:
    strategy_type: str = "Intraday"
    underlying_from: str = "Cash"
    entry_time: str = "11:00"
    exit_time: str = "15:15"
    no_reentry_after: Optional[str] = None
    overall_momentum: Optional[Dict] = None
    square_off_mode: str = "Partial"
    trail_to_be: TrailToBE = dc.field(default_factory=TrailToBE)
    lot_size: int = 50
    legs: List[LegSpec] = dc.field(default_factory=list)
    costs: Dict = dc.field(default_factory=lambda: {"per_lot_roundtrip": 0.0, "slippage_per_fill": 0.0})