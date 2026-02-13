# Exchange Configuration Guide

The Unified Trading Platform supports a fully exchange-agnostic architecture. While it defaults to **NSE** (National Stock Exchange of India) out of the box, you can configure any global exchange (e.g., NYSE, NASDAQ, LSE) via `config.yaml`.

## 1. Setting the Default Exchange
To change the system-wide default exchange, update the `system.default_exchange` key in `config.yaml`.

```yaml
system:
  max_concurrent_orders: 100
  ...
  default_exchange: "NYSE"  # <--- Change this
```

## 2. Defining a New Exchange
Add your exchange under the `exchanges` section. You must define:
*   **Currency**: The trading currency.
*   **Timezone**: The IANA timezone for the exchange location.
*   **Trading Hours**: Start and end times (local time).
*   **Expiry Rules**:
    *   `weekly_day`: Day of week for weekly expiry (0=Mon, 4=Fri).
    *   `switch_date` / `weekly_day_before` / `weekly_day_after`: Advanced logic for changing expiry days (e.g., NSE changing from Thu to Tue).

### Example: Adding NYSE
```yaml
exchanges:
  NYSE:
    currency: "USD"
    timezone: "America/New_York"
    trading_hours:
      start: "09:30"
      end: "16:00"
    expiry:
      weekly_day: 4 # Friday
```

### Example: Adding Tokyo Stock Exchange (TSE)
```yaml
exchanges:
  TSE:
    currency: "JPY"
    timezone: "Asia/Tokyo"
    trading_hours:
      start: "09:00"
      end: "15:00"
    expiry:
      weekly_day: 4 # Friday
```

## 3. Usage in Code
The system automatically uses these settings.

*   **Strategy Utils**: Functions like `weekly_expiry_for(date)` will automatically use the `default_exchange` unless an override is provided.
    ```python
    # Uses default_exchange (e.g., NYSE if you changed config)
    expiry = strategy_utils.weekly_expiry_for(date)
    
    # Force specific exchange
    expiry = strategy_utils.weekly_expiry_for(date, exchange="TSE")
    ```

*   **Strike Selection**: When inferring expiry times for Greeks, the system looks up the exchange's closing time (e.g., 16:00 for NYSE).

## 4. Removing "Hardcoded" Defaults
The codebase no longer contains hardcoded "NSE" preferences in logic. All defaults are retrieved from `config.yaml`. If a configuration is missing, it may fallback to a generic safe default (Thursday expiry, 15:30 close) or raise an error, but "NSE" is not baked into the Python code anymore.
