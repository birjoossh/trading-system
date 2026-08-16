"""
Tests for behaviour that is driven by config.yaml rather than by literals.

The point of moving these values into config is that changing the config
actually changes what the system does. Each test here sets a value and checks
the behaviour follows, so a future refactor that quietly re-hardcodes a number
fails instead of silently ignoring the operator's settings.
"""

import datetime as dt

import pandas as pd
import pytest

from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.strategy_engine.config import (
    default_costs,
    load_strategy_config,
)
from unified_trading_platform.trading_core.strategy_engine.greeks_helper import (
    dividend_yield,
    min_option_price,
    risk_free_rate,
)
from unified_trading_platform.trading_core.strategy_engine.live_engine import UnifiedStrategyEngine
from unified_trading_platform.trading_core.strategy_engine.strikes import _detect_step, default_strike_step

from helpers import SESSION_DATE, SESSION_EXPIRY, at, make_tick, straddle_chain

ATM = 21600.0
SPOT = 21612.20


@pytest.fixture
def override_setting():
    """Temporarily set a dot-path config value, restoring it afterwards."""
    saved = {}

    def _set(path, value):
        if path not in saved:
            saved[path] = settings.get(path)
        settings.set(path, value)

    yield _set

    for path, value in saved.items():
        settings.set(path, value)


class TestConfigFileDeclaresEverything:
    """Every setting the code reads must actually exist in config.yaml."""

    @pytest.mark.parametrize(
        "path",
        [
            "system.event_queue_poll_s",
            "system.shutdown_timeout_s",
            "pricing.risk_free_rate",
            "pricing.dividend_yield",
            "pricing.min_option_price",
            "pricing.implied_vol.lower_bound",
            "pricing.implied_vol.upper_bound",
            "pricing.implied_vol.tolerance",
            "pricing.implied_vol.max_iterations",
            "backtest.bar_size",
            "backtest.default_duration_days",
            "backtest.max_reentries_cap",
            "backtest.costs.per_lot_roundtrip",
            "backtest.costs.slippage_per_fill",
            "brokers.paper_broker.fill_delay_s",
            "brokers.paper_broker.emit_interval_s",
            "brokers.paper_broker.poll_interval_s",
            "brokers.paper_broker.slippage_per_fill",
            "brokers.interactive_brokers.timeouts.connect_s",
            "brokers.interactive_brokers.timeouts.historical_data_s",
            "brokers.interactive_brokers.timeouts.contract_details_s",
            "brokers.interactive_brokers.timeouts.option_params_s",
            "brokers.interactive_brokers.timeouts.market_data_s",
            "defaults.data.strike_step",
            "defaults.contract.time_in_force",
        ],
    )
    def test_setting_is_present(self, path):
        assert settings.get(path) is not None, f"{path} is read by the code but missing from config.yaml"


class TestPricingAssumptions:
    def test_accessors_read_from_config(self, override_setting):
        override_setting("pricing.risk_free_rate", 0.075)
        override_setting("pricing.dividend_yield", 0.012)
        override_setting("pricing.min_option_price", 0.25)

        assert risk_free_rate() == pytest.approx(0.075)
        assert dividend_yield() == pytest.approx(0.012)
        assert min_option_price() == pytest.approx(0.25)

    def test_bs_params_default_from_config(self, override_setting):
        from unified_trading_platform.trading_core.strategy_engine.greeks_helper import BSParams

        override_setting("pricing.risk_free_rate", 0.09)
        assert BSParams().r == pytest.approx(0.09)

    def test_implied_vol_bounds_are_honoured(self, override_setting):
        from unified_trading_platform.trading_core.strategy_engine.greeks_helper import iv_from_price_scalar

        override_setting("pricing.implied_vol.upper_bound", 2.0)
        # A price above what the highest allowed vol can produce clamps to it.
        iv = iv_from_price_scalar(100.0, 100.0, 1.0, 0.05, 0.0, "C", 99.0)
        assert iv == pytest.approx(2.0)

    def test_rate_change_moves_prices(self, override_setting):
        """Proof the configured rate reaches the maths, not just the accessor."""
        from unified_trading_platform.trading_core.strategy_engine.greeks_helper import (
            compute_iv_delta_for_chain,
        )

        chain = pd.DataFrame(
            {
                "strike": [21600.0, 21600.0],
                "option_type": ["CE", "PE"],
                "Close": [120.0, 80.0],
                "timestamp": [dt.datetime(2024, 1, 2, 11, 0)] * 2,
            }
        )
        kwargs = dict(S=21612.2, expiry_dt=dt.datetime(2024, 1, 4, 15, 30), now_dt=dt.datetime(2024, 1, 2, 11, 0))

        override_setting("pricing.risk_free_rate", 0.0)
        low = compute_iv_delta_for_chain(chain, **kwargs)["IV"].tolist()
        override_setting("pricing.risk_free_rate", 0.50)
        high = compute_iv_delta_for_chain(chain, **kwargs)["IV"].tolist()

        assert low != high, "the configured risk-free rate must affect implied vol"


