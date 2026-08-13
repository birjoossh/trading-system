"""
JioH5Adapter: Adapter for Jio HDF5 data format.

This module provides an interface to read and process HDF5 files containing
market data in the Jio format, including tick data, spot prices, and options data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def to_pandas_freq(bar_size: str) -> str:
    """Normalize bar sizes ("1H", "1 hour", "5 mins", "1min") to pandas offset aliases."""
    s = str(bar_size).strip().lower().replace(" ", "")
    for suffix, alias in (("hours", "h"), ("hour", "h"), ("mins", "min"), ("secs", "s"), ("sec", "s")):
        if s.endswith(suffix):
            return s[: -len(suffix)] + alias
    return s


class JioH5Adapter:
    # Reads daily .h5 with '/tick_data' and exposes:
    # spot_series(), futures_series(), options_table().

    def __init__(self, h5_path: Path, exchange: str):
        self.exchange = exchange
        if not h5_path.exists():
            raise FileNotFoundError(h5_path)
        self.h5_path = h5_path
        with pd.HDFStore(h5_path, mode="r") as store:
            self.keys = list(store.keys())

    def _read_tick(self) -> pd.DataFrame:
        with pd.HDFStore(self.h5_path, mode="r") as store:
            key = "/tick_data" if "/tick_data" in self.keys else "tick_data"
            df = store[key]
        df = df.copy()
        df.columns = [str(c).strip() for c in df.columns]

        ts_cands = ["Timestamp", "timestamp", "time", "datetime", "DateTime", "ts"]
        px_cands = ["Close", "close", "ltp", "LTP", "price", "Price", "last", "Last"]

        def first(ss):
            for c in ss:
                if c in df.columns:
                    return c

        ts_c = first(ts_cands)
        px_c = first(px_cands)
        if ts_c is None or px_c is None:
            raise ValueError("H5 missing timestamp/price columns")

        ts = pd.to_datetime(df[ts_c])
        df.index = ts
        df["close"] = pd.to_numeric(df[px_c], errors="coerce")

        # normalize likely columns
        if "strike" in df.columns:
            df["Strike"] = pd.to_numeric(df["strike"], errors="coerce")
        for c in ("STRIKE", "StrikePrice", "strike_price"):
            if c in df.columns:
                df["Strike"] = pd.to_numeric(df[c], errors="coerce")
        for c in ("option_type", "OptionType", "right", "cp", "CALLPUT", "type", "instrumenttype"):
            if c in df.columns:
                s = df[c].astype(str).str.upper().replace({"CALL": "CE", "PUT": "PE", "C": "CE", "P": "PE"})
                df["OptionType"] = s
                break
        for c in ("expiry", "Expiry", "expiry_date", "maturity", "expdate"):
            if c in df.columns:
                df["Expiry"] = pd.to_datetime(df[c], errors="coerce").dt.date
                break
        for c in ("underlying", "underlying_price", "underlying_ltp", "spot", "index_price"):
            if c in df.columns:
                df["Underlying"] = pd.to_numeric(df[c], errors="coerce")
                break
        for c in ("instrument", "ptype", "segment", "itype", "product", "sec_type"):
            if c in df.columns:
                df["Instr"] = df[c].astype(str).str.upper()
                break

        # Stable sort: several ticks can share a timestamp, and the "last" tick of
        # a bar is then decided by tie order. A stable sort keeps the feed order
        # from the file, so bar aggregation is reproducible; the default
        # quicksort leaves it unspecified.
        return df.sort_index(kind="stable")

    # ----- public API -----
    def spot_series(self, bar_length: str) -> pd.Series:
        df = self._read_tick()
        # 1) If Underlying column exists, use it
        if "Underlying" in df.columns and df["Underlying"].notna().any():
            return df["Underlying"].groupby(pd.Grouper(freq=bar_length)).last().dropna()

        # 2) Prefer explicit EQ rows for spot in this H5 layout
        base = df.copy()
        if "OptionType" in base.columns:
            base = base[base["OptionType"].astype(str).str.upper().eq("EQ")]
        if "Strike" in base.columns:
            # treat NaN or 0 as "no strike" for spot rows
            base = base[base["Strike"].isna() | (base["Strike"] == 0)]

        if not base.empty:
            return base["close"].groupby(pd.Grouper(freq=bar_length)).last().dropna()

        # 3) Fallback: synthetic spot from options
        return self._synthetic_spot_from_options()

    def _synthetic_spot_from_options(self) -> pd.Series:
        opt = self.options_table()
        piv = (
            opt.reset_index()
            .pivot_table(index=["Timestamp", "Strike"], columns="OptionType", values="close", aggfunc="last")
            .dropna(subset=["CE", "PE"])
        )
        piv["diff"] = (piv["CE"] - piv["PE"]).abs()
        idx = piv.groupby(level=0)["diff"].idxmin()
        picked = piv.loc[idx].reset_index(level=1)
        spot = picked["Strike"].astype(float)
        spot.name = "Underlying"
        spot.index.name = "Timestamp"
        return spot.sort_index()

    def futures_series(self, bar_length: str):
        df = self._read_tick()
        if "Instr" not in df.columns:
            return None
        fut = df[df["Instr"].str.contains("FUT", na=False)]
        if fut.empty:
            return None
        return fut["close"].groupby(pd.Grouper(freq=bar_length)).last().dropna()

    def options_table(self) -> pd.DataFrame:
        df = self._read_tick()
        if "OptionType" not in df.columns or "Strike" not in df.columns:
            raise ValueError("tick_data lacks OptionType/Strike")
        opt = df[df["OptionType"].isin(["CE", "PE"]) & df["Strike"].notna()].copy()
        if "Expiry" not in opt.columns:
            opt["Expiry"] = pd.NaT
        opt["Timestamp"] = opt.index.floor("1min")
        opt["Exchange"] = self.exchange
        # Resample and aggregate
        result = (
            opt.groupby(["tsym", "OptionType", "Strike", "Expiry", pd.Grouper(freq="1min")], observed=True)
            .agg(
                {
                    "price": "last",  # Last price
                    "volume": "sum",  # Sum of volume
                    "lot": "last",  # Keep the last lot size
                    "Exchange": "last",
                }
            )
            .reset_index()
            .rename(columns={"tsym": "Symbol", "level_4": "timestamp"})
        )
        result.index = result["timestamp"]
        return result[["Symbol", "OptionType", "Strike", "Expiry", "price", "volume", "lot", "Exchange"]]

    def hist_ohlc(
        self,
        ticker: str = None,
        exchange: str = None,
        strike: int = None,
        opt_type: str = None,
        expiry: str = None,
        bar_length: str = "1min",
    ) -> pd.DataFrame:
        df = self._read_tick()

        df["exchange"] = self.exchange  # read from config, no hardcoded exchange

        if "tsym" not in df.columns:
            raise ValueError("tick_data lacks trading symbol column")

        base = df
        if ticker is not None:
            base = base[base["tsym"] == ticker]
        if exchange is not None:
            base = base[base["exchange"] == exchange]
        if opt_type is not None and "OptionType" in base.columns:
            base = base[base["OptionType"] == opt_type]
        if expiry is not None and "Expiry" in base.columns:
            expiry_date = pd.to_datetime(expiry, format="mixed").date()
            base = base[base["Expiry"] == expiry_date]

        if base.empty:
            return pd.DataFrame()

        base = base.copy()
        base.index.name = "timestamp"
        bar_length = to_pandas_freq(bar_length)
        ohlc = base.groupby([pd.Grouper(freq=bar_length), "OptionType", "Strike"]).agg(
            {"price": ["first", "max", "min", "last"], "volume": "sum"}
        )
        ohlc.columns = ["open", "high", "low", "close", "volume"]
        ohlc = ohlc.reset_index().dropna()
        return ohlc

    def tick_df(self, ticker: str = None, strike: int = None, opt_type: str = None, expiry: str = None) -> pd.DataFrame:
        df = self._read_tick()
        if ticker is not None:
            base = df[df["tsym"] == ticker].copy()
        else:
            expiry = pd.to_datetime(expiry, format="mixed").date()
            base = df[(df["strike"] == strike) & (df["type"] == opt_type) & (df["expiry"] == expiry)].copy()
        if base.empty:
            raise ValueError(f"tick data lacks data for {ticker} ticker")

        base.drop(columns=["iid", "price", "Expiry"], inplace=True)
        return base
