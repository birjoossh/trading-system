"""
Data manager for handling market data from various sources.
Provides unified interface for historical and real-time data.
"""

import pandas as pd
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta
import sqlite3

from trading_system.brokers.base_broker import BrokerInterface, Contract


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
                    symbol TEXT,
                    timestamp TEXT,
                    bid REAL,
                    ask REAL,
                    last REAL,
                    volume INTEGER,
                    PRIMARY KEY (symbol, timestamp)
                )
            """)

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
            self._cache_bars(contract, bars, bar_size)

        return df

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