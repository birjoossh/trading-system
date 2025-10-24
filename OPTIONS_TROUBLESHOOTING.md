# Troubleshooting "Not Supported" Error for Options Market Data

The "not supported" error when subscribing to options market data can have several causes. Here's a systematic approach to diagnose and fix it.

## Common Causes

### 1. **Invalid Contract Specification**
- **Expiry date format**: Must be `YYYYMMDD` (e.g., `"20250117"`)
- **Strike price**: Must be valid for the underlying
- **Exchange**: Use `"SMART"` for most US options
- **Multiplier**: Usually `"100"` for US options

### 2. **Contract Doesn't Exist**
- The specific option contract may not exist
- Expiry date might be too far in the future
- Strike price might not be available

### 3. **Market Data Permissions**
- Your account may not have options market data permissions
- Some tick types require additional subscriptions

### 4. **Market Hours**
- Options may not trade outside market hours
- Some data is only available during trading hours

## Step-by-Step Troubleshooting

### Step 1: Test Without Generic Tick List
```python
# Start with basic subscription (no tick list)
broker.subscribe_market_data(
    contract=option_contract,
    callback=callback,
    market_data_type=MarketDataType.DELAYED
    # No generic_tick_list
)
```

### Step 2: Verify Contract Details
```python
# Use a known liquid option contract
option_contract = Contract(
    symbol="SPY",  # Very liquid ETF
    security_type=SecurityType.OPTION,
    exchange="SMART",
    currency="USD",
    expiry="20250117",  # Near-term expiry
    strike=400.0,  # At-the-money strike
    right=OptionRight.CALL,
    multiplier="100"
)
```

### Step 3: Try Different Exchanges
```python
# Try different exchanges
exchanges_to_try = ["SMART", "CBOE", "NASDAQ"]
```

### Step 4: Check Market Hours
- Ensure you're testing during US market hours (9:30 AM - 4:00 PM ET)
- Some options data is only available during trading hours

### Step 5: Verify Account Permissions
- Check if your IB account has options trading permissions
- Verify market data subscriptions

## Debugging Code

```python
def debug_option_contract(contract):
    """Debug option contract details"""
    print(f"Contract Debug Info:")
    print(f"  Symbol: {contract.symbol}")
    print(f"  Security Type: {contract.security_type.value}")
    print(f"  Exchange: {contract.exchange}")
    print(f"  Currency: {contract.currency}")
    print(f"  Expiry: {contract.expiry}")
    print(f"  Strike: {contract.strike}")
    print(f"  Right: {contract.right.value}")
    print(f"  Multiplier: {contract.multiplier}")
    
    # Validate expiry format
    if contract.expiry and len(contract.expiry) == 8:
        try:
            datetime.strptime(contract.expiry, "%Y%m%d")
            print(f"  ✅ Expiry format valid")
        except ValueError:
            print(f"  ❌ Expiry format invalid: {contract.expiry}")
    else:
        print(f"  ❌ Expiry missing or wrong length: {contract.expiry}")
```

## Alternative Approaches

### 1. **Use Option Chain First**
```python
# Get available option contracts first
option_chain = broker.get_option_chain(underlying_contract)
print(f"Available strikes: {option_chain.strikes}")
print(f"Available expiries: {option_chain.expiration_dates}")

# Use a contract from the chain
if option_chain.strikes and option_chain.expiration_dates:
    strike = option_chain.strikes[0]
    expiry = option_chain.expiration_dates[0]
    
    option_contract = Contract(
        symbol=underlying_contract.symbol,
        security_type=SecurityType.OPTION,
        exchange="SMART",
        currency="USD",
        expiry=expiry,
        strike=strike,
        right=OptionRight.CALL,
        multiplier="100"
    )
```

### 2. **Start with Stocks**
```python
# Test with stocks first to verify basic functionality
stock_contract = Contract(
    symbol="AAPL",
    security_type=SecurityType.STOCK,
    exchange="SMART",
    currency="USD"
)

broker.subscribe_market_data(
    contract=stock_contract,
    callback=callback,
    market_data_type=MarketDataType.DELAYED
)
```

### 3. **Use Different Underlying**
```python
# Try different underlying symbols
symbols_to_try = ["SPY", "QQQ", "AAPL", "MSFT", "TSLA"]
```

## Recommended Test Sequence

1. **Test stock market data** (verify basic functionality)
2. **Test option without tick list** (verify contract validity)
3. **Test option with basic tick list** (verify tick types)
4. **Test option with comprehensive tick list** (verify all features)

## Error Messages to Look For

- **"Not supported"**: Usually contract or tick type issue
- **"Invalid contract"**: Contract specification problem
- **"No market data permissions"**: Account permission issue
- **"Contract not found"**: Contract doesn't exist

## Quick Fixes

1. **Remove generic tick list** initially
2. **Use SMART exchange** for US options
3. **Use near-term expiry** (within 1-3 months)
4. **Use at-the-money strikes**
5. **Test during market hours**
6. **Use liquid underlying symbols** (SPY, QQQ, AAPL)

## Example Working Code

```python
# Minimal working example
option_contract = Contract(
    symbol="SPY",
    security_type=SecurityType.OPTION,
    exchange="SMART",
    currency="USD",
    expiry="20250117",  # January 17, 2025
    strike=400.0,
    right=OptionRight.CALL,
    multiplier="100"
)

# Start without tick list
subscription_id = broker.subscribe_market_data(
    contract=option_contract,
    callback=callback,
    market_data_type=MarketDataType.DELAYED
)
```

This approach should help identify the root cause of the "not supported" error.


