"""
PaperBroker: Simulated broker that replays market data and accepts orders.
Supports CSV and SQLite DB as data sources for historical bars and tick replay.
"""
 # to do 
 ## implement the h5 file tick processing
from __future__ import annotations

from enum import unique
from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import threading
import time
import sqlite3
from pathlib import Path
from unified_trading_platform.trading_core.utils.utils import fromYYMMDD

from click import option
import pandas as pd

from ..base_broker import (
    BrokerInterface,
    Contract,
    Order,
    BarData,
    TickData,
    SecurityType,
    OptionChain,
    OrderStatus
)

from .jio import JioH5Adapter

@dataclass
class PaperBrokerConfig:
    csv_path: Optional[Path] = None
    db_path: Optional[Path] = None
    h5_path: Optional[Path] = None
    emit_interval_s: float = 0.5


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

            emit_interval_s=kwargs.get("emit_interval_s", 0.5),
        )
        self.mode="csv" if self.config.csv_path else "db" if self.config.db_path else "h5"
        self._md_threads: Dict[tuple, threading.Thread] = {}
        self._md_stops: Dict[tuple, threading.Event] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}
        self._next_order_id = 1

    # ---- Connection Management ----
    def connect(self, **kwargs) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> bool:
        for stop in list(self._md_stops.values()):
            stop.set()
        self.is_connected = False
        return True

    # ---- Option Chain ----
    def get_option_chain(self, contract: Contract):
        # format date
        expiry_date = pd.to_datetime(contract.expiry).date()

        df = JioH5Adapter(self.config.h5_path)
        option_chain = df.options_table()
        
        if not option_chain.empty:
            strikes = option_chain['Strike'].unique()
            expiration_dates = option_chain['Expiry'].unique()
            option_types = option_chain['OptionType'].unique()
            
            # More efficient: nested defaultdict
            ltp = defaultdict(lambda: defaultdict(dict))
            
            # Filter once for the contract expiry
            filtered_chain = option_chain[option_chain['Expiry'] == expiry_date] 

            # Iterate through filtered data
            for idx, row in filtered_chain.iterrows():
                timestamp = idx
                op_type = row['OptionType']
                strike = row['Strike']
                price = row['Close']
                
                # Automatically creates nested structure
                ltp[timestamp][op_type][strike] = price
            
            # Convert to regular dict (optional)
            ltp = {ts: {ot: dict(strikes) for ot, strikes in types.items()} 
                for ts, types in ltp.items()}
            
            oc = OptionChain(
                underlying_symbol=contract.symbol,
                strikes=strikes,
                expiration_dates=expiration_dates,
                type=option_types,
                ltp=ltp,
                underlying_contract=contract,
                tick_size=None, # fixme: where to find this?
                trading_class=contract.trading_class,
                options=option_chain
            )
        for ts in ltp.keys():
            call_oc = OptionChain(
                underlying_symbol=contract.symbol,
                strikes= list(ltp[ts]['CE'].keys()),
                expiration_dates=expiration_dates,
                type=option_types,
                ltp = ltp[ts]['CE'],
                underlying_contract=contract,
                tick_size=None, # fixme: where to find this?
                trading_class=contract.trading_class,
                options=option_chain
            )

            put_oc = OptionChain(
                underlying_symbol=contract.symbol,
                strikes= list(ltp[ts]['PE'].keys()),
                expiration_dates=expiration_dates,
                type=option_types,
                ltp = ltp[ts]['PE'],
                underlying_contract=contract,
                tick_size=None, # fixme: where to find this?
                trading_class=contract.trading_class,
                options=option_chain
            )
            return call_oc, put_oc
            #callback(call_oc)
            #callback(put_oc)

    # ---- Market Data ----
    def get_historical_data(self, contract: Contract, duration: str,
                          bar_size: str, what_to_show: str = "TRADES") -> List[BarData]:
        print("Fetching historica data", contract)
        df = df = pd.DataFrame()
        if self.mode == "csv":
            if not self.config.csv_path:
                return []
            df = pd.read_csv(self.config.csv_path)
            df["timestamp"] = pd.to_datetime(df["timestamp"])  # required column
            df = df[(df["symbol"] == contract.symbol) & (df["exchange"] == contract.exchange)]
            df = df.sort_values("timestamp")
            # Filter by duration ending at last available timestamp
        elif self.mode == 'h5':
            ja = JioH5Adapter(self.config.h5_path)
            df = ja.hist_ohlc(ticker=contract.symbol, exchange = contract.exchange, strike=contract.strike, \
                opt_type=contract.right, expiry=contract.expiry, bar_length=bar_size)

        if not df.empty:
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
                start_dt = end_dt - timedelta(days=30)
            df = df[df["timestamp"] >= start_dt]
            bars: List[BarData] = []
            for _, row in df.iterrows():
                bars.append(BarData(
                    timestamp=row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]) if pd.notna(row["volume"]) else 0,
                ))
            return bars
        
        # DB mode
        elif not self.config.db_path:
            return []
        end_date = datetime.now()
        if 'D' in duration:
            days = int(duration.split()[0])
            start_date = end_date - timedelta(days=days)
        elif 'M' in duration:
            months = int(duration.split()[0])
            start_date = end_date - timedelta(days=months*30)
        else:
            start_date = end_date - timedelta(days=30)
        query = (
            "SELECT timestamp, open, high, low, close, volume "
            "FROM historical_bars WHERE symbol = ? AND exchange = ? AND bar_size = ? "
            "AND timestamp >= ? AND timestamp <= ? ORDER BY timestamp"
        )
        bars: List[BarData] = []
        with sqlite3.connect(self.config.db_path) as conn:
            rows = conn.execute(query, (
                contract.symbol, contract.exchange, bar_size,
                start_date.isoformat(), end_date.isoformat()
            )).fetchall()
            for ts, op, hi, lo, cl, vol in rows:
                bars.append(BarData(
                    timestamp=pd.to_datetime(ts),
                    open=float(op), high=float(hi), low=float(lo), close=float(cl),
                    volume=int(vol) if vol is not None else 0,
                ))
        return bars

    def subscribe_market_data(self, contract: Contract, callback: Callable) -> bool:
        key = (contract.symbol, contract.exchange)
        if key in self._md_threads:
            return True
        stop = threading.Event()
        self._md_stops[key] = stop

        def run_csv():
            print("Fetching market data for", contract)
            print("self.config.csv_path = ", self.config.csv_path)
            if self.config.csv_path != None:
                df = pd.read_csv(self.config.csv_path)  # type: ignore[arg-type]
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df[(df["symbol"] == contract.symbol) & (df["exchange"] == contract.exchange)]
                df = df.sort_values("timestamp")
            else:
                tick_data = JioH5Adapter(self.config.h5_path)
                df = tick_data.tick_df(contract.symbol, contract.strike, contract.right, contract.expiry)
                print("df = ", df)
                
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
                time.sleep(self.config.emit_interval_s)

        def run_db():
            last_ts: Optional[str] = None
            while not stop.is_set():
                with sqlite3.connect(self.config.db_path) as conn:  # type: ignore[arg-type]
                    conn.row_factory = sqlite3.Row
                    if last_ts is None:
                        sql = (
                            "SELECT * FROM tick_data WHERE symbol = ? AND exchange = ? ORDER BY timestamp ASC LIMIT 1"
                        )
                        rows = conn.execute(sql, (contract.symbol, contract.exchange)).fetchall()
                    else:
                        sql = (
                            "SELECT * FROM tick_data WHERE symbol = ? AND exchange = ? AND timestamp > ? ORDER BY timestamp ASC"
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
                time.sleep(self.config.emit_interval_s)

        def run():
            try:
                if self.mode == "csv" or self.mode == 'h5':
                    run_csv()
                else:
                    run_db()
            finally:
                self._md_threads.pop(key, None)
                self._md_stops.pop(key, None)

        t = threading.Thread(target=run, daemon=True)
        self._md_threads[key] = t
        t.start()
        return True

    def unsubscribe_market_data(self, contract: Contract) -> bool:
        key = (contract.symbol, contract.exchange)
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
        #delayed status update to trigger order status update callback
        self._update_order_status(order_id, OrderStatus.FILLED, 1)
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        if order_id in self._orders:
            #delayed status update to trigger order status update callback
            self._update_order_status(order_id, OrderStatus.CANCELLED, 1)
            return True
        return False

    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        return self._orders.get(order_id, {"status": "Unknown"})

    def get_all_orders(self) -> List[Dict[str, Any]]:
        return list(self._orders.values())

    # ---- Positions/Accounts (stubbed) ----
    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def get_account_info(self) -> Dict[str, Any]:
        return {"account": "PAPER", "cash": 1_000_000}

    def get_contract_details(self, contract: Contract) -> Dict[str, Any]:
        raise NotImplementedError

    def get_greeks(self, contract: Contract) -> Dict[str, Any]:
        raise NotImplementedError
        
    def get_market_data_subscriptions(self) -> List[str]:
        raise NotImplementedError
    
    def set_market_data_type(self, market_data_type: str) -> bool:
        raise NotImplementedError
        
    def _update_order_status(self, order_id: str, status: OrderStatus, delay: float = 0) -> None:
        """Queue an order status update."""
        def update_and_cleanup():
            try:
                time.sleep(delay)
                if order_id in self._orders:
                    self._orders[order_id].update({"status": status})
                    self.trigger_callback("order_status", order_id, self._orders[order_id])
            except Exception as e:
                self.logger.error(f"Error in order status update for {order_id}: {e}")
            finally:
                # Ensure thread is cleaned up
                if hasattr(threading.current_thread(), '_stop'):
                    threading.current_thread()._stop()
        if delay > 0:
            thread = threading.Thread(target=update_and_cleanup, daemon=True)
            thread.start()
        else:
            update_and_cleanup()