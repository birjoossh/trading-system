"""
Conformance tests for the broker abstraction.

The platform's central claim is that it is broker-agnostic: strategies and the
API talk to `BrokerInterface`, and a new venue is added by implementing that
interface and registering it. These tests hold that claim to account — every
registered broker must actually satisfy the interface, and registering a new one
must be all it takes.
"""

import inspect

import pytest

from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.brokers.broker_factory import BrokerFactory
from unified_trading_platform.trading_core.brokers.paper_broker import PaperBroker
from unified_trading_platform.trading_core.data_models import (
    Contract,
    MarketDataType,
    Order,
    OrderAction,
    OrderType,
    SecurityType,
)

INTERFACE_METHODS = [
    "connect",
    "disconnect",
    "get_historical_data",
    "submit_order",
    "cancel_order",
    "get_order_status",
    "get_all_orders",
    "get_positions",
    "get_account_info",
    "subscribe_market_data",
    "unsubscribe_market_data",
    "get_market_data_subscriptions",
    "get_contract_details",
    "get_option_chain",
    "get_greeks",
    "set_market_data_type",
]


def registered_broker_classes():
    """Every broker class in the factory registry, de-duplicated by identity."""
    seen = {}
    for name in BrokerFactory.list_brokers():
        cls = BrokerFactory._brokers[name]
        seen.setdefault(cls, []).append(name)
    return seen


class TestRegistry:
    def test_paper_broker_is_registered(self):
        assert "paper" in BrokerFactory.list_brokers()

    def test_registry_is_not_empty(self):
        assert BrokerFactory.list_brokers()

    def test_unknown_broker_raises_with_a_helpful_message(self):
        with pytest.raises(ValueError) as excinfo:
            BrokerFactory.create_broker("not_a_broker")
        message = str(excinfo.value)
        assert "not_a_broker" in message
        assert "paper" in message, "the error should list what is available"

    def test_create_broker_returns_an_interface_implementation(self):
        broker = BrokerFactory.create_broker("paper")
        assert isinstance(broker, BrokerInterface)

    def test_create_broker_passes_configuration_through(self, h5_path):
        broker = BrokerFactory.create_broker("paper", h5_path=str(h5_path), fill_delay_s=0.01)
        assert broker.config.h5_path is not None
        assert broker.config.fill_delay_s == pytest.approx(0.01)

    def test_ib_aliases_agree_when_available(self):
        brokers = BrokerFactory.list_brokers()
        if "ib" not in brokers:
            pytest.skip("ibapi not installed; IB broker is not registered")
        assert BrokerFactory._brokers["ib"] is BrokerFactory._brokers["interactive_brokers"]

    def test_core_imports_without_ibapi(self):
        """The paper broker and the rest of the system must not need the IB SDK."""
        import importlib

        module = importlib.import_module("unified_trading_platform.trading_core.brokers.broker_factory")
        assert "paper" in module.BrokerFactory.list_brokers()


class TestInterfaceConformance:
    @pytest.mark.parametrize("cls", list(registered_broker_classes()), ids=lambda c: c.__name__)
    def test_no_abstract_methods_remain(self, cls):
        """An unimplemented abstract method makes the class un-instantiable."""
        assert not getattr(cls, "__abstractmethods__", set()), (
            f"{cls.__name__} leaves these unimplemented: {sorted(cls.__abstractmethods__)}"
        )

    @pytest.mark.parametrize("cls", list(registered_broker_classes()), ids=lambda c: c.__name__)
    def test_declares_every_interface_method(self, cls):
        for method in INTERFACE_METHODS:
            assert callable(getattr(cls, method, None)), f"{cls.__name__} is missing {method}()"

    @pytest.mark.parametrize("cls", list(registered_broker_classes()), ids=lambda c: c.__name__)
    def test_is_a_subclass_of_the_interface(self, cls):
        assert issubclass(cls, BrokerInterface)

    @pytest.mark.parametrize("method", ["get_historical_data", "submit_order", "cancel_order", "get_option_chain"])
    def test_paper_broker_signatures_match_the_interface(self, method):
        """Callers bind by name, so parameter names must line up."""
        expected = list(inspect.signature(getattr(BrokerInterface, method)).parameters)
        actual = list(inspect.signature(getattr(PaperBroker, method)).parameters)
        assert actual[: len(expected)] == expected, (
            f"PaperBroker.{method}{tuple(actual)} does not match the interface {tuple(expected)}"
        )

    def test_unsubscribe_takes_a_subscription_id(self):
        """A mismatch here means unsubscribing silently does nothing."""
        expected = list(inspect.signature(BrokerInterface.unsubscribe_market_data).parameters)
        actual = list(inspect.signature(PaperBroker.unsubscribe_market_data).parameters)
        assert actual == expected


