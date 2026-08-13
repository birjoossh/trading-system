"""
Accuracy tests for the strategy engine's state machine.

Each test drives `UnifiedStrategyEngine` with a hand-built sequence of ticks and
chain snapshots, so entry timing, exit thresholds, order sides and PnL are all
checked against arithmetic that is written out in the test rather than taken
from a previous run.

Reference strategy (`atm_short_straddle_1100_1515`): sell ATM CE and PE at
11:00, exit 15:15, lot size 75 (1 lot => qty 75), target 30% of premium, stop
25% of premium.
"""

import datetime as dt

import pytest

from unified_trading_platform.trading_core.data_models import OrderAction, OrderType, SecurityType
from unified_trading_platform.trading_core.strategy_engine.config import (
    ReEntryRule,
    RiskConfig,
    RiskRule,
    StrategyConfig,
    TrailRule,
    load_strategy_config,
)
from unified_trading_platform.trading_core.strategy_engine.live_engine import UnifiedStrategyEngine

from helpers import SESSION_DATE, SESSION_EXPIRY, at, make_tick, straddle_chain

ATM = 21600.0
SPOT = 21612.20
CE_ENTRY = 120.0
PE_ENTRY = 80.0
QTY = 75  # 1 lot * lot_size 75


def build_engine(strategy="atm_short_straddle_1100_1515", **overrides) -> UnifiedStrategyEngine:
    config = load_strategy_config(strategy)
    for key, value in overrides.items():
        setattr(config, key, value)
    engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
    engine.initialize(
        current_date=SESSION_DATE, entry_time=config.entry_time, exit_time=config.exit_time
    )
    return engine


def only_risk(target=None, sl=None, trail=None) -> RiskConfig:
    """A RiskConfig with everything disabled except what is passed in."""
    return RiskConfig(
        target=target or RiskRule(enabled=False, basis="premium_pct", value=0.0),
        sl=sl or RiskRule(enabled=False, basis="premium_pct", value=0.0),
        trail=trail or TrailRule(enabled=False, basis="points", value=0.0),
    )


def chain_at(ce=CE_ENTRY, pe=PE_ENTRY):
    return straddle_chain(center=ATM, ce_atm=ce, pe_atm=pe, expiry=SESSION_EXPIRY)


def enter(engine, when="11:00", spot=SPOT, chain=None):
    """Drive the engine through its entry tick and return the signals."""
    return engine.process_tick(make_tick(at(when), spot), spot, chain if chain is not None else chain_at())


class TestEntryTiming:
    def test_no_entry_before_entry_time(self):
        engine = build_engine()
        signals = engine.process_tick(make_tick(at("09:20"), SPOT), SPOT, chain_at())
        assert signals == []
        assert all(leg.entry_ts is None for leg in engine.live_legs)

    def test_no_entry_one_minute_early(self):
        engine = build_engine()
        assert engine.process_tick(make_tick(at("10:59"), SPOT), SPOT, chain_at()) == []

    def test_enters_exactly_at_entry_time(self):
        engine = build_engine()
        signals = enter(engine, "11:00")
        assert len(signals) == 2, "both straddle legs should enter"
        assert all(leg.entry_ts == at("11:00") for leg in engine.live_legs)

    def test_enters_on_first_tick_after_entry_time(self):
        engine = build_engine()
        assert engine.process_tick(make_tick(at("10:59"), SPOT), SPOT, chain_at()) == []
        signals = engine.process_tick(make_tick(at("11:03"), SPOT), SPOT, chain_at())
        assert len(signals) == 2
        assert all(leg.entry_ts == at("11:03") for leg in engine.live_legs)

    def test_does_not_re_enter_on_later_ticks(self):
        engine = build_engine()
        enter(engine, "11:00")
        assert engine.process_tick(make_tick(at("11:05"), SPOT), SPOT, chain_at()) == []

    def test_no_entry_without_a_chain(self):
        engine = build_engine()
        assert engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, None) == []

    def test_no_entry_when_strike_is_missing_from_chain(self):
        """A chain that does not contain the ATM strike must not force an entry."""
        engine = build_engine()
        far_chain = straddle_chain(center=25000.0, expiry=SESSION_EXPIRY)
        engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, far_chain)
        # Whatever strike is chosen must have come from the chain we supplied.
        for leg in engine.live_legs:
            if leg.entry_ts is not None:
                assert leg.strike in set(far_chain["strike"])

    def test_nan_premium_is_treated_as_missing_data(self):
        """A NaN premium must not open a leg — NaN entry prices poison all PnL."""
        engine = build_engine()
        chain = chain_at()
        chain.loc[chain["strike"] == ATM, "price"] = float("nan")
        engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain)

        for leg in engine.live_legs:
            if leg.entry_ts is not None:
                assert leg.entry_px is not None
                assert leg.entry_px == leg.entry_px, "entry price must never be NaN"
                assert leg.strike != ATM, "the NaN-priced strike must be skipped"

    def test_uninitialised_engine_refuses_ticks(self):
        config = load_strategy_config("atm_short_straddle_1100_1515")
        engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
        with pytest.raises(RuntimeError, match="not initialized"):
            engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain_at())


