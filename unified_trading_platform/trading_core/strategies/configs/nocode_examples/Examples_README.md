# Examples – No‑Code Time‑Based Options Backtester

This folder contains **ready‑to‑run** JSON configs for common index‑options strategies. Pick a file and run it with the single‑file engine—no coding required.

---

## Quick start — run any example

```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/<file>.json \
  --out backtests/NIFTY_time_intraday_<TYPE>.csv
```

Replace `<file>.json` with one from the list below. Start with a **single trading day** to validate fills, then expand the date range.

---

## New per‑leg features (now supported)

- **Expiry per leg:** `"Weekly" | "NextWeekly" | "Monthly" | "NextMonthly"`.
- **Risk basis per leg:**
  - Targets/SL: `"premium_pts" | "premium_pct" | "underlying_pts" | "underlying_pct"`
  - Trailing on option premium: `"points" | "percent"`.
- **Example (leg snippet):**
```json
"risk": {
  "target": { "enabled": true,  "basis": "premium_pct",    "value": 25 },
  "sl":     { "enabled": true,  "basis": "premium_pct",    "value": 20 },
  "trail":  { "enabled": false, "basis": "points",         "value": 0 }
}
```
- **Re‑entry per leg:** configure independent rules for **Stop‑Loss** and **Target** triggers.
  - Modes: `RE_ASAP`, `RE_ASAP_REV`, `RE_COST`, `RE_COST_REV`, `RE_MOMENTUM`, `RE_MOMENTUM_REV`, `LAZY_LEG`
  - Cap: `max_count` per trigger (engine enforces ≤ 20). Optional `no_reentry_after` at strategy level.
  - **Example (leg snippet):**
```json
"reentry_on_sl":     { "enabled": true,  "mode": "RE_ASAP",     "max_count": 1 },
"reentry_on_target": { "enabled": true,  "mode": "RE_COST",     "max_count": 1 }
```

---

## Example index

| # | File | Idea | Entry → Exit | Strike selector | Square‑off |
|---|---|---|---|---|---|
| 1 | `atm_short_straddle_1100_1515.json` | Sell ATM CE + ATM PE (short straddle) | 11:00 → 15:15 | `STRIKE_TYPE: ATM` | Partial |
| 2 | `otm2_short_strangle_1100_1515.json` | Sell OTM2 CE + OTM2 PE (short strangle) | 11:00 → 15:15 | `STRIKE_TYPE: OTM2` | Partial |
| 3 | `iron_condor_otm2_otm4_complete.json` | OTM2 short strangle + OTM4 long wings (iron condor) | 10:30 → 15:10 | `OTM2` / `OTM4` | **Complete** |
| 4 | `call_credit_spread_bearish.json` | Bearish call credit spread (sell ATM CE, buy OTM2 CE) | 10:00 → 15:20 | `ATM` / `OTM2` | Complete |
| 5 | `put_debit_spread_bearish.json` | Bearish put debit spread (buy ITM1 PE, sell ATM PE) | 11:00 → 15:00 | `ITM1` / `ATM` | Partial |
| 6 | `closest_premium_100_strangle.json` | Sell CE+PE whose premium is closest to ₹100 | 10:45 → 15:10 | `CLOSEST_PREMIUM: 100` | Partial |
| 7 | `premium_le_60_strangle.json` | Sell CE+PE where premium ≤ ₹60 | 10:15 → 15:05 | `PREMIUM_LE: 60` | Partial |
| 8 | `atm_long_straddle_trail_be.json` | Buy ATM CE + ATM PE (trail to break‑even enabled) | 09:45 → 15:20 | `ATM` | Partial |
| 9 | `monthly_atm_short_straddle.json` | Monthly‑expiry short straddle (ATM CE+PE) | 11:00 → 15:10 | `ATM` | Partial |
| 10 | `iron_condor_deltarange_complete.json` | Delta‑based iron condor (sell ~25Δ CE/PE, buy ~10Δ wings) | 10:00 → 15:10 | `CLOSEST_DELTA: 25 / 10` | **Complete** |

