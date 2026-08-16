"""
PaperBroker: Simulated broker that replays market data and accepts orders.
Supports CSV and SQLite DB as data sources for historical bars and tick replay.
"""

import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface
from unified_trading_platform.trading_core.data_models import Contract
from unified_trading_platform.trading_core.data_models import Order, OrderAction, OrderStatus
from unified_trading_platform.trading_core.data_models import OptionChain, StrikeGroup, ExpirationGroup
from unified_trading_platform.trading_core.data_models import OptionContract
from unified_trading_platform.trading_core.data_models import OptionRight
from unified_trading_platform.trading_core.data_models import TickData
from unified_trading_platform.trading_core.data_models import UnderlyingInfo
from unified_trading_platform.trading_core.data_models.security_type_enum import SecurityType
from unified_trading_platform.trading_core.utils import get_logger

from .jio import JioH5Adapter

# Initialize logger
logger = get_logger(__name__)


def _default_duration_days() -> int:
    """Fallback lookback when a duration string cannot be parsed."""
    from unified_trading_platform.trading_core.config.config import settings

    return int(settings.get("backtest.default_duration_days", 30))


def _paper_default(key: str, fallback):
    """Paper-broker setting from config.yaml (`brokers.paper_broker.*`)."""
    from unified_trading_platform.trading_core.config.config import settings

    value = settings.get(f"brokers.paper_broker.{key}")
    return fallback if value is None else value


@dataclass
class PaperBrokerConfig:
    csv_path: Optional[Path] = None
    db_path: Optional[Path] = None
    h5_path: Optional[Path] = None
    #: Pause between replayed ticks. 0 replays as fast as the consumer can go;
    #: raise it to pace a replay against a wall clock.
    emit_interval_s: float = 0.0
    #: Simulated latency between acknowledgement and fill. 0 fills immediately.
    fill_delay_s: float = 0.0
    #: How often the SQLite tailer looks for new rows. Never 0 — that would spin.
    poll_interval_s: float = 0.5
    slippage_per_fill: float = 0.0  # price concession per fill, in points


