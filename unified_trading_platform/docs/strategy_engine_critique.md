# Strategy Engine Logic Critique

## 1. Critical Logic Issues

### A. Dangerous Price Fallback in `live_engine.py`
In `_check_entry_conditions` and `_update_positions_with_tick`, there is a fallback mechanism when option premium lookup fails:

```python
# live_engine.py:190 & 420
price_for_pnl = (
    option_premium
    if option_premium is not None
    else (tick_data.close or tick_data.last or ...)
)
```

**The Issue**: `tick_data` typically represents the **Underlying** (e.g., Index at 25,000) when the strategy is driven by underlying ticks. If the option chain lookup fails (returns `None`), the code assigns the Index Value (25,000) as the Option Price (expected ~100).
**Consequence**: 
-   **Entries**: Executing trades at phantom prices (paper trading) or miscalculating position sizing.
-   **PnL**: Massive artificial PnL spikes causing stop-loss/target triggers instantly.

**Recommendation**: 
-   If `option_premium` is `None`, **skip** the update or entry. Do not use `tick_data` unless `tick_data` is explicitly confirmed to be the specific option contract (which is not the case here).

### B. Hardcoded Expiry Logic in `strategy_utils.py`
The expiry calculation functions contain hardcoded dates specific to Indian Markets (NSE) changes:

```python
def weekly_expiry_for(date: dt.date) -> dt.date:
    switch = dt.date(2025, 9, 1)  # Magic Date
    wd = 1 if date >= switch else 3  # Magic Weekday (Tue/Thu)
```

**The Issue**: This makes the generic `strategy_utils` module specific to one exchange/regime.
**Recommendation**: Move expiry rules to `config.py` or an exchange-specific calendar adapter.

## 2. Performance & Efficiency

### A. Iterative Greeks Calculation in `greeks_helper.py`
`compute_iv_delta_for_chain` uses a Python loop to iterate over the DataFrame:

```python
for _, row in df.iterrows():
    # ... bs_price / bs_delta calls
```

**The Issue**: `iterrows` is extremely slow. For large chains (or frequent updates), this will bottleneck the strategy engine.
**Recommendation**: Use `pandas.DataFrame.apply` or vectorized numpy arrays. While `iv_from_price` (bisection) is hard to fully vectorize, `bs_delta` and `bs_price` can definitely be vectorized.

### B. O(N log N) Sorting in `strikes.py`
`select_strike` uses sorting to find the nearest strike:

```python
df.iloc[(df["strike"] - target).abs().argsort()].iloc[0]["strike"]
```

**The Issue**: Sorting the whole array is $O(N \log N)$.
**Recommendation**: Use `(df["strike"] - target).abs().idxmin()` which is $O(N)$ and more readable.

## 3. Architecture & State

### A. Indefinite Legend Growth
`UnifiedStrategyEngine.live_legs` is a list that is only appended to (via re-entries).
**The Issue**: In a continuous running system (e.g., 24/7 crypto or multi-day server), this list will grow indefinitely.
**Recommendation**: Implement a cleanup / archiving mechanism for closed legs (e.g., move to `history` list after N minutes of closure).

## 4. Minor Bugs

-   **Strike Selection Fallback**: In `_detect_step`, `diffs.mode()` can be empty if all strikes are unique but no repeats in differences (unlikely for regular chains, but possible).
-   **Underlying calculation**: `tick_data.close` is used as current underlying price. In live trading, `last` (LTP) is usually preferred over `close` (which might be prev day close if not updated). The code uses `tick_data.close or tick_data.last`. It should probably prioritize `last`.

## Summary of Recommendations
1.  **FIX CRITICAL**: Remove `tick_data` fallback for option prices.
2.  **REFACTOR**: Externalize expiry rules.
3.  **OPTIMIZE**: Vectorize Greeks calculation.
4.  **CLEANUP**: Use `idxmin` for strike selection.
