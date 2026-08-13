"""
Contract tests for the HTTP gateway.

These drive the FastAPI app through its real routes against the paper broker and
assert on the response shapes clients depend on. The gateway is a thin layer, so
the point here is that it wires through to `trading_core` correctly and reports
errors with sensible status codes rather than 500s.
"""

import time

import pytest

fastapi_testclient = pytest.importorskip("fastapi.testclient", reason="fastapi is required for API tests")

from helpers import NIFTY_SYMBOL  # noqa: E402

SETTLE_TIMEOUT = 5.0


@pytest.fixture
def api(tmp_db, h5_path):
    """A TestClient whose shared TradingSystem points at a throwaway database."""
    from unified_trading_platform.api import runtime
    from unified_trading_platform.api.endpoints import strategies as strategies_endpoint
    from unified_trading_platform.api.main import app
    from unified_trading_platform.trading_core.trading_system import TradingSystem

    system = TradingSystem(db_path=tmp_db)
    previous = runtime._trading_system
    runtime._trading_system = system
    strategies_endpoint._strategy_managers.clear()

    with fastapi_testclient.TestClient(app) as client:
        client.h5_path = str(h5_path)
        yield client

    runtime._trading_system = previous
    system.shutdown()


@pytest.fixture
def api_with_broker(api):
    response = api.post(
        "/brokers",
        json={
            "name": "paper",
            "broker_type": "paper",
            "config": {"h5_path": api.h5_path, "fill_delay_s": 0.05},
        },
    )
    assert response.status_code == 201, response.text
    return api


class TestHealth:
    def test_ready(self, api):
        response = api.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_live(self, api):
        assert api.get("/health/live").json() == {"status": "ok"}

    def test_openapi_schema_is_served(self, api):
        response = api.get("/api/v1/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"]
        for path in ("/health/ready", "/brokers", "/orders/limit", "/data/historical"):
            assert path in schema["paths"], f"{path} missing from the OpenAPI schema"


class TestBrokerEndpoints:
    def test_broker_list_starts_empty(self, api):
        assert api.get("/brokers").json() == []

    def test_add_broker(self, api):
        response = api.post(
            "/brokers",
            json={"name": "paper", "broker_type": "paper", "config": {"h5_path": api.h5_path}},
        )
        assert response.status_code == 201
        assert response.json()["success"] is True

    def test_added_broker_is_listed_as_connected(self, api_with_broker):
        brokers = api_with_broker.get("/brokers").json()
        assert len(brokers) == 1
        assert brokers[0]["name"] == "paper"
        assert brokers[0]["broker_type"] == "PaperBroker"
        assert brokers[0]["is_connected"] is True

    def test_get_single_broker(self, api_with_broker):
        broker = api_with_broker.get("/brokers/paper").json()
        assert broker["name"] == "paper"

    def test_unknown_broker_is_404(self, api_with_broker):
        assert api_with_broker.get("/brokers/ghost").status_code == 404

    def test_account_info(self, api_with_broker):
        info = api_with_broker.get("/brokers/paper/account").json()
        assert info["broker_name"] == "paper"
        assert info["cash_balance"] == pytest.approx(1_000_000.0)

    def test_account_for_unknown_broker_is_404(self, api_with_broker):
        assert api_with_broker.get("/brokers/ghost/account").status_code == 404

    def test_remove_broker(self, api_with_broker):
        assert api_with_broker.delete("/brokers/paper").status_code == 200
        assert api_with_broker.get("/brokers").json() == []

    def test_removing_unknown_broker_is_404(self, api_with_broker):
        assert api_with_broker.delete("/brokers/ghost").status_code == 404

    def test_unknown_broker_type_is_rejected(self, api):
        response = api.post("/brokers", json={"name": "x", "broker_type": "not_a_broker"})
        assert response.status_code >= 400
        assert api.get("/brokers").json() == []