class TestEntryValues:
    def test_selects_the_atm_strike(self):
        engine = build_engine()
        enter(engine)
        assert {leg.strike for leg in engine.live_legs} == {ATM}

    def test_records_the_chain_premium_as_entry_price(self):
        engine = build_engine()
        enter(engine)
        by_type = {leg.spec.option_type: leg for leg in engine.live_legs}
        assert by_type["CE"].entry_px == pytest.approx(CE_ENTRY)
        assert by_type["PE"].entry_px == pytest.approx(PE_ENTRY)

    def test_records_the_underlying_at_entry(self):
        engine = build_engine()
        enter(engine)
        assert all(leg.entry_S == pytest.approx(SPOT) for leg in engine.live_legs)

    def test_quantity_is_lots_times_lot_size(self):
        engine = build_engine()
        enter(engine)
        assert all(leg.qty == QTY for leg in engine.live_legs)

    def test_expiry_resolves_to_the_weekly_contract(self):
        engine = build_engine()
        enter(engine)
        assert all(leg.expiry_date == SESSION_EXPIRY for leg in engine.live_legs)

    def test_best_favourable_price_starts_at_entry(self):
        engine = build_engine()
        enter(engine)
        assert all(leg.best_fav_px == leg.entry_px for leg in engine.live_legs)


class TestOrderSignals:
    def test_short_legs_open_with_sell_orders(self):
        engine = build_engine()
        signals = enter(engine)
        assert all(s.action == OrderAction.SELL for s in signals)
        assert all(s.is_exit is False for s in signals)

    def test_long_legs_open_with_buy_orders(self):
        engine = build_engine()
        for leg in engine.live_legs:
            leg.spec.position = "Buy"
        signals = enter(engine)
        assert all(s.action == OrderAction.BUY for s in signals)

    def test_closing_a_short_leg_buys_it_back(self):
        """The single most dangerous mistake would be exiting on the same side."""
        engine = build_engine()
        enter(engine)
        leg = engine.live_legs[0]
        assert leg.spec.position.lower().startswith("sell")

        signal = engine.generate_signal_for_leg(leg, closing=True)
        assert signal.action == OrderAction.BUY
        assert signal.is_exit is True

    def test_closing_a_long_leg_sells_it(self):
        engine = build_engine()
        for leg in engine.live_legs:
            leg.spec.position = "Buy"
        enter(engine)
        signal = engine.generate_signal_for_leg(engine.live_legs[0], closing=True)
        assert signal.action == OrderAction.SELL
        assert signal.is_exit is True

    def test_signal_contract_describes_the_option(self):
        engine = build_engine()
        signals = enter(engine)
        signal = signals[0]
        contract = signal.contract
        assert contract.security_type == SecurityType.OPTION
        assert contract.strike == ATM
        assert contract.exchange == "NSE"
        assert contract.currency == "INR"
        assert contract.expiry == SESSION_EXPIRY.strftime("%Y%m%d")
        assert contract.multiplier == "75"
        assert signal.quantity == QTY
        assert signal.order_type == OrderType.MARKET

    def test_signal_carries_its_leg_id(self):
        engine = build_engine()
        signals = enter(engine)
        assert {s.leg_id for s in signals} == {leg.leg_id for leg in engine.live_legs}


