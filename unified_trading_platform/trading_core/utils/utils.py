from __future__ import annotations
import datetime as dt
from pathlib import Path
import pandas as pd

FILL_MODEL = "close_same"   # kept for future use
TZ_OFFSET_MIN = 0           # set to 330 if your H5 is UTC and you want IST

def parse_time(t: str) -> dt.time:
    h, m = t.split(":"); return dt.time(int(h), int(m))

def ensure_dir(p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)

def nearest_ts(df: pd.DataFrame | pd.Series, ts: pd.Timestamp) -> pd.Timestamp:
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("DataFrame must be indexed by datetime")
    # robust to duplicates
    uniq = pd.DatetimeIndex(df.index.unique()).sort_values()
    pos = uniq.get_indexer([pd.Timestamp(ts)], method="nearest")[0]
    return uniq[pos]

"""
Convert date string from one format to another.
    formats_to_try = [
        "%Y-%m-%d",    # 2024-01-02
        "%d-%m-%Y",    # 02-01-2024
        "%m/%d/%Y",    # 01/02/2024
        "%Y%m%d",      # 20240102
        "%d/%m/%Y",    # 02/01/2024
        "%Y/%m/%d",    # 2024/01/02
        "%d.%m.%Y",    # 02.01.2024
        "%Y.%m.%d",    # 2024.01.02
        "%b %d, %Y",   # Jan 02, 2024
        "%B %d, %Y",   # January 02, 2024
    ]
"""
def fromYYMMDD(date_str: str, dest_format: str = "%Y-%m-%d") -> str:
    date_obj = dt.datetime.strptime(date_str, dest_format).date()
    if date_obj is None:
        raise ValueError(f"Could not parse date string: {date_str}")
    return date_obj.strftime(dest_format)