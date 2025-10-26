# Interactive Brokers Generic Tick List for Options Market Data

This document provides a comprehensive list of all relevant tick types for options market data subscriptions in Interactive Brokers.

## Basic Option Price Data

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"100"` | Option bid price | Price |
| `"101"` | Option ask price | Price |
| `"104"` | Option last price | Price |
| `"105"` | Option last size | Size |
| `"106"` | Option high price | Price |
| `"107"` | Option low price | Price |
| `"108"` | Option volume | Size |
| `"109"` | Option close price | Price |
| `"110"` | Option open price | Price |

## Options Greeks

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"101"` | Delta | Greek |
| `"106"` | Gamma | Greek |
| `"111"` | Theta | Greek |
| `"115"` | Vega | Greek |
| `"117"` | Rho | Greek |
| `"104"` | Implied volatility | Percentage |

## Additional Options Data

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"21"` | Open interest | Size |
| `"22"` | Historical volatility | Percentage |
| `"24"` | Option volume | Size |
| `"25"` | Option open interest | Size |

## Model-Derived Data

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"106"` | Model option price | Price |
| `"107"` | Model delta | Greek |
| `"108"` | Model gamma | Greek |
| `"109"` | Model theta | Greek |
| `"110"` | Model vega | Greek |
| `"111"` | Model rho | Greek |

## Bid/Ask Size Data

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"0"` | Bid size | Size |
| `"3"` | Ask size | Size |
| `"5"` | Last size | Size |

## Standard Market Data

| Tick Type | Description | Data Type |
|-----------|-------------|-----------|
| `"8"` | Volume | Size |
| `"14"` | Open price | Price |
| `"15"` | Close price | Price |
| `"16"` | High price | Price |
| `"17"` | Low price | Price |
| `"18"` | Last price | Price |
| `"19"` | Bid price | Price |
| `"20"` | Ask price | Price |

## Recommended Tick Lists by Use Case

### Basic Options Trading
```python
basic_options_ticks = [
    "100",  # Option bid
    "101",  # Option ask
    "104",  # Option last
    "108",  # Option volume
    "21",   # Open interest
]
```

### Options Greeks Analysis
```python
greeks_ticks = [
    "101",  # Delta
    "106",  # Gamma
    "111",  # Theta
    "115",  # Vega
    "117",  # Rho
    "104",  # Implied volatility
]
```

### Comprehensive Options Data
```python
comprehensive_ticks = [
    # Basic prices
    "100", "101", "104", "105", "106", "107", "108", "109", "110",
    # Greeks
    "101", "106", "111", "115", "117", "104",
    # Additional data
    "21", "22", "24", "25",
    # Sizes
    "0", "3", "5",
    # Standard data
    "8", "14", "15", "16", "17", "18", "19", "20"
]
```

### Model-Based Pricing
```python
model_ticks = [
    "106",  # Model option price
    "107",  # Model delta
    "108",  # Model gamma
    "109",  # Model theta
    "110",  # Model vega
    "111",  # Model rho
]
```

## Usage Examples

### Python Implementation
```python
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

# Create option contract
option_contract = Contract(
    symbol="AAPL",
    security_type=SecurityType.OPTION,
    exchange="SMART",
    currency="USD",
    expiry="20250117",
    strike=150.0,
    right=OptionRight.CALL,
    multiplier="100"
)

# Subscribe with comprehensive tick list
broker.subscribe_market_data(
    contract=option_contract,
    callback=market_data_callback,
    market_data_type=MarketDataType.DELAYED,
    generic_tick_list=[
        "100", "101", "104", "105", "106", "107", "108", "109", "110",  # Basic prices
        "101", "106", "111", "115", "117", "104",  # Greeks
        "21", "22", "24", "25",  # Additional data
        "0", "3", "5",  # Sizes
        "8", "14", "15", "16", "17", "18", "19", "20"  # Standard data
    ]
)
```

## Important Notes

1. **Not all tick types are available for all options**: Some tick types may not be supported for certain option contracts.

2. **Account permissions required**: Some tick types require specific market data subscriptions.

3. **Real-time vs delayed**: Live data requires appropriate market data subscriptions.

4. **Model data**: Model-derived Greeks are calculated by IB's pricing models and may differ from market-derived values.

5. **Error handling**: If a tick type is not supported, IB will return an error. Start with basic tick types and add more gradually.

## Troubleshooting

### Common Issues
- **"Not supported" error**: The tick type is not available for this contract
- **No data received**: Check if the contract exists and is valid
- **Inconsistent data**: Some tick types may not update as frequently as others

### Best Practices
1. Start with basic tick types (`"100"`, `"101"`, `"104"`)
2. Add Greeks gradually (`"101"`, `"106"`, `"111"`)
3. Test with a known liquid option contract first
4. Monitor for errors and adjust tick list accordingly

## References

- [Interactive Brokers API Documentation](https://interactivebrokers.github.io/tws-api/)
- [Market Data Types](https://interactivebrokers.github.io/tws-api/market_data.html)
- [Generic Tick Types](https://interactivebrokers.github.io/tws-api/tick_types.html)
