# Enhanced Market Data Support for Trading System

This document describes the enhanced market data capabilities added to the trading system, supporting both stocks and options with comprehensive market data subscriptions.

## Overview

The enhanced market data system provides:
- **Generic data models** that work with any broker
- **Comprehensive options support** including Greeks and implied volatility
- **Enhanced market data types** for different subscription levels
- **Robust error handling** and subscription management
- **Future-proof architecture** for easy integration with other brokers

## Key Features

### 1. Enhanced Data Models

#### Contract Class
```python
@dataclass
class Contract:
    symbol: str
    security_type: SecurityType  # STK, OPT, FUT, etc.
    exchange: str
    currency: str
    # Enhanced options support
    expiry: Optional[str] = None  # YYYYMMDD format
    strike: Optional[float] = None
    right: Optional[OptionRight] = None  # Call/Put
    multiplier: Optional[str] = None
    trading_class: Optional[str] = None
    # Additional fields for complex instruments
    combo_legs: Optional[List[Dict[str, Any]]] = None
```

#### Enhanced TickData Class
```python
@dataclass
class TickData:
    # Basic price data
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    
    # Options-specific data
    delta: Optional[float] = None
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    rho: Optional[float] = None
    implied_volatility: Optional[float] = None
    
    # Metadata
    tick_type: Optional[TickType] = None
    market_data_type: Optional[MarketDataType] = None
```

### 2. Market Data Subscriptions

#### Subscription Management
```python
# Subscribe to market data
subscription_id = broker.subscribe_market_data(
    contract=contract,
    callback=callback_function,
    market_data_type=MarketDataType.DELAYED,
    snapshot=False,
    regulatory_snapshot=False,
    generic_tick_list=["101", "106", "111"]  # Greeks
)

# Unsubscribe
broker.unsubscribe_market_data(subscription_id)

# Get active subscriptions
subscriptions = broker.get_market_data_subscriptions()
```

### 3. Options Support

#### Option Chain Retrieval
```python
# Get option chain for underlying
option_chain = broker.get_option_chain(
    underlying_contract=stock_contract,
    expiration_dates=["20241220", "20250117"],
    strikes=[140, 150, 160]
)
```

#### Greeks Calculation
```python
# Get Greeks for specific option
greeks = broker.get_greeks(option_contract)
print(f"Delta: {greeks.delta}")
print(f"Gamma: {greeks.gamma}")
print(f"Theta: {greeks.theta}")
```

### 4. Market Data Types

The system supports different market data types:

- **LIVE**: Real-time market data (requires subscription)
- **DELAYED**: 15-minute delayed data (free for most instruments)
- **FROZEN**: Frozen market data
- **DELAYED_FROZEN**: Delayed frozen data

### 5. Enhanced Tick Types

Comprehensive tick type support:

#### Basic Price Ticks
- BID, ASK, LAST
- HIGH, LOW, OPEN, CLOSE
- VOLUME, BID_SIZE, ASK_SIZE

#### Options-Specific Ticks
- DELTA, GAMMA, THETA, VEGA, RHO
- IMPLIED_VOLATILITY
- OPTION_PRICE
- OPEN_INTEREST

## Interactive Brokers Implementation

### Enhanced IB Broker Features

1. **Comprehensive Tick Mapping**: Maps IB tick types to our generic format
2. **Options Greeks Support**: Automatic calculation and streaming of Greeks
3. **Error Handling**: Enhanced error tracking for market data subscriptions
4. **Caching**: Intelligent caching for option chains and Greeks data
5. **Subscription Management**: Track and manage multiple subscriptions

### IB-Specific Features

```python
# Set market data type
broker.set_market_data_type(MarketDataType.DELAYED)

# Subscribe with Greeks for options
subscription_id = broker.subscribe_market_data(
    contract=option_contract,
    callback=callback,
    generic_tick_list=["101", "106", "111", "115", "117"]  # All Greeks
)
```

## Usage Examples

### Basic Stock Market Data
```python
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, MarketDataType
)

# Create stock contract
stock_contract = Contract(
    symbol="AAPL",
    security_type=SecurityType.STOCK,
    exchange="SMART",
    currency="USD"
)

# Subscribe to market data
def market_data_callback(tick_data):
    print(f"AAPL: Bid=${tick_data.bid}, Ask=${tick_data.ask}")

subscription_id = broker.subscribe_market_data(
    contract=stock_contract,
    callback=market_data_callback,
    market_data_type=MarketDataType.DELAYED
)
```

### Options Market Data with Greeks
```python
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

# Create option contract
option_contract = Contract(
    symbol="AAPL",
    security_type=SecurityType.OPTION,
    exchange="SMART",
    currency="USD",
    expiry="20241220",
    strike=150.0,
    right=OptionRight.CALL,
    multiplier="100"
)

# Subscribe with Greeks
def options_callback(tick_data):
    print(f"AAPL 150C: Price=${tick_data.last}")
    print(f"Delta: {tick_data.delta}, Gamma: {tick_data.gamma}")
    print(f"Theta: {tick_data.theta}, Vega: {tick_data.vega}")

subscription_id = broker.subscribe_market_data(
    contract=option_contract,
    callback=options_callback,
    market_data_type=MarketDataType.DELAYED,
    generic_tick_list=["101", "106", "111", "115", "117"]  # Greeks
)
```

### Option Chain Analysis
```python
# Get option chain
option_chain = broker.get_option_chain(stock_contract)

print(f"Available expirations: {option_chain.expiration_dates}")
print(f"Available strikes: {option_chain.strikes}")

# Create specific option contracts
for strike in option_chain.strikes[:5]:  # First 5 strikes
    call_option = Contract(
        symbol=option_chain.underlying_symbol,
        security_type=SecurityType.OPTION,
        exchange="SMART",
        currency="USD",
        expiry=option_chain.expiration_dates[0],
        strike=strike,
        right=OptionRight.CALL,
        multiplier="100"
    )
    
    # Subscribe to this option
    broker.subscribe_market_data(call_option, callback)
```

## Error Handling

The system provides comprehensive error handling:

```python
# Register error callbacks
def market_data_error_callback(error):
    print(f"Market data error: {error.error_code} - {error.error_message}")

broker.register_callback('market_data_error', market_data_error_callback)
```

## Future Broker Integration

The generic design allows easy integration with other brokers:

1. **Abstract Interface**: All brokers implement the same interface
2. **Generic Data Models**: Work with any broker's data format
3. **Broker-Specific Mapping**: Each broker maps to generic format
4. **Consistent API**: Same methods work across all brokers

## Performance Considerations

1. **Caching**: Option chains and Greeks are cached to reduce API calls
2. **Subscription Limits**: IB has limits on concurrent subscriptions
3. **Data Frequency**: Market data updates vary by instrument type
4. **Memory Management**: Subscriptions are properly cleaned up

## Requirements

- Interactive Brokers TWS or Gateway running
- Appropriate market data subscriptions for live data
- Python 3.7+ with required dependencies

## Testing

Run the example to test the implementation:

```bash
python example_enhanced_market_data.py
```

This will demonstrate:
- Stock market data subscription
- Options market data with Greeks
- Option chain retrieval
- Subscription management
- Error handling

## Conclusion

The enhanced market data system provides a robust, scalable foundation for trading applications that need comprehensive market data support for both stocks and options. The generic design ensures easy integration with multiple brokers while maintaining consistent functionality across all implementations.
