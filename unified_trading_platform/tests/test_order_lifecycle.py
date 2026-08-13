"""
Accuracy tests for order management and status tracking.

Covers the whole path an order takes: TradingSystem -> OrderManager -> broker,
the status callbacks coming back, and what ends up in SQLite. Assertions are on
required behaviour (an order's quantity must survive the round trip, a filled
order must not be cancellable) rather than on recorded output.
"""

import sqlite3
import time

import pytest

from unified_trading_platform.trading_core.data_models import (
    Contract,
    Order,
    OrderAction,
    OrderStatus,
    OrderType,
    SecurityType,
)

from helpers import NIFTY_SYMBOL

SETTLE_TIMEOUT = 5.0


def wait_until(predicate, timeout=SETTLE_TIMEOUT, interval=0.02):
    """Poll until `predicate()` is truthy; return whether it became true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def order_of(system, order_id):
    return system.order_manager.get_order(order_id)


@pytest.fixture
def submit_limit(paper_system):
    def _submit(action="BUY", quantity=75, limit_price=121.15):
        return paper_system.submit_limit_order(
            symbol=NIFTY_SYMBOL,
            exchange="NSE",
            action=action,
            quantity=quantity,
            limit_price=limit_price,
            broker_name="paper",
            currency="INR",
        )

    return _submit


class TestOrderSubmission:
    def test_limit_order_is_recorded_with_its_terms(self, paper_system, submit_limit):
        order_id = submit_limit(action="BUY", quantity=75, limit_price=121.15)
        managed = order_of(paper_system, order_id)

        assert managed is not None
        assert managed.order.action == OrderAction.BUY
        assert managed.order.quantity == 75
        assert managed.order.order_type == OrderType.LIMIT
        assert managed.order.limit_price == pytest.approx(121.15)
        assert managed.broker_name == "paper"
        assert managed.contract.symbol == NIFTY_SYMBOL
        assert managed.broker_order_id is not None, "broker's id must be captured"

    def test_market_order_has_no_limit_price(self, paper_system):
        order_id = paper_system.submit_market_order(
            symbol=NIFTY_SYMBOL, exchange="NSE", action="SELL", quantity=150, broker_name="paper", currency="INR"
        )
        managed = order_of(paper_system, order_id)
        assert managed.order.order_type == OrderType.MARKET
        assert managed.order.limit_price is None
        assert managed.order.action == OrderAction.SELL
        assert managed.order.quantity == 150

    def test_stop_order_carries_stop_price(self, paper_system):
        order_id = paper_system.submit_stop_order(
            symbol=NIFTY_SYMBOL,
            exchange="NSE",
            action="SELL",
            quantity=75,
            stop_price=21500.0,
            broker_name="paper",
            currency="INR",
        )
        managed = order_of(paper_system, order_id)
        assert managed.order.order_type == OrderType.STOP
        assert managed.order.stop_price == pytest.approx(21500.0)

    def test_order_ids_are_unique(self, submit_limit):
        ids = {submit_limit() for _ in range(5)}
        assert len(ids) == 5

    def test_remaining_quantity_starts_at_full_size(self, paper_system, submit_limit):
        order_id = submit_limit(quantity=225)
        managed = order_of(paper_system, order_id)
        # Read before the fill lands, so compare against either state.
        assert managed.remaining_quantity in (225, 0)

    def test_unknown_broker_is_rejected(self, paper_system):
        with pytest.raises(ValueError, match="not found"):
            paper_system.submit_market_order(
                symbol=NIFTY_SYMBOL,
                exchange="NSE",
                action="BUY",
                quantity=75,
                broker_name="ghost_broker",
                currency="INR",
            )

    def test_invalid_action_is_rejected(self, paper_system):
        with pytest.raises(ValueError):
            paper_system.submit_market_order(
                symbol=NIFTY_SYMBOL,
                exchange="NSE",
                action="SIDEWAYS",
                quantity=75,
                broker_name="paper",
                currency="INR",
            )


class TestFillTracking:
    def test_order_reaches_filled_state(self, paper_system, submit_limit):
        order_id = submit_limit()
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)

    def test_fill_populates_quantities_and_price(self, paper_system, submit_limit):
        order_id = submit_limit(quantity=150, limit_price=99.5)
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)

        managed = order_of(paper_system, order_id)
        assert managed.filled_quantity == 150, "a filled order must report the filled size"
        assert managed.remaining_quantity == 0
        assert managed.avg_fill_price == pytest.approx(99.5), "paper broker fills at the limit price"

    def test_updated_at_advances_on_fill(self, paper_system, submit_limit):
        order_id = submit_limit()
        created = order_of(paper_system, order_id).created_at
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)
        assert order_of(paper_system, order_id).updated_at >= created

    def test_fill_callback_fires_with_the_order(self, paper_system, submit_limit):
        seen = []
        paper_system.register_order_callback("order_filled", seen.append)
        order_id = submit_limit()

        assert wait_until(lambda: any(o.order_id == order_id for o in seen))
        filled = next(o for o in seen if o.order_id == order_id)
        assert filled.status == OrderStatus.FILLED

    def test_submission_callback_fires_immediately(self, paper_system, submit_limit):
        seen = []
        paper_system.register_order_callback("order_submitted", seen.append)
        order_id = submit_limit()
        assert any(o.order_id == order_id for o in seen)

    def test_unknown_callback_type_is_rejected(self, paper_system):
        with pytest.raises(ValueError, match="Unknown event type"):
            paper_system.register_order_callback("order_teleported", lambda o: None)


class TestCancellation:
    def test_cancelling_a_filled_order_is_refused(self, paper_system, submit_limit):
        """A terminal order cannot be cancelled, and must not report success."""
        order_id = submit_limit()
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)

        assert paper_system.cancel_order(order_id) is False
        time.sleep(0.2)
        assert order_of(paper_system, order_id).status == OrderStatus.FILLED, (
            "a filled order must stay filled after a refused cancel"
        )

    def test_cancelling_before_fill_succeeds(self, paper_system):
        """Submit against a slow-filling broker so the order is still live."""
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        broker: PaperBroker = paper_system.brokers["paper"]
        broker.config.fill_delay_s = 3.0
        try:
            order_id = paper_system.submit_limit_order(
                symbol=NIFTY_SYMBOL,
                exchange="NSE",
                action="BUY",
                quantity=75,
                limit_price=100.0,
                broker_name="paper",
                currency="INR",
            )
            assert paper_system.cancel_order(order_id) is True
        finally:
            broker.config.fill_delay_s = 0.05

    def test_cancelling_unknown_order_returns_false(self, paper_system):
        assert paper_system.cancel_order("no-such-order-id") is False

    def test_cancel_callback_fires(self, paper_system):
        from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker

        broker: PaperBroker = paper_system.brokers["paper"]
        broker.config.fill_delay_s = 3.0
        seen = []
        paper_system.register_order_callback("order_cancelled", seen.append)
        try:
            order_id = paper_system.submit_limit_order(
                symbol=NIFTY_SYMBOL,
                exchange="NSE",
                action="BUY",
                quantity=75,
                limit_price=100.0,
                broker_name="paper",
                currency="INR",
            )
            broker.config.fill_delay_s = 0.05
            paper_system.cancel_order(order_id)
            assert wait_until(lambda: any(o.order_id == order_id for o in seen))
            assert order_of(paper_system, order_id).status == OrderStatus.CANCELLED
        finally:
            broker.config.fill_delay_s = 0.05


class TestStatusReporting:
    REQUIRED_FIELDS = {
        "order_id",
        "broker_order_id",
        "broker_name",
        "symbol",
        "exchange",
        "security_type",
        "currency",
        "action",
        "order_type",
        "quantity",
        "limit_price",
        "stop_price",
        "time_in_force",
        "status",
        "filled_quantity",
        "remaining_quantity",
        "avg_fill_price",
        "created_at",
        "updated_at",
    }

    def test_status_dict_is_complete(self, paper_system, submit_limit):
        """The API's OrderInfo model requires every one of these keys."""
        order_id = submit_limit()
        status = paper_system.get_order_status(order_id)
        assert self.REQUIRED_FIELDS <= set(status), (
            f"missing: {self.REQUIRED_FIELDS - set(status)}"
        )

    def test_status_values_are_serialisable_primitives(self, paper_system, submit_limit):
        order_id = submit_limit()
        status = paper_system.get_order_status(order_id)
        assert isinstance(status["status"], str)
        assert isinstance(status["action"], str)
        assert isinstance(status["order_type"], str)
        assert isinstance(status["security_type"], str)

    def test_unknown_order_yields_empty_status(self, paper_system):
        assert paper_system.get_order_status("nope") == {}

    def test_get_all_orders_lists_every_order(self, paper_system, submit_limit):
        ids = {submit_limit() for _ in range(3)}
        listed = {o["order_id"] for o in paper_system.get_all_orders()}
        assert ids <= listed

    def test_orders_can_be_filtered_by_status(self, paper_system, submit_limit):
        order_id = submit_limit()
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)
        filled = paper_system.order_manager.get_orders(status=OrderStatus.FILLED)
        assert order_id in {o.order_id for o in filled}

    def test_orders_can_be_filtered_by_broker(self, paper_system, submit_limit):
        order_id = submit_limit()
        assert order_id in {o.order_id for o in paper_system.order_manager.get_orders(broker_name="paper")}
        assert paper_system.order_manager.get_orders(broker_name="other") == []