class TestExitConditions:
    """Each rule is isolated so a triggered exit can only have one cause."""

    def _short_ce_engine(self, risk):
        engine = build_engine()
        engine.live_legs = [engine.live_legs[0]]  # CE only
        engine.live_legs[0].spec.risk = risk
        engine.live_legs[0].spec.reentry_on_sl = ReEntryRule(enabled=False)
        engine.live_legs[0].spec.reentry_on_target = ReEntryRule(enabled=False)
        enter(engine)
        return engine

    def test_target_fires_exactly_at_the_threshold(self):
        """30% of a 120 premium means exiting at 84.00."""
        risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
        engine = self._short_ce_engine(risk)

        just_above = engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=84.5))
        assert just_above == [], "84.5 is only a 29.6% gain; must not exit"

        at_threshold = engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=84.0))
        assert len(at_threshold) == 1
        assert engine.live_legs[0].exit_reason == "TARGET"
        assert engine.live_legs[0].hit_target is True

    def test_stop_fires_exactly_at_the_threshold(self):
        """25% adverse move on a 120 premium means stopping out at 150.00."""
        risk = only_risk(sl=RiskRule(enabled=True, basis="premium_pct", value=25))
        engine = self._short_ce_engine(risk)

        assert engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=149.5)) == []
        signals = engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=150.0))
        assert len(signals) == 1
        assert engine.live_legs[0].exit_reason == "SL"
        assert engine.live_legs[0].hit_sl is True

    def test_target_on_premium_points(self):
        risk = only_risk(target=RiskRule(enabled=True, basis="premium_pts", value=20))
        engine = self._short_ce_engine(risk)
        assert engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=100.5)) == []
        assert len(engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=100.0))) == 1
        assert engine.live_legs[0].exit_reason == "TARGET"

    def test_stop_on_underlying_points(self):
        """A short call is hurt by the index rising: stop at entry + 50 points."""
        risk = only_risk(sl=RiskRule(enabled=True, basis="underlying_pts", value=50))
        engine = self._short_ce_engine(risk)
        assert engine.process_tick(make_tick(at("12:00"), SPOT + 49), SPOT + 49, chain_at()) == []
        signals = engine.process_tick(make_tick(at("12:01"), SPOT + 50), SPOT + 50, chain_at())
        assert len(signals) == 1
        assert engine.live_legs[0].exit_reason == "SL"

    def test_trailing_stop_on_points(self):
        """Premium falls to 100 (best), then a 10-point retrace exits."""
        risk = only_risk(trail=TrailRule(enabled=True, basis="points", value=10))
        engine = self._short_ce_engine(risk)

        assert engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=100.0)) == []
        assert engine.live_legs[0].best_fav_px == pytest.approx(100.0)

        assert engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=109.5)) == []
        signals = engine.process_tick(make_tick(at("12:02"), SPOT), SPOT, chain_at(ce=110.0))
        assert len(signals) == 1
        assert engine.live_legs[0].exit_reason == "TRAIL"
        assert engine.live_legs[0].hit_trail is True

    def test_end_of_day_exit(self):
        engine = self._short_ce_engine(only_risk())
        assert engine.process_tick(make_tick(at("15:14"), SPOT), SPOT, chain_at()) == []
        signals = engine.process_tick(make_tick(at("15:15"), SPOT), SPOT, chain_at())
        assert len(signals) == 1
        assert engine.live_legs[0].exit_reason == "EOD"

    def test_end_of_day_exit_is_not_recorded_as_a_target_hit(self):
        """Exit-reason statistics are worthless if EOD counts as a win."""
        engine = self._short_ce_engine(only_risk())
        engine.process_tick(make_tick(at("15:15"), SPOT), SPOT, chain_at())
        leg = engine.live_legs[0]
        assert leg.exit_reason == "EOD"
        assert leg.hit_target is False, "EOD is not a target hit"
        assert leg.hit_sl is False

    def test_a_leg_exits_only_once(self):
        risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
        engine = self._short_ce_engine(risk)
        first = engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=80.0))
        assert len(first) == 1
        second = engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=70.0))
        assert second == [], "an exited leg must not exit again"

    def test_exit_timestamp_and_price_are_recorded(self):
        risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
        engine = self._short_ce_engine(risk)
        engine.process_tick(make_tick(at("12:34"), SPOT), SPOT, chain_at(ce=80.0))
        leg = engine.live_legs[0]
        assert leg.exit_ts == at("12:34")
        assert leg.exit_px == pytest.approx(80.0)

    def test_missing_premium_defers_the_exit_decision(self):
        """No price means no information — the leg must stay open, not guess."""
        risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
        engine = self._short_ce_engine(risk)
        empty = chain_at().iloc[0:0]
        assert engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, empty) == []
        assert engine.live_legs[0].exit_ts is None

    def test_disabled_rules_never_fire(self):
        engine = self._short_ce_engine(only_risk())
        for premium in (1.0, 500.0, 0.5):
            assert engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=premium)) == []
        assert engine.live_legs[0].exit_ts is None


