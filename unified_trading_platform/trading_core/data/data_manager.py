"""
Data manager for handling market data from various sources.
Provides unified interface for historical and real-time data.
"""

import pandas as pd
from typing import List, Dict, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import asdict
import sqlite3

from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.data_models import TickData, OptionChain, Contract
from unified_trading_platform.trading_core.brokers.base_broker import BrokerInterface

# Initialize logger
logger = get_logger(__name__)


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

    def _get_broker(self, name: Optional[str]) -> BrokerInterface:
        """Resolve a broker by name, falling back to the sole registered broker."""
        if not self.brokers:
            raise ValueError("No brokers registered")
        if name is None:
            if len(self.brokers) == 1:
                return next(iter(self.brokers.values()))
            raise ValueError(f"broker_name is required when multiple brokers are registered: {list(self.brokers)}")
        if name not in self.brokers:
            raise ValueError(f"Broker '{name}' not found. Available: {list(self.brokers)}")
        return self.brokers[name]

    def add_broker(self, name: str, broker: BrokerInterface):
        """Add a broker for data retrieval"""
        self.brokers[name] = broker

    def get_historical_data(
        self,
        contract: Contract,
        duration: str,
        bar_size: str,
        broker_name: Optional[str] = None,
        use_cache: bool = True,
    ) -> List[TickData]:
        """Get historical tick data

        Args:
            contract: The contract to get data for
            duration: Duration of data to fetch (e.g., '1 D', '1 W', '1 M')
            bar_size: Bar size (e.g., '1 min', '5 mins', '1 hour')
            broker_name: Optional name of the broker to use
            use_cache: Whether to use cached data if available

        Returns:
            List of TickData objects containing the historical data
        """
        # Check cache first
        if use_cache:
            cached_data = self._get_cached_bars(contract, bar_size, duration)
            if cached_data:  # Check if list is not empty
                return cached_data  # Already in List[TickData] format

        # Get from broker
        broker = self._get_broker(broker_name)
        bars = broker.get_historical_data(contract, duration, bar_size)

        # Cache the data if needed
        if use_cache and bars:
            self._cache_bars(bars)
        return bars  # Should already be List[TickData] from broker

    def get_option_chain(self, broker_name: Optional[str] = None, contract: Contract = None) -> OptionChain:
        broker = self._get_broker(broker_name)
        return broker.get_option_chain(contract)

    def _cache_bars(self, bars: List[TickData]):
        """Cache a list of TickData objects to the database

        Args:
            bars: List of TickData objects to cache
        """
        if not bars:
            return

        rows = [
            (
                bar.symbol,
                bar.exchange,
                bar.security_type.value if bar.security_type else None,
                bar.currency,
                bar.timestamp.isoformat(),
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                getattr(bar, "bar_size", "1 min"),
            )
            for bar in bars
        ]
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO historical_bars
                (symbol, exchange, security_type, currency, timestamp, open, high, low, close, volume, bar_size)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def _get_cached_bars(self, contract: Contract, bar_size: str, duration: str) -> List[TickData]:
        """Retrieve cached bar data as a list of TickData

        Args:
            contract: The contract to get data for
            bar_size: Bar size (e.g., '1 min', '5 mins')
            duration: Duration of data to fetch (e.g., '1 D', '1 W')

        Returns:
            List of TickData objects containing the historical data
        """
        # Calculate date range based on duration
        end_date = datetime.now()
        if "D" in duration:
            days = int(duration.split()[0])
            start_date = end_date - timedelta(days=days)
        elif "M" in duration:
            months = int(duration.split()[0])
            start_date = end_date - timedelta(days=months * 30)  # Approximate
        else:
            start_date = end_date - timedelta(days=30)  # Default

        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM historical_bars
            WHERE symbol = ? AND exchange = ? AND bar_size = ?
            AND timestamp >= ? AND timestamp <= ?
            ORDER BY timestamp
        """

        tick_data_list = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                query, [contract.symbol, contract.exchange, bar_size, start_date.isoformat(), end_date.isoformat()]
            )

            for row in cursor.fetchall():
                tick_data = TickData(
                    timestamp=pd.to_datetime(row[0]),
                    exchange=contract.exchange,
                    security_type=contract.security_type,
                    symbol=contract.symbol,
                    currency=contract.currency,
                    open=row[1],
                    high=row[2],
                    low=row[3],
                    close=row[4],
                    volume=row[5],
                )
                tick_data_list.append(tick_data)

        return tick_data_list

    def subscribe_real_time_data(
        self,
        contract: Contract,
        callback: Callable,
        broker_name: Optional[str] = None,
        store_data: bool = True,
    ) -> bool:
        """Subscribe to real-time market data
        Args:
            contract: Instrument to subscribe to
            callback: Function to call with each TickData
            broker_name: Which broker to use
            store_data: Whether to synchronously store data in DB (default True)
                        Set to False if using async/event system.
        """
        broker = self._get_broker(broker_name)

        if store_data:
            def storage_and_user_callback(tick_data: TickData):
                # Store tick data
                self._store_tick_data(tick_data)
                # Forward to user's callback
                callback(tick_data)
            
            final_callback = storage_and_user_callback
        else:
            final_callback = callback

        # Use broker to subscribe
        logger.info(f"Subscribing to market data for {asdict(contract)}")
        return broker.subscribe_market_data(contract, final_callback)

    def store_tick(self, tick_data: TickData):
        """Public method to store tick data (for external/async use)"""
        self._store_tick_data(tick_data)

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
                    tick_data.security_type.value
                    if hasattr(tick_data.security_type, "value")
                    else str(tick_data.security_type),
                    tick_data.symbol,
                    tick_data.currency,
                    tick_data.timestamp.isoformat(),
                    tick_data.bid,
                    tick_data.ask,
                    tick_data.last,
                    tick_data.volume,
                ),
            )