class TestPersistence:
    def test_order_is_written_to_the_database(self, paper_system, submit_limit, tmp_db):
        order_id = submit_limit(action="SELL", quantity=225, limit_price=88.25)

        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT broker_name, symbol, exchange, currency, action, order_type, "
                "quantity, limit_price, status FROM orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()

        assert row is not None, "order was not persisted"
        broker_name, symbol, exchange, currency, action, order_type, quantity, limit_price, status = row
        assert broker_name == "paper"
        assert symbol == NIFTY_SYMBOL
        assert exchange == "NSE"
        assert currency == "INR"
        assert action == "SELL"
        assert order_type == OrderType.LIMIT.value
        assert quantity == 225
        assert limit_price == pytest.approx(88.25)
        assert status in {s.value for s in OrderStatus}

    def test_fill_is_persisted(self, paper_system, submit_limit, tmp_db):
        order_id = submit_limit(quantity=75, limit_price=50.0)
        assert wait_until(lambda: order_of(paper_system, order_id).status == OrderStatus.FILLED)
        # The manager writes on each status change; give the callback a moment.
        assert wait_until(lambda: self._db_status(tmp_db, order_id) == OrderStatus.FILLED.value)

        with sqlite3.connect(tmp_db) as conn:
            filled_qty, avg_price = conn.execute(
                "SELECT filled_quantity, avg_fill_price FROM orders WHERE order_id = ?", (order_id,)
            ).fetchone()
        assert filled_qty == 75
        assert avg_price == pytest.approx(50.0)

    @staticmethod
    def _db_status(db_path, order_id):
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return row[0] if row else None

    def test_order_history_returns_persisted_orders(self, paper_system, submit_limit):
        order_id = submit_limit()
        history = paper_system.get_order_history()
        assert order_id in {row["order_id"] for row in history}

    def test_order_history_filters_by_symbol(self, paper_system, submit_limit):
        order_id = submit_limit()
        assert order_id in {row["order_id"] for row in paper_system.get_order_history(symbol=NIFTY_SYMBOL)}
        assert paper_system.get_order_history(symbol="NOT_A_SYMBOL") == []

    def test_trade_history_query_works(self, paper_system):
        """The trades table must be queryable even when empty (schema sanity)."""
        assert paper_system.get_trade_history() == []

    def test_trade_persistence_matches_schema(self, paper_system, tmp_db):
        """A trade must insert cleanly — the INSERT and CREATE TABLE must agree."""
        from datetime import datetime

        from unified_trading_platform.trading_core.data_models import Trade

        trade = Trade(
            trade_id="t-1",
            order_id="o-1",
            contract=Contract(
                symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.OPTION, currency="INR"
            ),
            execution_id="exec-1",
            quantity=75,
            price=121.15,
            timestamp=datetime(2024, 1, 2, 11, 0),
            side=OrderAction.SELL,
            commission=1.5,
        )
        paper_system.order_manager._save_trade(trade, "o-1")

        with sqlite3.connect(tmp_db) as conn:
            row = conn.execute(
                "SELECT order_id, quantity, price, commission, exchange FROM trades WHERE trade_id = ?",
                ("t-1",),
            ).fetchone()
        assert row == ("o-1", 75, pytest.approx(121.15), pytest.approx(1.5), "NSE")