class TestProfitAndLoss:
    def _run(self, position, entry_premium, exit_premium):
        engine = build_engine()
        engine.live_legs = [engine.live_legs[0]]
        leg = engine.live_legs[0]
        leg.spec.position = position
        leg.spec.risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
        leg.spec.reentry_on_sl = ReEntryRule(enabled=False)
        leg.spec.reentry_on_target = ReEntryRule(enabled=False)

        enter(engine, chain=chain_at(ce=entry_premium))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=exit_premium))
        return engine, leg

    def test_short_gains_when_premium_falls(self):
        engine, leg = self._run("Sell", 120.0, 80.0)
        assert leg.pnl == pytest.approx((80.0 - 120.0) * -1 * QTY)
        assert leg.pnl == pytest.approx(3000.0)

    def test_short_loses_when_premium_rises(self):
        engine, leg = self._run("Sell", 120.0, 150.0)
        assert leg.pnl == pytest.approx((150.0 - 120.0) * -1 * QTY)
        assert leg.pnl == pytest.approx(-2250.0)

    def test_long_gains_when_premium_rises(self):
        engine, leg = self._run("Buy", 120.0, 150.0)
        assert leg.pnl == pytest.approx((150.0 - 120.0) * 1 * QTY)
        assert leg.pnl == pytest.approx(2250.0)

    def test_long_loses_when_premium_falls(self):
        engine, leg = self._run("Buy", 120.0, 80.0)
        assert leg.pnl == pytest.approx(-3000.0)

    def test_recorded_rows_agree_with_the_pnl_formula(self):
        engine, leg = self._run("Sell", 120.0, 80.0)
        assert engine.rows
        for row in engine.rows:
            mult = -1 if row["position"].lower().startswith("sell") else 1
            expected = (row["exit_price"] - row["entry_price"]) * mult * row["qty"]
            assert row["pnl"] == pytest.approx(round(expected, 2))

    def test_rows_capture_leg_identity(self):
        engine, leg = self._run("Sell", 120.0, 80.0)
        row = engine.rows[-1]
        assert row["leg_id"] == leg.leg_id
        assert row["strike"] == leg.strike
        assert row["qty"] == QTY
        assert row["expiry"] == str(SESSION_EXPIRY)

    def test_no_rows_before_entry(self):
        engine = build_engine()
        engine.process_tick(make_tick(at("09:30"), SPOT), SPOT, chain_at())
        assert engine.rows == []

    def test_closed_leg_keeps_reporting_its_exit_price(self):
        engine, leg = self._run("Sell", 120.0, 80.0)
        engine.process_tick(make_tick(at("13:00"), SPOT), SPOT, chain_at(ce=200.0))
        last = engine.rows[-1]
        assert last["exit_price"] == pytest.approx(80.0), "a closed leg must not re-mark to market"

    def test_portfolio_summary_counts(self):
        engine = build_engine()
        enter(engine)
        summary = engine.get_portfolio_summary()
        assert summary["total_positions"] == 2
        assert summary["open_positions"] == 2
        assert summary["closed_positions"] == 0

        engine.process_tick(make_tick(at("15:15"), SPOT), SPOT, chain_at())
        summary = engine.get_portfolio_summary()
        assert summary["open_positions"] == 0
        assert summary["closed_positions"] == 2

    def test_summary_total_is_the_sum_of_leg_pnl(self):
        engine = build_engine()
        enter(engine)
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=100.0, pe=60.0))
        expected = sum(leg.pnl for leg in engine.live_legs if leg.entry_ts is not None)
        assert engine.get_portfolio_summary()["total_pnl"] == pytest.approx(expected)