class PaperBroker(BrokerInterface):
    """Paper (simulated) broker implementing BrokerInterface.

    - Historical bars: loaded from CSV/DB
    - Market data: tick replay from CSV/DB via subscription
    - Orders: accepted and acknowledged immediately (no real fills)
    """

    def __init__(self, **kwargs):
        super().__init__()
        self.config = PaperBrokerConfig(
            csv_path=Path(kwargs.get("csv_path")) if kwargs.get("csv_path") else None,
            db_path=Path(kwargs.get("db_path")) if kwargs.get("db_path") else None,
            h5_path=Path(kwargs.get("h5_path")) if kwargs.get("h5_path") else None,
            emit_interval_s=kwargs.get("emit_interval_s", _paper_default("emit_interval_s", 0.0)),
            fill_delay_s=kwargs.get("fill_delay_s", _paper_default("fill_delay_s", 0.0)),
            poll_interval_s=kwargs.get("poll_interval_s", _paper_default("poll_interval_s", 0.5)),
            slippage_per_fill=kwargs.get(
                "slippage_per_fill", _paper_default("slippage_per_fill", 0.0)
            ),
        )
        self.mode = "csv" if self.config.csv_path else "db" if self.config.db_path else "h5"
        self._md_threads: Dict[tuple, threading.Thread] = {}
        self._md_stops: Dict[tuple, threading.Event] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._next_order_id = 1
        logger.debug("h5_path = %s", self.config.h5_path)

    # ---- Connection Management ----
    def connect(self, **kwargs) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        for stop in list(self._md_stops.values()):
            stop.set()
        self.is_connected = False
        return True

    def normalize_symbol(self, symbol: str) -> str:
        symbol = symbol.split("2")[0]
        symbol = symbol.split(" ")[0]
        return symbol

    # ---- Option Chain ----
    def get_option_chain(self, contract: Contract) -> OptionChain:
        if not self.config.h5_path:
            raise ValueError("PaperBroker needs an h5_path to serve option chains")
        df = JioH5Adapter(self.config.h5_path, exchange=contract.exchange)
        option_chain = df.options_table()
        logger.debug("option_chain = %s", option_chain)

        #  Apply filters based on contract
        filters = []
        # Filter by symbol (extract base symbol from contract)
        if contract.symbol:
            base_symbol = self.normalize_symbol(contract.symbol)
            filters.append(option_chain["Symbol"].str.startswith(base_symbol))

        # Filter by exchange if provided
        if contract.exchange:
            filters.append(option_chain["Exchange"] == contract.exchange)

        # Filter by expiry if provided
        if contract.expiry:
            # format date
            expiry_date = pd.to_datetime(contract.expiry).date()
            filters.append(option_chain["Expiry"] == expiry_date)

        # Apply all filters
        if filters:
            option_chain = option_chain[pd.concat(filters, axis=1).all(axis=1)]

        if option_chain.empty:
            return None

        # Create underlying info
        underlying_symbol = contract.symbol.split("2")[0]  # Extract NIFTY from NIFTY2410418300CE
        underlying_info = UnderlyingInfo(
            underlying_symbol=underlying_symbol
            # underlying_contract=contract
        )
        # Process the option chain data
        if not pd.api.types.is_datetime64_any_dtype(option_chain.index):
            option_chain.index = pd.to_datetime(option_chain.index)

        # Group by expiry date
        expiration_groups = []
        for expiry_date, expiry_group in option_chain.groupby("Expiry"):
            # Calculate days to expiry
            days_to_expiry = (expiry_date - datetime.now().date()).days

            # Group by strike price
            strike_groups = []
            for strike_price, strike_group in expiry_group.groupby("Strike"):
                # Group by option type (CE/PE)
                call_data = strike_group[strike_group["OptionType"] == "CE"]
                put_data = strike_group[strike_group["OptionType"] == "PE"]

                # Process call option if exists
                call_option = None
                if not call_data.empty:
                    latest_call = call_data.iloc[-1]  # Get the latest data point
                    call_option = OptionContract(
                        option_ticker=latest_call["Symbol"],
                        ltp=float(latest_call["price"]),
                        option_right=OptionRight.CALL,
                        lot=latest_call["lot"],
                        last_updated=latest_call.name.to_pydatetime(),
                    )

                # Process put option if exists
                put_option = None
                if not put_data.empty:
                    latest_put = put_data.iloc[-1]  # Get the latest data point
                    put_option = OptionContract(
                        option_ticker=latest_put["Symbol"],
                        ltp=float(latest_put["price"]),
                        option_right=OptionRight.PUT,
                        lot=latest_put["lot"],
                        last_updated=latest_put.name.to_pydatetime(),
                    )

                # Only add strike group if at least one option exists
                if call_option or put_option:
                    strike_groups.append(
                        StrikeGroup(strike_price=float(strike_price), call_option=call_option, put_option=put_option)
                    )

            # Sort strikes by price
            strike_groups.sort(key=lambda x: x.strike_price)

            # Only add expiration group if there are valid strikes
            if strike_groups:
                expiration_groups.append(
                    ExpirationGroup(expiry_date=expiry_date, days_to_expiry=days_to_expiry, strikes=strike_groups)
                )

        # Sort expiration dates
        expiration_groups.sort(key=lambda x: x.expiry_date)

        # Create and return the option chain
        return OptionChain(contract=contract, underlying_info=underlying_info, expiration_dates=expiration_groups)

    # ---- Market Data ----
    def get_historical_data(
        self, contract: Contract, duration: str, bar_size: str, what_to_show: str = "TRADES"
    ) -> List[TickData]:
        logger.info(f"Fetching historica data {contract}")
        df = pd.DataFrame()
        if self.mode == "csv":
            if not self.config.csv_path:
                return []
            df = pd.read_csv(self.config.csv_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])  # required column
            df = df[(df["symbol"] == contract.symbol) & (df["exchange"] == contract.exchange)]
            df = df.sort_values("timestamp")
            # Filter by duration ending at last available timestamp
        elif self.mode == "h5":
            ja = JioH5Adapter(self.config.h5_path, exchange=contract.exchange)

            optionType = None
            if contract.security_type == SecurityType.STOCK:
                optionType = "EQ"
            elif contract.security_type == SecurityType.OPTION and contract.option_right is not None:
                optionType = contract.option_right.value
            df = ja.hist_ohlc(
                ticker=contract.symbol,
                exchange=contract.exchange,
                strike=contract.strike,
                opt_type=optionType,
                expiry=contract.expiry,
                bar_length=bar_size,
            )

        if not df.empty:
            return self.filter_df_for_duration(df, contract, duration)

        # DB mode
        if self.mode == "db":
            return self.read_hist_bars_from_db(contract, duration, bar_size)

        return []

    def filter_df_for_duration(self, df: pd.DataFrame, contract: Contract, duration: str) -> pd.DataFrame:
        end_dt = df["timestamp"].iloc[-1]
        num, unit = duration.split()
        num = int(num)
        if unit.upper().startswith("D"):
            start_dt = end_dt - timedelta(days=num)
        elif unit.upper().startswith("M"):
            start_dt = end_dt - timedelta(days=num * 30)
        elif unit.upper().startswith("W"):
            start_dt = end_dt - timedelta(weeks=num)
        else:
            start_dt = end_dt - timedelta(days=_default_duration_days())
        df = df[df["timestamp"] >= start_dt]
        ticks: List[TickData] = []
        for _, row in df.iterrows():
            ticks.append(
                TickData(
                    timestamp=row["timestamp"],
                    exchange=contract.exchange,
                    security_type=contract.security_type,
                    symbol=contract.symbol,
                    currency=contract.currency,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]) if pd.notna(row["volume"]) else 0,
                )
            )
        return ticks

    def read_hist_bars_from_db(self, contract: Contract, duration: str, bar_size: str) -> List[TickData]:
        # DB mode
        if not self.config.db_path:
            return []
        end_date = datetime.now()
        if "D" in duration:
            days = int(duration.split()[0])
            start_date = end_date - timedelta(days=days)
        elif "M" in duration:
            months = int(duration.split()[0])
            start_date = end_date - timedelta(days=months * 30)
        else:
            start_date = end_date - timedelta(days=_default_duration_days())
        query = (
            "SELECT timestamp, open, high, low, close, volume "
            "FROM historical_bars WHERE symbol = ? AND exchange = ? AND bar_size = ? "
            "AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp"
        )
        bars: List[TickData] = []
        with sqlite3.connect(self.config.db_path) as conn:
            rows = conn.execute(
                query, (contract.symbol, contract.exchange, bar_size, start_date.isoformat(), end_date.isoformat())
            ).fetchall()
            for ts, op, hi, lo, cl, vol in rows:
                bars.append(
                    TickData(
                        timestamp=pd.to_datetime(ts),
                        open=float(op),
                        high=float(hi),
                        low=float(lo),
                        close=float(cl),
                        volume=int(vol) if vol is not None else 0,
                    )
                )
        return bars

    def subscribe_market_data(
        self,
        contract: Contract,
        callback: Callable,
        market_data_type=None,
        snapshot: bool = False,
        regulatory_snapshot: bool = False,
        generic_tick_list=None,
    ) -> str:
        key = (contract.symbol, contract.exchange)
        if key in self._md_threads:
            return f"{contract.symbol}:{contract.exchange}"
        stop = threading.Event()
        self._md_stops[key] = stop

        def run_csv():
            logger.info(f"Fetching market data for {contract}")
            if self.config.csv_path is not None:
                df = pd.read_csv(self.config.csv_path)  # type: ignore[arg-type]
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df[(df["symbol"] == contract.symbol) & (df["exchange"] == contract.exchange)]
                df = df.sort_values("timestamp")
                logger.debug("CSV data shape: %s", df.shape)
                logger.debug("\n%s", df.head())
            else:
                tick_data = JioH5Adapter(self.config.h5_path, exchange=contract.exchange)
                df = tick_data.tick_df(contract.symbol, contract.strike, contract.option_right, contract.expiry)
                logger.debug("H5 data shape: %s", df.shape)
                logger.debug("\n%s", df.head())

            for _, row in df.iterrows():
                if stop.is_set():
                    break
                tick = TickData(
                    timestamp=row["timestamp"],
                    exchange=row.get("exchange", contract.exchange),
                    security_type=row.get("security_type", contract.security_type),
                    currency=row.get("currency", contract.currency),
                    symbol=row.get("symbol", contract.symbol),
                    bid=row.get("bid"),
                    ask=row.get("ask"),
                    last=row.get("last", row.get("close")),
                    volume=int(row.get("volume")) if pd.notna(row.get("volume")) else None,
                )
                callback(tick)
                if self.config.emit_interval_s:
                    time.sleep(self.config.emit_interval_s)

        def run_db():
            last_ts: Optional[str] = None
            while not stop.is_set():
                with sqlite3.connect(self.config.db_path) as conn:  # type: ignore[arg-type]
                    conn.row_factory = sqlite3.Row
                    if last_ts is None:
                        sql = "SELECT * FROM tick_data WHERE symbol = ? AND exchange = ? ORDER BY timestamp ASC LIMIT 1"
                        rows = conn.execute(sql, (contract.symbol, contract.exchange)).fetchall()
                    else:
                        sql = (
                            "SELECT * FROM tick_data WHERE symbol = ? AND exchange = ? "
                            "AND timestamp > ? ORDER BY timestamp ASC"
                        )
                        rows = conn.execute(sql, (contract.symbol, contract.exchange, last_ts)).fetchall()
                for r in rows:
                    last_ts = r["timestamp"]
                    tick = TickData(
                        timestamp=pd.to_datetime(r["timestamp"]),
                        exchange=r["exchange"],
                        security_type=r["security_type"],
                        currency=r["currency"],
                        symbol=r["symbol"],
                        bid=r["bid"],
                        ask=r["ask"],
                        last=r["last"],
                        volume=r["volume"],
                    )
                    callback(tick)
                time.sleep(self.config.poll_interval_s)

        def run():
            try:
                if self.mode == "csv" or self.mode == "h5":
                    run_csv()
                else:
                    run_db()
            finally:
                self._md_threads.pop(key, None)
                self._md_stops.pop(key, None)

        t = threading.Thread(target=run, daemon=True)
        self._md_threads[key] = t
        t.start()
        return f"{contract.symbol}:{contract.exchange}"

    def unsubscribe_market_data(self, subscription_id: str) -> bool:
        # Subscription IDs are "SYMBOL:EXCHANGE" (see subscribe_market_data)
        symbol, _, exchange = subscription_id.rpartition(":")
        key = (symbol, exchange)
        if key in self._md_stops:
            self._md_stops[key].set()
            return True
        return False

    # ---- Orders ----
    def submit_order(self, contract: Contract, order: Order) -> str:
        order_id = str(self._next_order_id)
        self._next_order_id += 1
        self._orders[order_id] = {
            "contract": contract,
            "order": order,
            "status": "Submitted",
            "created_at": datetime.now(),
        }
        # Simulated exchange latency: fill shortly after acknowledgement, which
        # drives the same order_status callback path as a real broker.
        self._update_order_status(order_id, OrderStatus.FILLED, self.config.fill_delay_s)
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        entry = self._orders.get(order_id)
        if entry is None:
            return False
        # A terminal order cannot be cancelled; saying otherwise would let the
        # recorded status flip from Filled back to Cancelled.
        if entry.get("status") in (OrderStatus.FILLED, OrderStatus.CANCELLED):
            logger.info(f"Order {order_id} is already {entry['status']}; cancel rejected")
            return False
        self._update_order_status(order_id, OrderStatus.CANCELLED, self.config.fill_delay_s)
        return True

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._orders.get(order_id, {"status": "Unknown"})

    def get_all_orders(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())

    # ---- Positions/Accounts (stubbed) ----
    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_account_info(self) -> Dict[str, Any]:
        return {
            "account_id": "PAPER",
            "cash_balance": 1_000_000.0,
            "buying_power": 1_000_000.0,
            "total_value": 1_000_000.0,
            "equity": 1_000_000.0,
        }

    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        raise NotImplementedError

    def get_greeks(self, contract: Contract) -> Dict[str, Any]:
        raise NotImplementedError

    def get_market_data_subscriptions(self) -> List[str]:
        return [f"{symbol}:{exchange}" for symbol, exchange in self._md_threads]

    def set_market_data_type(self, market_data_type: str) -> bool:
        # Paper broker replays recorded data; the market data type has no effect.
        return True

    def _fill_price(self, order: Order) -> float:
        """Price this simulated venue fills an order at.

        The reference is the order's own price (limit price, or the stop price
        for stop orders). Slippage is a concession, so it works against the
        trader: buys fill higher, sells fill lower.
        """
        reference = order.limit_price if order.limit_price is not None else order.stop_price
        if reference is None:
            logger.warning(
                "No reference price on %s order; filling at 0.0. Attach a price to the order "
                "so fills can be priced.",
                order.order_type.value,
            )
            return 0.0

        slippage = float(self.config.slippage_per_fill or 0.0)
        if not slippage:
            return float(reference)
        direction = 1.0 if order.action == OrderAction.BUY else -1.0
        return max(0.0, float(reference) + direction * slippage)

    def _update_order_status(self, order_id: str, status: OrderStatus, delay: float = 0) -> None:
        """Queue an order status update."""

        def update_and_cleanup():
            try:
                time.sleep(delay)
                if order_id in self._orders:
                    entry = self._orders[order_id]
                    entry.update({"status": status})
                    if status == OrderStatus.FILLED:
                        order = entry["order"]
                        entry.update(
                            {
                                "filled": order.quantity,
                                "remaining": 0,
                                "avg_fill_price": self._fill_price(order),
                            }
                        )
                    self.trigger_callback("order_status", order_id, entry)
            except Exception as e:
                logger.error(f"Error in order status update for {order_id}: {e}")

        if delay > 0:
            thread = threading.Thread(target=update_and_cleanup, daemon=True)
            thread.start()
        else:
            # No latency to simulate: report synchronously rather than paying for
            # a thread per order. OrderManager buffers a status that lands before
            # submit_order() has returned.
            update_and_cleanup()