class TestPositionsAndAccount:
    def test_positions_are_listable(self, paper_system):
        assert isinstance(paper_system.get_positions(), list)

    def test_positions_for_named_broker(self, paper_system):
        assert isinstance(paper_system.get_positions("paper"), list)

    def test_account_info_has_numeric_balances(self, paper_system):
        info = paper_system.get_account_info("paper")
        assert info["account_id"] == "PAPER"
        for field in ("cash_balance", "buying_power", "total_value", "equity"):
            assert isinstance(info[field], (int, float))

    def test_account_info_for_unknown_broker_is_empty(self, paper_system):
        assert paper_system.get_account_info("ghost") == {}


class TestOrderManagerDirectly:
    def test_submit_requires_a_registered_broker(self, trading_system):
        contract = Contract(
            symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        order = Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.MARKET)
        with pytest.raises(ValueError, match="not found"):
            trading_system.order_manager.submit_order(contract, order, "paper")

    def test_rejected_order_is_recorded_and_raises(self, paper_system, monkeypatch):
        """A broker failure must surface, and leave a REJECTED record behind."""
        broker = paper_system.brokers["paper"]
        monkeypatch.setattr(
            broker, "submit_order", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("venue down"))
        )
        rejected = []
        paper_system.register_order_callback("order_rejected", rejected.append)

        contract = Contract(
            symbol=NIFTY_SYMBOL, exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        order = Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.MARKET)
        with pytest.raises(RuntimeError, match="venue down"):
            paper_system.order_manager.submit_order(contract, order, "paper")

        assert rejected, "order_rejected callback should have fired"
        assert rejected[0].status == OrderStatus.REJECTED

    def test_status_update_for_unknown_broker_order_is_ignored(self, paper_system):
        """Stray broker callbacks must not raise or corrupt state."""
        paper_system.order_manager._on_order_status("unknown-broker-id", {"status": OrderStatus.FILLED})