class TestFillReconciliation:
    """Broker fills refine the simulated bookkeeping; they must not destroy it."""

    def _entered(self):
        engine = build_engine()
        enter(engine)
        return engine, engine.live_legs[0]

    def test_real_fill_price_replaces_the_simulated_one(self):
        engine, leg = self._entered()
        engine.update_position_on_fill(
            leg.leg_id,
            {
                "action": "entry",
                "price": 118.4,
                "underlying_price": 21610.0,
                "timestamp": "2024-01-02T11:00:01",
            },
        )
        assert leg.entry_px == pytest.approx(118.4)
        assert leg.entry_S == pytest.approx(21610.0)

    def test_empty_fill_price_does_not_erase_the_entry(self):
        engine, leg = self._entered()
        original_px, original_ts = leg.entry_px, leg.entry_ts
        engine.update_position_on_fill(leg.leg_id, {"action": "entry", "price": 0.0, "underlying_price": 0.0})
        assert leg.entry_px == pytest.approx(original_px)
        assert leg.entry_ts == original_ts

    def test_missing_fill_price_does_not_erase_the_entry(self):
        engine, leg = self._entered()
        original_px = leg.entry_px
        engine.update_position_on_fill(leg.leg_id, {"action": "entry"})
        assert leg.entry_px == pytest.approx(original_px)

    def test_simulated_entry_timestamp_is_preserved(self):
        """Backtests must not stamp wall-clock time onto historical entries."""
        engine, leg = self._entered()
        engine.update_position_on_fill(
            leg.leg_id, {"action": "entry", "price": 118.4, "timestamp": dt.datetime.now().isoformat()}
        )
        assert leg.entry_ts == at("11:00")

    def test_exit_fill_updates_exit_price(self):
        engine, leg = self._entered()
        engine.process_tick(make_tick(at("15:15"), SPOT), SPOT, chain_at())
        engine.update_position_on_fill(leg.leg_id, {"action": "exit", "price": 79.5})
        assert leg.exit_px == pytest.approx(79.5)

    def test_fill_for_unknown_leg_is_ignored(self):
        engine, _ = self._entered()
        engine.update_position_on_fill(999, {"action": "entry", "price": 1.0})


