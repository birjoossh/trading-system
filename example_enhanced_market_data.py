#!/usr/bin/env python3
"""
Example demonstrating enhanced market data subscriptions for stocks and options
using the updated base_broker and ib_broker implementations.
"""

import time
from datetime import datetime
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType, TickType
)

def market_data_callback(tick_data):
    """Callback function for market data updates"""
    print(f"Market Data Update for {tick_data.symbol}:")
    print(f"  Timestamp: {tick_data.timestamp}")
    print(f"  Security Type: {tick_data.security_type.value}")
    print(f"  Exchange: {tick_data.exchange}")
    print(f"  Currency: {tick_data.currency}")
    
    # Basic price data
    if tick_data.bid is not None:
        print(f"  Bid: ${tick_data.bid:.2f}")
    if tick_data.ask is not None:
        print(f"  Ask: ${tick_data.ask:.2f}")
    if tick_data.last is not None:
        print(f"  Last: ${tick_data.last:.2f}")
    
    # Options-specific data
    if tick_data.delta is not None:
        print(f"  Delta: {tick_data.delta:.4f}")
    if tick_data.gamma is not None:
        print(f"  Gamma: {tick_data.gamma:.4f}")
    if tick_data.theta is not None:
        print(f"  Theta: {tick_data.theta:.4f}")
    if tick_data.vega is not None:
        print(f"  Vega: {tick_data.vega:.4f}")
    if tick_data.implied_volatility is not None:
        print(f"  Implied Volatility: {tick_data.implied_volatility:.2%}")
    
    print("-" * 50)

def main():
    """Main example function"""
    print("Enhanced Market Data Subscription Example")
    print("=" * 50)
    
    # Try different ports in order of preference
    ports_to_try = [
        (4002, "IB Gateway Simulated Trading")
    ]
    
    broker = None
    connected = False
    
    for port, description in ports_to_try:
        print(f"\nTrying to connect to {description} on port {port}...")
        broker = IBBroker(host="127.0.0.1", port=port, client_id=1)
        
        try:
            if broker.connect():
                print(f"✅ Successfully connected to {description} on port {port}")
                connected = True
                break
            else:
                print(f"❌ Failed to connect to {description} on port {port}")
        except Exception as e:
            print(f"❌ Error connecting to {description} on port {port}: {e}")
    
    if not connected:
        print("\n" + "="*60)
        print("❌ FAILED TO CONNECT TO INTERACTIVE BROKERS")
        return
    
    try:
        
        print("Connected successfully!")
        
        # Set market data type to delayed (free)
        broker.set_market_data_type(MarketDataType.DELAYED)
        
        # Example 1: Subscribe to stock market data
        # print("\n1. Subscribing to AAPL stock market data...")
        # stock_contract = Contract(
        #     symbol="AAPL",
        #     security_type=SecurityType.STOCK,
        #     exchange="NYSE",
        #     currency="USD"
        # )
        
        # stock_subscription_id = broker.subscribe_market_data(
        #     contract=stock_contract,
        #     callback=market_data_callback,
        #     market_data_type=MarketDataType.DELAYED
        # )
        # print(f"Stock subscription ID: {stock_subscription_id}")
        
        # Example 2: Subscribe to options market data
        print("\n2. Subscribing to AAPL options market data...")
        option_contract = Contract(
            symbol="AAPL",
            security_type=SecurityType.OPTION,
            exchange="SMART",  # Use SMART for options
            currency="USD",
            expiry="20251024",
            strike=150.0,
            right=OptionRight.CALL,
            multiplier="100"
        )
        
        option_subscription_id = broker.subscribe_market_data(
            contract=option_contract,
            callback=market_data_callback,
            market_data_type=MarketDataType.DELAYED
            # Start with NO generic tick list to isolate the issue
        )
        print(f"Option subscription ID: {option_subscription_id}")
        
        # # Example 3: Get option chain
        # print("\n3. Getting AAPL option chain...")
        # try:
        #     option_chain = broker.get_option_chain(stock_contract)
        #     print(f"Option chain for {option_chain.underlying_symbol}:")
        #     print(f"  Expiration dates: {option_chain.expiration_dates[:5]}...")  # Show first 5
        #     print(f"  Strikes: {option_chain.strikes[:10]}...")  # Show first 10
        # except Exception as e:
        #     print(f"Error getting option chain: {e}")
        
        # # Example 4: Get Greeks for option
        # print("\n4. Getting Greeks for AAPL option...")
        # try:
        #     greeks = broker.get_greeks(option_contract)
        #     print(f"Greeks for {option_contract.symbol} {option_contract.strike} {option_contract.right.value}:")
        #     if greeks.delta is not None:
        #         print(f"  Delta: {greeks.delta:.4f}")
        #     if greeks.gamma is not None:
        #         print(f"  Gamma: {greeks.gamma:.4f}")
        #     if greeks.theta is not None:
        #         print(f"  Theta: {greeks.theta:.4f}")
        #     if greeks.vega is not None:
        #         print(f"  Vega: {greeks.vega:.4f}")
        # except Exception as e:
        #     print(f"Error getting Greeks: {e}")
        
        # Example 5: List active subscriptions
        print("\n5. Active market data subscriptions:")
        subscriptions = broker.get_market_data_subscriptions()
        for sub in subscriptions:
            print(f"  {sub.subscription_id}: {sub.contract.symbol} ({sub.contract.security_type.value})")
        
        # Let market data flow for a few seconds
        print("\n6. Receiving market data for 100 seconds...")
        time.sleep(100)
        
        # Example 6: Unsubscribe from market data
        print("\n7. Unsubscribing from market data...")
        broker.unsubscribe_market_data(stock_subscription_id)
        broker.unsubscribe_market_data(option_subscription_id)
        print("Unsubscribed successfully!")
        
    except Exception as e:
        print(f"Error: {e}")
    
    finally:
        # Disconnect
        print("\n8. Disconnecting from broker...")
        broker.disconnect()
        print("Disconnected successfully!")

if __name__ == "__main__":
    main()