class TestStrikeStep:
    def test_default_comes_from_config(self, override_setting):
        override_setting("defaults.data.strike_step", 25.0)
        assert default_strike_step() == pytest.approx(25.0)

    def test_sparse_chain_falls_back_to_configured_step(self, override_setting):
        override_setting("defaults.data.strike_step", 100.0)
        assert _detect_step(pd.Series([21600.0])) == pytest.approx(100.0)

    def test_inferred_step_still_wins_over_config(self, override_setting):
        override_setting("defaults.data.strike_step", 100.0)
        assert _detect_step(pd.Series([21500.0, 21550.0, 21600.0])) == pytest.approx(50.0)


class TestExecutionCosts:
    """`costs` in config.yaml / a strategy JSON must reach the PnL numbers."""

    def _engine(self, costs):
        config = load_strategy_config("atm_short_straddle_1100_1515")
        config.costs = costs
        engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
        engine.initialize(current_date=SESSION_DATE, entry_time="11:00", exit_time="15:15")
        engine.live_legs = [engine.live_legs[0]]  # single CE leg
        return engine

    def _run(self, costs, exit_premium=80.0):
        engine = self._engine(costs)
        chain = straddle_chain(center=ATM, ce_atm=120.0, expiry=SESSION_EXPIRY)
        engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain)
        engine.process_tick(
            make_tick(at("15:15"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=exit_premium, expiry=SESSION_EXPIRY)
        )
        return engine

    def test_zero_costs_leave_pnl_untouched(self):
        engine = self._run({"per_lot_roundtrip": 0.0, "slippage_per_fill": 0.0})
        row = engine.rows[-1]
        assert row["pnl_after_cost"] == pytest.approx(row["pnl"])

    def test_commission_is_charged_per_lot_over_a_round_trip(self):
        """qty 75 / lot 75 = 1 lot; a closed leg pays the full round trip."""
        engine = self._run({"per_lot_roundtrip": 40.0, "slippage_per_fill": 0.0})
        row = engine.rows[-1]
        assert row["pnl_after_cost"] == pytest.approx(row["pnl"] - 40.0)

    def test_open_leg_is_charged_only_the_entry_half(self):
        engine = self._engine({"per_lot_roundtrip": 40.0, "slippage_per_fill": 0.0})
        chain = straddle_chain(center=ATM, ce_atm=120.0, expiry=SESSION_EXPIRY)
        engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain)
        engine.process_tick(make_tick(at("12:00"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=110.0))
        row = engine.rows[-1]
        assert engine.live_legs[0].exit_ts is None
        assert row["pnl_after_cost"] == pytest.approx(row["pnl"] - 20.0)

    def test_slippage_is_charged_per_fill_per_unit(self):
        """2 fills x 75 units x 0.5 points = 75.0."""
        engine = self._run({"per_lot_roundtrip": 0.0, "slippage_per_fill": 0.5})
        row = engine.rows[-1]
        assert row["pnl_after_cost"] == pytest.approx(row["pnl"] - 75.0)

    def test_costs_reduce_a_winning_trade(self):
        engine = self._run({"per_lot_roundtrip": 40.0, "slippage_per_fill": 0.0})
        row = engine.rows[-1]
        assert row["pnl"] > 0
        assert row["pnl_after_cost"] < row["pnl"]

    def test_strategy_costs_default_to_platform_config(self, override_setting):
        override_setting("backtest.costs.per_lot_roundtrip", 12.5)
        assert default_costs()["per_lot_roundtrip"] == pytest.approx(12.5)

    def test_bundled_strategies_carry_cost_keys(self):
        config = load_strategy_config("atm_short_straddle_1100_1515")
        assert "per_lot_roundtrip" in config.costs
        assert "slippage_per_fill" in config.costs


class TestReEntryCap:
    def test_cap_is_configurable(self, override_setting):
        from unified_trading_platform.trading_core.strategy_engine.live_engine import _max_reentries_cap

        override_setting("backtest.max_reentries_cap", 3)
        assert _max_reentries_cap() == 3

    def test_cap_limits_a_greedy_strategy(self, override_setting):
        """A strategy asking for 99 re-entries is held to the configured ceiling."""
        from unified_trading_platform.trading_core.strategy_engine.config import ReEntryRule, RiskConfig, RiskRule

        override_setting("backtest.max_reentries_cap", 1)
        config = load_strategy_config("atm_short_straddle_1100_1515")
        engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
        engine.initialize(current_date=SESSION_DATE, entry_time="11:00", exit_time="15:15")
        engine.live_legs = [engine.live_legs[0]]
        leg = engine.live_legs[0]
        leg.spec.risk = RiskConfig(
            target=RiskRule(enabled=False, basis="premium_pct", value=0.0),
            sl=RiskRule(enabled=True, basis="premium_pct", value=25),
        )
        leg.spec.reentry_on_sl = ReEntryRule(enabled=True, mode="RE_ASAP", max_count=99)
        leg.re_sl_count = 1  # already at the configured cap

        engine.process_tick(
            make_tick(at("11:00"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=120.0, expiry=SESSION_EXPIRY)
        )
        engine.process_tick(
            make_tick(at("12:00"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=150.0, expiry=SESSION_EXPIRY)
        )
        assert engine.pending_reentries == []
        assert len(engine.live_legs) == 1


class TestPaperBrokerSettings:
    def test_defaults_come_from_config(self, override_setting, h5_path):
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        override_setting("brokers.paper_broker.fill_delay_s", 0.25)
        override_setting("brokers.paper_broker.slippage_per_fill", 1.5)

        broker = PaperBroker(h5_path=str(h5_path))
        assert broker.config.fill_delay_s == pytest.approx(0.25)
        assert broker.config.slippage_per_fill == pytest.approx(1.5)

    def test_explicit_argument_beats_config(self, override_setting, h5_path):
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        override_setting("brokers.paper_broker.fill_delay_s", 0.25)
        broker = PaperBroker(h5_path=str(h5_path), fill_delay_s=0.01)
        assert broker.config.fill_delay_s == pytest.approx(0.01)


class TestFillPricing:
    """Fills must be priced off the order's reference, not zero."""

    def _broker(self, h5_path, **kwargs):
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        return PaperBroker(h5_path=str(h5_path), fill_delay_s=0.01, **kwargs)

    def _order(self, action, **kwargs):
        from unified_trading_platform.trading_core.data_models import Order, OrderAction, OrderType

        return Order(
            action=OrderAction[action],
            quantity=75,
            order_type=kwargs.pop("order_type", OrderType.LIMIT),
            **kwargs,
        )

    def test_limit_order_fills_at_its_limit(self, h5_path):
        broker = self._broker(h5_path)
        assert broker._fill_price(self._order("BUY", limit_price=121.15)) == pytest.approx(121.15)

    def test_market_order_with_a_reference_price_fills_there(self, h5_path):
        """The engine attaches the premium it acted on; a fill must use it."""
        from unified_trading_platform.trading_core.data_models import OrderType

        broker = self._broker(h5_path)
        order = self._order("SELL", order_type=OrderType.MARKET, limit_price=81.75)
        assert broker._fill_price(order) == pytest.approx(81.75)

    def test_stop_order_falls_back_to_the_stop_price(self, h5_path):
        from unified_trading_platform.trading_core.data_models import OrderType

        broker = self._broker(h5_path)
        order = self._order("SELL", order_type=OrderType.STOP, stop_price=21500.0)
        assert broker._fill_price(order) == pytest.approx(21500.0)

    def test_slippage_works_against_the_trader(self, h5_path):
        broker = self._broker(h5_path, slippage_per_fill=0.5)
        assert broker._fill_price(self._order("BUY", limit_price=100.0)) == pytest.approx(100.5)
        assert broker._fill_price(self._order("SELL", limit_price=100.0)) == pytest.approx(99.5)

    def test_slippage_never_produces_a_negative_price(self, h5_path):
        broker = self._broker(h5_path, slippage_per_fill=10.0)
        assert broker._fill_price(self._order("SELL", limit_price=1.0)) == 0.0

    def test_priceless_order_fills_at_zero_with_a_warning(self, h5_path, caplog):
        from unified_trading_platform.trading_core.data_models import OrderType

        broker = self._broker(h5_path)
        order = self._order("BUY", order_type=OrderType.MARKET)
        assert broker._fill_price(order) == 0.0
        assert any("reference price" in record.message for record in caplog.records)


class TestSignalsCarryTheirReferencePrice:
    def _engine(self):
        config = load_strategy_config("atm_short_straddle_1100_1515")
        engine = UnifiedStrategyEngine(config, exchange="NSE", currency="INR")
        engine.initialize(current_date=SESSION_DATE, entry_time="11:00", exit_time="15:15")
        return engine

    def test_entry_signal_carries_the_premium(self):
        engine = self._engine()
        chain = straddle_chain(center=ATM, ce_atm=120.0, pe_atm=80.0, expiry=SESSION_EXPIRY)
        signals = engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain)
        prices = sorted(s.price for s in signals)
        assert prices == pytest.approx([80.0, 120.0])

    def test_entry_signal_carries_the_underlying(self):
        engine = self._engine()
        chain = straddle_chain(center=ATM, expiry=SESSION_EXPIRY)
        signals = engine.process_tick(make_tick(at("11:00"), SPOT), SPOT, chain)
        assert all(s.underlying_price == pytest.approx(SPOT) for s in signals)

    def test_exit_signal_carries_the_exit_premium(self):
        engine = self._engine()
        engine.process_tick(
            make_tick(at("11:00"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=120.0, expiry=SESSION_EXPIRY)
        )
        signals = engine.process_tick(
            make_tick(at("15:15"), SPOT), SPOT, straddle_chain(center=ATM, ce_atm=70.0, pe_atm=40.0)
        )
        assert signals
        assert all(s.price is not None and s.price > 0 for s in signals)

    def test_signal_timestamp_is_the_simulated_clock(self):
        engine = self._engine()
        signals = engine.process_tick(
            make_tick(at("11:00"), SPOT), SPOT, straddle_chain(center=ATM, expiry=SESSION_EXPIRY)
        )
        assert all(s.signal_timestamp == at("11:00") for s in signals)


class TestUnderlyingContractFromStrategyConfig:
    def test_contract_id_and_type_are_not_hardcoded(self, tmp_path, h5_path):
        from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

        manager = StrategyManager(
            broker_name="paper",
            exchange="NSE",
            strategy_name="atm_short_straddle_1100_1515",
            start_date="2024-01-01",
            end_date="2024-01-31",
            db_path=str(tmp_path / "c.db"),
        )
        manager.strategy_config = load_strategy_config("atm_short_straddle_1100_1515")
        manager.strategy_config.underlying_con_id = 4242
        manager.strategy_config.underlying_security_type = "STK"

        contract = manager._create_underlying_contract()
        assert contract.conId == 4242, "contract id must come from the strategy, not a constant"
        manager.trading_system.shutdown()

    def test_strategy_config_exposes_the_fields(self):
        config = load_strategy_config("atm_short_straddle_1100_1515")
        assert hasattr(config, "underlying_con_id")
        assert hasattr(config, "underlying_security_type")
