"""
Shared fixtures for the test suite.

IMPORTANT: the working directory is switched to the repo root at import time,
before any package import happens. `trading_core/config/config.py` builds its
module-level `settings` singleton by reading `config.yaml` from the current
working directory, so the chdir has to happen before collection imports it.
"""

import os
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
os.chdir(REPO_ROOT)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from helpers import NIFTY_SYMBOL, make_chain, make_tick  # noqa: E402

H5_PATH = REPO_ROOT / "unified_trading_platform" / "examples" / "2024-01-02.h5"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def h5_path() -> Path:
    if not H5_PATH.exists():
        pytest.skip("bundled sample H5 not available")
    return H5_PATH


@pytest.fixture(scope="session")
def raw_h5(h5_path) -> pd.DataFrame:
    """The H5 tick log read straight through pandas — the independent oracle.

    Deliberately does NOT go through JioH5Adapter: tests compare the adapter's
    output against this, so it must not share the adapter's code path.
    """
    with pd.HDFStore(h5_path, mode="r") as store:
        key = "/tick_data" if "/tick_data" in store.keys() else "tick_data"
        df = store[key]
    df = df.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@pytest.fixture(scope="session")
def raw_spot_ticks(raw_h5) -> pd.DataFrame:
    """Underlying (EQ) ticks only, indexed by timestamp."""
    spot = raw_h5[raw_h5["tsym"].astype(str) == NIFTY_SYMBOL].copy()
    # Stable sort so ties on identical timestamps keep feed order, matching the
    # adapter's own ordering — otherwise "last tick of the minute" is ambiguous.
    return spot.set_index("timestamp").sort_index(kind="stable")


@pytest.fixture(scope="session")
def raw_option_ticks(raw_h5) -> pd.DataFrame:
    """Option (CE/PE) ticks only, indexed by timestamp."""
    opts = raw_h5[raw_h5["type"].astype(str).isin(["CE", "PE"])].copy()
    return opts.set_index("timestamp").sort_index(kind="stable")


@pytest.fixture
def tmp_db(tmp_path) -> str:
    return str(tmp_path / "test_trading.db")


@pytest.fixture
def trading_system(tmp_db):
    """A TradingSystem with no brokers attached, on a throwaway database."""
    from unified_trading_platform.trading_core.trading_system import TradingSystem

    ts = TradingSystem(db_path=tmp_db)
    yield ts
    ts.shutdown()


#: Simulated fill latency for tests — the production default is 1s, which would
#: add a full second to every order assertion.
TEST_FILL_DELAY_S = 0.05


@pytest.fixture
def paper_system(tmp_db, h5_path):
    """A TradingSystem with the paper broker connected against the sample H5."""
    from unified_trading_platform.trading_core.trading_system import TradingSystem

    ts = TradingSystem(db_path=tmp_db)
    assert ts.add_broker(
        name="paper", broker_type="paper", h5_path=str(h5_path), fill_delay_s=TEST_FILL_DELAY_S
    )
    yield ts
    ts.shutdown()


@pytest.fixture
def fill_delay() -> float:
    return TEST_FILL_DELAY_S


@pytest.fixture
def chain_factory():
    return make_chain


@pytest.fixture
def tick_factory():
    return make_tick