> **Square‑off modes**  
> *Partial* = each leg exits on its own SL/Target or at time exit.  
> *Complete* = if any leg exits, **all** legs exit together at that minute.

---

## Detailed examples

### 1) ATM short straddle (baseline)
**File:** `atm_short_straddle_1100_1515.json`  
**What it does:** Sells ATM CE and PE to capture intraday decay; neutral bias.  
**Risk (in config):** Target 30%, SL 25% (basis: `premium_pct`, per leg). Trailing: disabled.  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/atm_short_straddle_1100_1515.json \
  --out backtests/NIFTY_time_intraday_ShortStrangle_ATM.csv
```

---

### 2) OTM2 short strangle
**File:** `otm2_short_strangle_1100_1515.json`  
**What it does:** Sells OTM2 CE/PE; lower gamma risk vs ATM, lower credit.  
**Risk:** Target 25%, SL 20% (basis: `premium_pct`, per leg).  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/otm2_short_strangle_1100_1515.json \
  --out backtests/NIFTY_time_intraday_ShortStrangle_OTM2.csv
```

---

### 3) Iron condor (OTM2 short, OTM4 wings) — Complete exit
**File:** `iron_condor_otm2_otm4_complete.json`  
**What it does:** Short OTM2 strangle hedged with long OTM4 wings; exits as a package.  
**Risk:** Shorts Target 25%, SL 20% (basis: `premium_pct`); wings: exits disabled.  
**Re-entry:** Shorts → SL: `RE_ASAP` (1x), Target: `RE_COST` (1x); Wings: disabled.  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/iron_condor_otm2_otm4_complete.json \
  --out backtests/NIFTY_time_intraday_IronCondor_OTM2.csv
```

---

### 4) Call credit spread (bearish)
**File:** `call_credit_spread_bearish.json`  
**What it does:** Sell ATM CE; buy OTM2 CE hedge (defined‑risk bearish view).  
**Risk:** Short CE Target 30%, SL 25% (basis: `premium_pct`); long CE: exits disabled.  
**Re-entry:** Short CE → SL: `RE_ASAP` (1x), Target: `RE_COST` (1x); Long CE: disabled.  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/call_credit_spread_bearish.json \
  --out backtests/NIFTY_time_intraday_CALLCredit_Spread.csv
```

---

### 5) Put debit spread (bearish, long premium)
**File:** `put_debit_spread_bearish.json`  
**What it does:** Buy ITM1 PE; sell ATM PE to reduce cost; partial exits.  
**Risk:** Long PE Target 80%, SL 40% (basis: `premium_pct`); short PE: exits disabled.  
**Re-entry:** Long PE → SL: `RE_ASAP` (1x), Target: `RE_COST` (1x); Short PE: disabled.  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/put_debit_spread_bearish.json \
  --out backtests/NIFTY_time_intraday_PutDebit_Spread.csv
```

---

### 6) Closest‑premium strangle (₹100 each side)
**File:** `closest_premium_100_strangle.json`  
**What it does:** Chooses CE & PE whose option price is closest to ₹100; keeps daily risk normalized.  
**Risk:** Target 25%, SL 20% (basis: `premium_pct`, per leg).  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/closest_premium_100_strangle.json \
  --out backtests/NIFTY_time_intraday_ClosestPremium.csv
```

---

### 7) Premium‑cap strangle (premium ≤ ₹60)
**File:** `premium_le_60_strangle.json`  
**What it does:** Picks strikes where premium is ≤ ₹60 on both sides.  
**Risk:** Target 22%, SL 18% (basis: `premium_pct`, per leg).  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/premium_le_60_strangle.json \
  --out backtests/NIFTY_time_intraday_LowerPremium.csv
