# Installation Guide

## Quick Installation

1. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

2. **Install the package** (optional):
```bash
pip install -e .
```

## Interactive Brokers Setup

### Step 1: Download IB Software
- Download TWS or IB Gateway from https://www.interactivebrokers.com/
- Install and create a paper trading account for testing

### Step 2: Configure TWS/Gateway
1. Start TWS or IB Gateway
2. Go to File â†’ Global Configuration â†’ API â†’ Settings
3. Enable "ActiveX and Socket Clients"
4. Set Socket port:
   - 7497 for paper trading (recommended for testing)
   - 7496 for live trading
5. Check "Allow connections from localhost only"
6. For testing, check "Read-Only API"

### Step 3: Test Connection
Run the example:
```bash
python example_usage.py
```

## Troubleshooting

### IB API Installation Issues
If `pip install ibapi` fails:

**For Windows**:
1. Download the TWS API from IB website
2. Extract and navigate to `/TWSApi/source/pythonclient/`
3. Run: `python setup.py install`

**For Mac/Linux**:
Same steps as Windows, or try:
```bash
pip install --upgrade pip
pip install ibapi --no-cache-dir
```

### Connection Issues
- Ensure TWS/Gateway is running
- Check firewall settings
- Try different client IDs
- Restart TWS/Gateway

### Market Data Issues
- Verify you have data subscriptions
- Check if markets are open
- Some symbols require specific exchanges

## Next Steps

1. Run `python example_usage.py` to test basic functionality
2. Try `python strategy_example.py` for a simple trading strategy
3. Read the API documentation in README.md
4. Start building your own strategies!