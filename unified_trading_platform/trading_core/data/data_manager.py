"""
Data manager for handling market data from various sources.
Provides unified interface for historical and real-time data.
"""

import pandas as pd
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import asdict
import sqlite3

from trading_core.brokers.base_broker import BrokerInterface, Contract, BarData, TickData


class DataManager:
    """Manages market data storage and retrieval"""

    def __init__(self, db_path: str = "trading_data.db"):
        self.db_path = db_path
        self.brokers: Dict[str, BrokerInterface] = {}
        self.subscribers: Dict[str, List[Callable]] = {}
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database for data storage"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS historical_bars (
                    symbol TEXT,
                    exchange TEXT,
                    security_type TEXT,
                    currency TEXT,
                    timestamp TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume INTEGER,
                    bar_size TEXT,
                    PRIMARY KEY (symbol, exchange, timestamp, bar_size)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS tick_data (
                    exchange TEXT,
                    security_type TEXT,
                    currency TEXT,
                    symbol TEXT,
                    timestamp TEXT,
                    bid REAL,
                    ask REAL,
                    last REAL,
                    volume INTEGER,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)

    def _get_broker(self, name: str):
        """Add a broker for data retrieval"""
        return self.brokers[name]

    def _bars_to_dataframe(self, bars: List[BarData]):
        df = pd.DataFrame([asdict(bar) for bar in bars])
        df.set_index('timestamp', inplace=True)
        return df

    def add_broker(self, name: str, broker: BrokerInterface):
        """Add a broker for data retrieval"""
        self.brokers[name] = broker

    def get_historical_data(self, contract: Contract, duration: str, bar_size: str,
                          broker_name: Optional[str] = None, use_cache: bool = True) -> pd.DataFrame:
        """Get historical data, optionally from cache"""

        # Check cache first
        if use_cache:
            cached_data = self._get_cached_bars(contract, bar_size, duration)
            if not cached_data.empty:
                return cached_data

        # Get from broker
        broker = self._get_broker(broker_name)
        bars = broker.get_historical_data(contract, duration, bar_size)
        # Convert to DataFrame
        df = self._bars_to_dataframe(bars)

        # Cache the data
        if use_cache and not df.empty:
            self._cache_bars(df)

        return df

    def _cache_bars(self, df: pd.DataFrame):
        with sqlite3.connect(self.db_path) as conn:
            df.to_sql('historical_bars', conn, if_exists='append', index=True, index_label="timestamp")

    def _get_cached_bars(self, contract: Contract, bar_size: str, duration: str) -> pd.DataFrame:
        """Retrieve cached bar data"""
        # Calculate date range based on duration
        end_date = datetime.now()
        if 'D' in duration:
            days = int(duration.split()[0])
            start_date = end_date - timedelta(days=days)
        elif 'M' in duration:
            months = int(duration.split()[0])
            start_date = end_date - timedelta(days=months*30)  # Approximate
        else:
            start_date = end_date - timedelta(days=30)  # Default

        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM historical_bars 
            WHERE symbol = ? AND exchange = ? AND bar_size = ?
            AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """

        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(
                query,
                conn,
                params=[contract.symbol, contract.exchange, bar_size,
                       start_date.isoformat(), end_date.isoformat()],
                parse_dates=['timestamp'],
                index_col='timestamp'
            )
        return df

    def subscribe_real_time_data(self, contract: Contract, callback: Callable,
                                 broker_name: Optional[str] = None) -> bool:
        """Subscribe to real-time market data and store in DB and/or notify subscribers.

        Args:
            contract (Contract): Instrument to subscribe to.
            callback (Callable): Function to call with each TickData.
            broker_name (str, optional): Which broker to use. Defaults to only/first one.

        Returns:
            bool: True if subscription was successful.
        """
        broker = self._get_broker(broker_name)

        def storage_and_user_callback(tick_data: TickData):
            # Store tick data
            self._store_tick_data(tick_data)
            # Forward to user's callback
            callback(tick_data)
        # Use broker to subscribe
        return broker.subscribe_market_data(contract, storage_and_user_callback)

    def _store_tick_data(self, tick_data):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO tick_data 
                (exchange, security_type, symbol, currency, timestamp, bid, ask, last, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tick_data.exchange,
                    tick_data.security_type,
                    tick_data.symbol,
                    tick_data.currency,
                    tick_data.timestamp,
                    tick_data.bid,
                    tick_data.ask,
                    tick_data.last,
                    tick_data.volume
                )
            )