class TestPaperBrokerBehaviour:
    @pytest.fixture
    def broker(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path), fill_delay_s=0.01)
        broker.connect()
        yield broker
        broker.disconnect()

    def test_connect_and_disconnect_toggle_state(self, h5_path):
        broker = PaperBroker(h5_path=str(h5_path))
        assert broker.is_connected is False
        assert broker.connect() is True
        assert broker.is_connected is True
        assert broker.disconnect() is True
        assert broker.is_connected is False

    def test_submit_order_returns_an_id(self, broker):
        order_id = broker.submit_order(
            Contract(symbol="NIFTY 50", exchange="NSE", security_type=SecurityType.STOCK, currency="INR"),
            Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.LIMIT, limit_price=100.0),
        )
        assert isinstance(order_id, str) and order_id

    def test_order_ids_increment(self, broker):
        contract = Contract(
            symbol="NIFTY 50", exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        order = Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.MARKET)
        ids = [broker.submit_order(contract, order) for _ in range(3)]
        assert len(set(ids)) == 3

    def test_get_all_orders_lists_submissions(self, broker):
        contract = Contract(
            symbol="NIFTY 50", exchange="NSE", security_type=SecurityType.STOCK, currency="INR"
        )
        broker.submit_order(contract, Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.MARKET))
        assert len(broker.get_all_orders()) >= 1

    def test_status_of_unknown_order(self, broker):
        assert broker.get_order_status("nope")["status"] == "Unknown"

    def test_account_info_shape(self, broker):
        info = broker.get_account_info()
        assert set(info) >= {"account_id", "cash_balance", "total_value"}

    def test_positions_is_a_list(self, broker):
        assert isinstance(broker.get_positions(), list)

    def test_market_data_subscriptions_start_empty(self, broker):
        assert broker.get_market_data_subscriptions() == []

    def test_set_market_data_type_is_accepted(self, broker):
        assert broker.set_market_data_type(MarketDataType.DELAYED) is True

    def test_unsubscribing_an_unknown_id_is_false(self, broker):
        assert broker.unsubscribe_market_data("NOTHING:NSE") is False

    def test_callbacks_can_be_registered_and_fire(self, broker):
        received = []
        broker.register_callback("order_status", lambda *args: received.append(args))
        broker.submit_order(
            Contract(symbol="NIFTY 50", exchange="NSE", security_type=SecurityType.STOCK, currency="INR"),
            Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.LIMIT, limit_price=10.0),
        )
        import time

        deadline = time.time() + 3
        while time.time() < deadline and not received:
            time.sleep(0.02)
        assert received, "order_status callback never fired"

    def test_a_failing_callback_does_not_break_the_broker(self, broker):
        broker.register_callback("order_status", lambda *args: 1 / 0)
        good = []
        broker.register_callback("order_status", lambda *args: good.append(args))
        broker.submit_order(
            Contract(symbol="NIFTY 50", exchange="NSE", security_type=SecurityType.STOCK, currency="INR"),
            Order(action=OrderAction.BUY, quantity=75, order_type=OrderType.MARKET),
        )
        import time

        deadline = time.time() + 3
        while time.time() < deadline and not good:
            time.sleep(0.02)
        assert good, "one broken callback must not stop the others"


class TestExtensibility:
    """Adding a venue must be: implement the interface, register it."""

    def test_a_new_broker_can_be_registered_and_created(self):
        class DummyBroker(BrokerInterface):
            def connect(self, **kwargs):
                self.is_connected = True
                return True

            def disconnect(self):
                self.is_connected = False
                return True

            def get_historical_data(self, contract, duration, bar_size, what_to_show="TRADES"):
                return []

            def submit_order(self, contract, order):
                return "dummy-1"

            def cancel_order(self, order_id):
                return True

            def get_order_status(self, order_id):
                return {"status": "Unknown"}

            def get_all_orders(self):
                return []

            def get_positions(self):
                return []

            def get_account_info(self):
                return {}

            def subscribe_market_data(self, contract, callback, market_data_type=None, snapshot=False,
                                      regulatory_snapshot=False, generic_tick_list=None):
                return "sub-1"

            def unsubscribe_market_data(self, subscription_id):
                return True

            def get_market_data_subscriptions(self):
                return []

            def get_contract_details(self, contract):
                return {}

            def get_option_chain(self, option_contract):
                return None

            def get_greeks(self, option_contract):
                return None

            def set_market_data_type(self, market_data_type):
                return True

        BrokerFactory.register_broker("dummy_test_broker", DummyBroker)
        try:
            broker = BrokerFactory.create_broker("dummy_test_broker")
            assert isinstance(broker, BrokerInterface)
            assert broker.connect() is True
            assert broker.submit_order(None, None) == "dummy-1"
        finally:
            BrokerFactory._brokers.pop("dummy_test_broker", None)

    def test_an_incomplete_broker_cannot_be_instantiated(self):
        """The ABC is what stops a half-built venue reaching production."""

        class HalfBroker(BrokerInterface):
            def connect(self, **kwargs):
                return True

        with pytest.raises(TypeError, match="abstract"):
            HalfBroker()

    def test_registering_replaces_a_name_cleanly(self):
        original = BrokerFactory._brokers.get("paper")
        try:
            BrokerFactory.register_broker("paper", PaperBroker)
            assert BrokerFactory._brokers["paper"] is PaperBroker
        finally:
            if original is not None:
                BrokerFactory._brokers["paper"] = original


class TestInterfaceIsNotInstantiable:
    def test_base_interface_cannot_be_constructed(self):
        with pytest.raises(TypeError):
            BrokerInterface()
