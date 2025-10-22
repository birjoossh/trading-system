# Interactive Brokers Setup Guide

This guide will help you set up Interactive Brokers for use with the enhanced market data trading system.

## Prerequisites

1. **Interactive Brokers Account**: You need an IB account (paper trading or live)
2. **TWS or IB Gateway**: Download and install from [Interactive Brokers](https://www.interactivebrokers.com/en/trading/tws.php)
3. **Python Dependencies**: Install the required packages

## Step 1: Install Python Dependencies

```bash
pip install ibapi
```

## Step 2: Download and Install IB Software

### Option A: IB Gateway (Recommended for API)
1. Download IB Gateway from the IB website
2. Install and run IB Gateway
3. Login with your IB credentials
4. Choose "Paper Trading" for testing

### Option B: TWS (Trader Workstation)
1. Download TWS from the IB website
2. Install and run TWS
3. Login with your IB credentials
4. Choose "Paper Trading" for testing

## Step 3: Configure API Settings

### For IB Gateway:
1. When IB Gateway starts, it will show API settings
2. Make sure "Enable ActiveX and Socket EClients" is checked
3. Note the port numbers:
   - **Live Trading**: 4001
   - **Simulated Trading**: 4002

### For TWS:
1. Go to **Edit → Global Configuration → API → Settings**
2. Check **"Enable ActiveX and Socket EClients"**
3. Note the port numbers:
   - **Live Trading**: 7496
   - **Simulated Trading**: 7497

## Step 4: Test Connection

Run the connection test script:

```bash
python test_ib_connection.py
```

This will:
- Test port connectivity
- Attempt to connect to IB
- Verify basic functionality
- Provide troubleshooting tips

## Step 5: Run the Enhanced Market Data Example

Once the connection test passes, run the full example:

```bash
python example_enhanced_market_data.py
```

## Troubleshooting

### Error 502: Couldn't connect to TWS

This error means the connection to IB failed. Common causes:

1. **TWS/Gateway not running**: Make sure IB Gateway or TWS is running
2. **API not enabled**: Check API settings in TWS/Gateway
3. **Wrong port**: Try different ports (4002, 4001, 7497, 7496)
4. **Firewall**: Check if firewall is blocking the connection
5. **Client ID conflict**: Another application might be using the same client ID

### Port Configuration

| Port | Application | Trading Type | Description |
|------|-------------|--------------|-------------|
| 4002 | IB Gateway | Simulated | **Recommended for testing** |
| 4001 | IB Gateway | Live | For live trading |
| 7497 | TWS | Simulated | TWS paper trading |
| 7496 | TWS | Live | TWS live trading |

### API Settings Checklist

- [ ] TWS/Gateway is running
- [ ] "Enable ActiveX and Socket EClients" is checked
- [ ] Port number matches the one in your code
- [ ] No other applications using the same client ID
- [ ] Firewall allows the connection

### Common Solutions

1. **Restart IB Gateway/TWS**: Sometimes a restart fixes connection issues
2. **Check client ID**: Make sure no other application is using client ID 1
3. **Try different ports**: The example script tries multiple ports automatically
4. **Check firewall**: Windows/Mac firewall might be blocking the connection
5. **Use IB Gateway**: Gateway is more stable for API connections than TWS

## Market Data Subscriptions

### Free Data (Delayed)
- US stocks: 15-minute delayed
- US options: 15-minute delayed
- No subscription required

### Live Data (Requires Subscription)
- Real-time data
- Requires market data subscriptions
- Additional costs apply

## Example Usage

```python
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, MarketDataType
)

# Initialize broker
broker = IBBroker(host="127.0.0.1", port=4002, client_id=1)

# Connect
if broker.connect():
    print("Connected successfully!")
    
    # Your trading code here
    
    broker.disconnect()
else:
    print("Failed to connect")
```

## Support

If you continue to have issues:

1. Check the IB API documentation
2. Verify your IB account has API access enabled
3. Contact IB support for API-related issues
4. Check the example logs for specific error messages

## Next Steps

Once you have the connection working:

1. Run the enhanced market data example
2. Explore the options trading capabilities
3. Test the Greeks calculation
4. Experiment with different market data types
5. Build your own trading strategies

The enhanced system provides comprehensive support for both stocks and options with real-time market data, Greeks calculation, and robust error handling.