```

---

### 8) ATM long straddle with trail‑to‑BE
**File:** `atm_long_straddle_trail_be.json`  
**What it does:** Buys ATM CE & PE; `trail_to_be` enabled in config for future support.  
**Risk:** Target 80%, SL 35% (basis: `premium_pct`, per leg). Per‑leg trailing: disabled; config includes `trail_to_be` support.  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/atm_long_straddle_trail_be.json \
  --out backtests/NIFTY_time_intraday_LongStraddle_Trail.csv
```

---

### 9) Monthly ATM short straddle
**File:** `monthly_atm_short_straddle.json`  
**What it does:** Same as (1) but on **monthly** expiry; use to study month‑end behaviour.  
**Risk:** Target 30%, SL 25% (basis: `premium_pct`, per leg).  
**Re-entry:** On SL → `RE_ASAP` (1x); on Target → `RE_COST` (1x).  
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-31 \
  --index NIFTY \
  --config configs/examples/monthly_atm_short_straddle.json \
  --out backtests/NIFTY_time_monthly.csv
```

---

### 10) Iron condor (delta‑based) — Complete exit
**File:** `iron_condor_deltarange_complete.json`  
**What it does:** Sells ~25Δ CE & ~25Δ PE, hedged with ~10Δ long wings (delta‑based iron condor). Exits **as a package** (Complete) when any leg hits SL/Target or at time exit.
**Risk (in config):** Shorts have SL 20%, Target 25% (basis: `premium_pct`, per leg); wings have no SL/Target.
**Re-entry:** Shorts → SL: `RE_ASAP` (1x), Target: `RE_COST` (1x); Wings: disabled.
**Run:**
```bash
python3 -m nocode_backtester \
  --root $HOME/Downloads/JioAICloud-Download/NIFTY \
  --start 2025-01-16 --end 2025-01-16 \
  --index NIFTY \
  --config configs/examples/iron_condor_deltarange_complete.json \
  --out backtests/NIFTY_time_intraday_IronCondor_DeltaBased.csv
```

> **Notes**
> - Strike selection uses `CLOSEST_DELTA` with targets 25Δ (shorts) and 10Δ (wings), snapping to NIFTY’s 50‑point grid.
> - Delta is computed automatically via the built‑in greeks helper when missing.

---

## Outputs

- **Trades CSV:** `backtests/NIFTY_time_intraday.csv` (one row per leg action/exit).  
- **Daily summary:** `backtests/NIFTY_time_intraday.__summary.csv` (P&L per day plus cumulative).

Inspect the CSVs with your spreadsheet tool or pandas to validate fills and costs.

---

## Notes & tips

- **Per‑leg re‑entry:** Add `reentry_on_sl`/`reentry_on_target` to each leg. Modes: `RE_ASAP`, `RE_ASAP_REV`, `RE_COST`, `RE_COST_REV`, `RE_MOMENTUM`, `RE_MOMENTUM_REV`, `LAZY_LEG`. Use `max_count` (≤20) and optional strategy-level `no_reentry_after`.
- **Per‑leg expiry keywords:** Use `Weekly`, `NextWeekly`, `Monthly`, or `NextMonthly` on each leg.
- **Per‑leg risk bases:** `premium_pts/premium_pct` (option LTP based) or `underlying_pts/underlying_pct` (spot based). Trailing supports `points/percent` on option premium.
- **OTM steps:** `OTM1/OTM2/…` assume a standard strike step (e.g., 50 for NIFTY). Adjust in code if your market differs.  
- **Premium selectors:** `CLOSEST_PREMIUM`, `PREMIUM_LE`, `PREMIUM_GE` choose strikes by option price instead of distance from ATM.  
- **Underlying stream:** Set `underlying_from` to `Cash` or `Futures` based on what your `.h5` provides; if spot is missing, the tool derives it when possible.  
- **Costs:** Config supports per‑lot round‑trip brokerage and per‑fill slippage—tweak to reflect your venue.  
- **Holidays/weekends:** Provide business‑day ranges that match available `.h5` files to avoid gaps.

---

## Contributing

New ideas? Add a JSON under `configs/examples/` and submit a PR with:  
- Clear name, timing, selection logic.  
- Short description and a “How to run” block like above.