class TestDataEndpoints:
    def test_historical_data(self, api_with_broker):
        response = api_with_broker.post(
            "/data/historical",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "currency": "INR",
                "duration": "1 D",
                "bar_size": "1h",
                "broker_name": "paper",
            },
        )
        assert response.status_code == 200, response.text
        bars = response.json()["bars"]
        assert bars, "no bars returned"
        first = bars[0]
        for field in ("timestamp", "open", "high", "low", "close", "volume"):
            assert field in first
        assert first["high"] >= first["low"]

    def test_historical_bars_are_ordered(self, api_with_broker):
        bars = api_with_broker.post(
            "/data/historical",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "currency": "INR",
                "duration": "1 D",
                "bar_size": "1h",
                "broker_name": "paper",
            },
        ).json()["bars"]
        stamps = [b["timestamp"] for b in bars]
        assert stamps == sorted(stamps)

    def test_option_chain(self, api_with_broker):
        response = api_with_broker.post(
            "/data/option-chain",
            json={"symbol": "NIFTY", "exchange": "NSE", "expiry": "2024-01-04", "broker_name": "paper"},
        )
        assert response.status_code == 200, response.text
        assert response.json() is not None

    def test_historical_data_for_unknown_broker_errors(self, api_with_broker):
        response = api_with_broker.post(
            "/data/historical",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "currency": "INR",
                "duration": "1 D",
                "bar_size": "1h",
                "broker_name": "ghost",
            },
        )
        assert response.status_code >= 400


class TestOrderEndpoints:
    def _limit_order(self, client, **overrides):
        payload = {
            "symbol": NIFTY_SYMBOL,
            "exchange": "NSE",
            "action": "BUY",
            "quantity": 75,
            "limit_price": 121.15,
            "broker_name": "paper",
            "currency": "INR",
        }
        payload.update(overrides)
        return client.post("/orders/limit", json=payload)

    def test_submit_limit_order(self, api_with_broker):
        response = self._limit_order(api_with_broker)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["order_id"]
        assert body["status"] == "submitted"

    def test_submit_market_order(self, api_with_broker):
        response = api_with_broker.post(
            "/orders/market",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "action": "SELL",
                "quantity": 75,
                "broker_name": "paper",
                "currency": "INR",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["order_id"]

    def test_submit_stop_order(self, api_with_broker):
        response = api_with_broker.post(
            "/orders/stop",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "action": "SELL",
                "quantity": 75,
                "stop_price": 21500.0,
                "broker_name": "paper",
                "currency": "INR",
            },
        )
        assert response.status_code == 200, response.text

    def test_stop_limit_is_reported_as_unimplemented(self, api_with_broker):
        response = api_with_broker.post(
            "/orders/stop-limit",
            json={
                "symbol": NIFTY_SYMBOL,
                "exchange": "NSE",
                "action": "BUY",
                "quantity": 75,
                "limit_price": 100.0,
                "stop_price": 99.0,
                "broker_name": "paper",
                "currency": "INR",
            },
        )
        assert response.status_code == 501, "unimplemented must be 501, not 500"

    def test_order_status_round_trip(self, api_with_broker):
        order_id = self._limit_order(api_with_broker).json()["order_id"]
        response = api_with_broker.get(f"/orders/{order_id}")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["order_id"] == order_id
        assert body["symbol"] == NIFTY_SYMBOL
        assert body["quantity"] == 75
        assert body["broker_name"] == "paper"

    def test_order_reaches_filled_over_the_api(self, api_with_broker):
        order_id = self._limit_order(api_with_broker).json()["order_id"]
        deadline = time.time() + SETTLE_TIMEOUT
        status = None
        while time.time() < deadline:
            status = api_with_broker.get(f"/orders/{order_id}").json()["status"]
            if status == "Filled":
                break
            time.sleep(0.05)
        assert status == "Filled"

    def test_list_orders(self, api_with_broker):
        ids = {self._limit_order(api_with_broker).json()["order_id"] for _ in range(3)}
        listed = {o["order_id"] for o in api_with_broker.get("/orders").json()}
        assert ids <= listed

    def test_unknown_order_is_404(self, api_with_broker):
        assert api_with_broker.get("/orders/not-a-real-order").status_code == 404

    def test_order_history(self, api_with_broker):
        order_id = self._limit_order(api_with_broker).json()["order_id"]
        response = api_with_broker.get("/orders/history/orders")
        assert response.status_code == 200, response.text
        assert order_id in {row["order_id"] for row in response.json()}

    def test_trade_history_is_queryable(self, api_with_broker):
        response = api_with_broker.get("/orders/history/trades")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_cancel_filled_order_reports_failure(self, api_with_broker):
        order_id = self._limit_order(api_with_broker).json()["order_id"]
        deadline = time.time() + SETTLE_TIMEOUT
        while time.time() < deadline:
            if api_with_broker.get(f"/orders/{order_id}").json()["status"] == "Filled":
                break
            time.sleep(0.05)
        assert api_with_broker.delete(f"/orders/{order_id}").status_code == 400

    def test_invalid_quantity_is_rejected(self, api_with_broker):
        response = self._limit_order(api_with_broker, quantity="many")
        assert response.status_code == 422, "pydantic should reject a non-integer quantity"


