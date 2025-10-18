from __future__ import annotations
import dataclasses as dc
from typing import Dict, List, Optional
import json
from pathlib import Path

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

def load_strategy_config(strategy_name: str, strategies_dir: str = None) -> StrategyConfig:
    """Load strategy configuration from JSON file"""
    if strategies_dir is None:
        # Default to the strategies directory relative to this file
        current_dir = Path(__file__).parent
        strategies_dir = current_dir.parent / "strategies"
    
    strategy_path = Path(strategies_dir) / f"{strategy_name}.json"
    
    if not strategy_path.exists():
        raise FileNotFoundError(f"Strategy file not found: {strategy_path}")
    
    with open(strategy_path, 'r') as f:
        config_dict = json.load(f)
    
    # Convert legs to LegSpec objects
    legs = []
    for leg_dict in config_dict.get('legs', []):
        # Convert strike_criteria
        sc_dict = leg_dict.get('strike_criteria', {})
        strike_criteria = StrikeCriteria(
            mode=sc_dict.get('mode', 'STRIKE_TYPE'),
            params=sc_dict.get('params', {})
        )
        
        # Convert risk config
        risk_dict = leg_dict.get('risk', {})
        target_dict = risk_dict.get('target', {})
        sl_dict = risk_dict.get('sl', {})
        trail_dict = risk_dict.get('trail', {})
        
        target = RiskRule(
            enabled=target_dict.get('enabled', True),
            basis=target_dict.get('basis', 'premium_pct'),
            value=target_dict.get('value', 0.0)
        )
        
        sl = RiskRule(
            enabled=sl_dict.get('enabled', True),
            basis=sl_dict.get('basis', 'premium_pct'),
            value=sl_dict.get('value', 0.0)
        )
        
        trail = TrailRule(
            enabled=trail_dict.get('enabled', False),
            basis=trail_dict.get('basis', 'points'),
            value=trail_dict.get('value', 0.0)
        )
        
        risk_config = RiskConfig(target=target, sl=sl, trail=trail)
        
        # Convert reentry rules
        reentry_sl_dict = leg_dict.get('reentry_on_sl', {})
        reentry_target_dict = leg_dict.get('reentry_on_target', {})
        
        reentry_sl = ReEntryRule(
            enabled=reentry_sl_dict.get('enabled', False),
            mode=reentry_sl_dict.get('mode', 'RE_ASAP'),
            max_count=reentry_sl_dict.get('max_count', 0),
            lazy_leg=reentry_sl_dict.get('lazy_leg')
        )
        
        reentry_target = ReEntryRule(
            enabled=reentry_target_dict.get('enabled', False),
            mode=reentry_target_dict.get('mode', 'RE_ASAP'),
            max_count=reentry_target_dict.get('max_count', 0),
            lazy_leg=reentry_target_dict.get('lazy_leg')
        )
        
        leg_spec = LegSpec(
            segment=leg_dict.get('segment', 'Options'),
            position=leg_dict.get('position', 'Sell'),
            option_type=leg_dict.get('option_type', 'CE'),
            expiry=leg_dict.get('expiry', 'Weekly'),
            qty_lots=leg_dict.get('qty_lots', 1),
            strike_criteria=strike_criteria,
            risk=risk_config,
            reentry_on_sl=reentry_sl,
            reentry_on_target=reentry_target
        )
        legs.append(leg_spec)
    
    # Convert trail_to_be
    trail_to_be_dict = config_dict.get('trail_to_be', {})
    trail_to_be = TrailToBE(
        enabled=trail_to_be_dict.get('enabled', False),
        scope=trail_to_be_dict.get('scope', 'All'),
        trigger=trail_to_be_dict.get('trigger', {"mode": "percent", "value": 30})
    )
    
    return StrategyConfig(
        strategy_type=config_dict.get('strategy_type', 'Intraday'),
        underlying_from=config_dict.get('underlying_from', 'Cash'),
        entry_time=config_dict.get('entry_time', '11:00'),
        exit_time=config_dict.get('exit_time', '15:15'),
        no_reentry_after=config_dict.get('no_reentry_after'),
        overall_momentum=config_dict.get('overall_momentum'),
        square_off_mode=config_dict.get('square_off_mode', 'Partial'),
        trail_to_be=trail_to_be,
        lot_size=config_dict.get('lot_size', 50),
        legs=legs,
        costs=config_dict.get('costs', {"per_lot_roundtrip": 0.0, "slippage_per_fill": 0.0})
    )