class TestReEntries:
    def _engine_with_reentry(self, rule, reason="sl"):
        engine = build_engine()
        engine.live_legs = [engine.live_legs[0]]
        leg = engine.live_legs[0]
        if reason == "sl":
            leg.spec.risk = only_risk(sl=RiskRule(enabled=True, basis="premium_pct", value=25))
            leg.spec.reentry_on_sl = rule
            leg.spec.reentry_on_target = ReEntryRule(enabled=False)
        else:
            leg.spec.risk = only_risk(target=RiskRule(enabled=True, basis="premium_pct", value=30))
            leg.spec.reentry_on_target = rule
            leg.spec.reentry_on_sl = ReEntryRule(enabled=False)
        enter(engine)
        return engine

    def test_re_asap_opens_a_replacement_leg_on_the_same_tick(self):
        """RE_ASAP means exactly that: the stop and the replacement share a tick."""
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP", max_count=1))
        signals = engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))

        assert len(signals) == 2, "one exit for the stopped leg, one entry for the replacement"
        exits = [s for s in signals if s.is_exit]
        entries = [s for s in signals if not s.is_exit]
        assert len(exits) == 1 and len(entries) == 1

        assert len(engine.live_legs) == 2
        assert engine.pending_reentries == []

        replacement = engine.live_legs[-1]
        assert replacement.parent_leg_id == 1
        assert replacement.entry_ts == at("12:00")
        assert replacement.entry_px == pytest.approx(150.0)

    def test_replacement_leg_is_independent_of_its_parent(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP", max_count=1))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        parent, replacement = engine.live_legs
        assert parent.exit_ts is not None, "the stopped leg stays closed"
        assert replacement.exit_ts is None, "the replacement is open"
        assert replacement.leg_id != parent.leg_id

    def test_disabled_reentry_spawns_nothing(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=False, mode="RE_ASAP", max_count=1))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        assert engine.pending_reentries == []
        assert len(engine.live_legs) == 1

    def test_max_count_zero_spawns_nothing(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP", max_count=0))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        assert engine.pending_reentries == []

    def test_reversed_mode_flips_the_position(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP_REV", max_count=1))
        signals = engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))

        assert engine.live_legs[-1].spec.position == "Buy", "a reversed re-entry flips short to long"
        entry_signal = next(s for s in signals if not s.is_exit)
        assert entry_signal.action == OrderAction.BUY

    def test_reversal_does_not_mutate_the_parent_leg(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP_REV", max_count=1))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        assert engine.live_legs[0].spec.position == "Sell"

    def test_no_reentry_after_cutoff(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP", max_count=1))
        engine.config.no_reentry_after = "11:30"
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        assert engine.pending_reentries == [], "past the cutoff, no re-entry may be queued"

    def test_cost_based_reentry_waits_for_the_price(self):
        """RE_COST re-enters only once the underlying comes back to the watch price."""
        engine = self._engine_with_reentry(
            ReEntryRule(enabled=True, mode="RE_COST", max_count=1), reason="target"
        )
        entry_premium = engine.live_legs[0].entry_px
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=80.0))  # target hit
        assert len(engine.pending_reentries) == 1
        assert engine.pending_reentries[0].watch_price == pytest.approx(entry_premium)

        # Underlying above the watch price: a short leg must not re-enter yet.
        signals = engine.process_tick(make_tick(at("12:01"), 30000.0), 30000.0, chain_at(ce=80.0))
        assert signals == []
        assert len(engine.pending_reentries) == 1, "untriggered re-entries must stay queued"

    def test_pending_reentry_survives_a_priceless_tick(self):
        """A gap in the chain must not silently discard a queued re-entry."""
        engine = self._engine_with_reentry(
            ReEntryRule(enabled=True, mode="RE_COST", max_count=1), reason="target"
        )
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=80.0))
        assert len(engine.pending_reentries) == 1

        empty = chain_at().iloc[0:0]
        engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, empty)
        assert len(engine.pending_reentries) == 1, "a chain gap must not drop the re-entry"

    def test_reentry_is_skipped_when_the_new_strike_has_no_premium(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_ASAP", max_count=1))
        chain = chain_at(ce=150.0)
        # Stop the leg out, but blank the premium the replacement would need.
        chain.loc[(chain["strike"] == ATM) & (chain["option_type"] == "CE"), "price"] = 150.0
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain)
        for leg in engine.live_legs:
            assert leg.entry_px is None or leg.entry_px == leg.entry_px, "no NaN entry prices"

    def test_unknown_mode_is_dropped_not_retried_forever(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="NOT_A_MODE", max_count=1))
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=150.0))
        engine.process_tick(make_tick(at("12:01"), SPOT), SPOT, chain_at(ce=150.0))
        assert engine.pending_reentries == []

    def test_summary_reports_pending_reentries(self):
        engine = self._engine_with_reentry(ReEntryRule(enabled=True, mode="RE_COST", max_count=1), reason="target")
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, chain_at(ce=80.0))
        assert engine.get_portfolio_summary()["pending_reentries"] == 1


class TestExitTimeHelper:
    def test_should_exit_compares_against_exit_time(self):
        engine = build_engine()
        assert engine.should_exit(dt.time(15, 15)) is True
        assert engine.should_exit(dt.time(15, 30)) is True
        assert engine.should_exit(dt.time(15, 14)) is False


class TestStrategyConfigValidation:
    def test_symbol_is_required(self):
        with pytest.raises(ValueError, match="symbol"):
            StrategyConfig(currency="INR")

    def test_currency_is_required(self):
        with pytest.raises(ValueError, match="currency"):
            StrategyConfig(symbol="NIFTY 50")

    def test_valid_config_constructs(self):
        config = StrategyConfig(symbol="NIFTY 50", currency="INR")
        assert config.entry_time and config.exit_time

    def test_bundled_strategies_all_load(self):
        """Every shipped strategy JSON must satisfy its own schema."""
        from pathlib import Path

        directory = Path("unified_trading_platform/trading_core/strategies")
        names = sorted(p.stem for p in directory.glob("*.json"))
        assert names, "no strategy configs found"
        for name in names:
            config = load_strategy_config(name)
            assert config.symbol and config.currency
            assert config.legs, f"{name} has no legs"
            for leg in config.legs:
                assert leg.option_type.upper() in {"CE", "PE"}
                assert leg.position.lower() in {"buy", "sell"}
                assert leg.qty_lots >= 1

    def test_unknown_strategy_raises(self):
        with pytest.raises(FileNotFoundError):
            load_strategy_config("no_such_strategy")