class TestStrategyEndpoints:
    def _initialize(self, client, tmp_path):
        return client.post(
            "/strategies/initialize",
            json={
                "broker_name": "paper",
                "exchange": "NSE",
                "strategy_name": "atm_short_straddle_1100_1515",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "db_path": str(tmp_path / "api_strategy.db"),
            },
        )

    def test_initialize_returns_a_run_id(self, api_with_broker, tmp_path):
        response = self._initialize(api_with_broker, tmp_path)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["run_id"]
        assert body["is_initialized"] is True
        assert body["strategy_name"] == "atm_short_straddle_1100_1515"

    def test_status_for_a_run(self, api_with_broker, tmp_path):
        run_id = self._initialize(api_with_broker, tmp_path).json()["run_id"]
        response = api_with_broker.get(f"/strategies/{run_id}/status")
        assert response.status_code == 200
        assert response.json()["run_id"] == run_id

    def test_portfolio_for_a_run(self, api_with_broker, tmp_path):
        run_id = self._initialize(api_with_broker, tmp_path).json()["run_id"]
        response = api_with_broker.get(f"/strategies/{run_id}/portfolio")
        assert response.status_code == 200, response.text
        body = response.json()
        for field in ("total_pnl", "open_positions", "closed_positions", "total_positions"):
            assert field in body

    def test_unknown_run_is_404(self, api_with_broker):
        assert api_with_broker.get("/strategies/no-such-run/status").status_code == 404

    def test_delete_run(self, api_with_broker, tmp_path):
        run_id = self._initialize(api_with_broker, tmp_path).json()["run_id"]
        assert api_with_broker.delete(f"/strategies/{run_id}").status_code == 200
        assert api_with_broker.get(f"/strategies/{run_id}/status").status_code == 404

    def test_unknown_strategy_name_errors(self, api_with_broker, tmp_path):
        response = api_with_broker.post(
            "/strategies/initialize",
            json={
                "broker_name": "paper",
                "exchange": "NSE",
                "strategy_name": "does_not_exist",
                "db_path": str(tmp_path / "x.db"),
            },
        )
        assert response.status_code >= 400


class TestSharedRuntime:
    def test_endpoints_share_one_trading_system(self, api_with_broker):
        """A broker added through one request must be visible to the next."""
        from unified_trading_platform.api.runtime import get_trading_system

        assert "paper" in get_trading_system().brokers
        assert api_with_broker.get("/brokers").json()[0]["name"] == "paper"

    def test_get_trading_system_is_a_singleton(self):
        from unified_trading_platform.api.runtime import get_trading_system

        assert get_trading_system() is get_trading_system()
