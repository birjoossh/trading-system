#!/usr/bin/env python3
"""
Focused example for options market data with comprehensive tick types
This demonstrates all the relevant tick types for options trading.
"""

import time
from datetime import datetime
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

def options_callback(tick_data):
    """Callback function for options market data"""
    print(f"\n[{tick_data.timestamp.strftime('%H:%M:%S')}] {tick_data.symbol} Option Update:")
    print(f"  Contract: {tick_data.symbol} {tick_data.raw_data.get('strike', 'N/A')} {tick_data.raw_data.get('right', 'N/A')}")
    
    # Basic prices
    if tick_data.bid is not None:
        print(f"  Bid: ${tick_data.bid:.2f}")
    if tick_data.ask is not None:
        print(f"  Ask: ${tick_data.ask:.2f}")
    if tick_data.last is not None:
        print(f"  Last: ${tick_data.last:.2f}")
    
    # Greeks
    if tick_data.delta is not None:
        print(f"  Delta: {tick_data.delta:.4f}")
    if tick_data.gamma is not None:
        print(f"  Gamma: {tick_data.gamma:.4f}")
    if tick_data.theta is not None:
        print(f"  Theta: {tick_data.theta:.4f}")
    if tick_data.vega is not None:
        print(f"  Vega: {tick_data.vega:.4f}")
    if tick_data.rho is not None:
        print(f"  Rho: {tick_data.rho:.4f}")
    if tick_data.implied_volatility is not None:
        print(f"  Implied Vol: {tick_data.implied_volatility:.2%}")
    
    # Volume and open interest
    if tick_data.volume is not None:
        print(f"  Volume: {tick_data.volume:,}")
    if tick_data.open_interest is not None:
        print(f"  Open Interest: {tick_data.open_interest:,}")
    
    # Sizes
    if tick_data.bid_size is not None:
        print(f"  Bid Size: {tick_data.bid_size}")
    if tick_data.ask_size is not None:
        print(f"  Ask Size: {tick_data.ask_size}")
    
    print("-" * 50)

def main():
    print("Options Market Data with Comprehensive Tick Types")
    print("=" * 60)
    
    # Initialize broker
    broker = IBBroker(host="127.0.0.1", port=4002, client_id=1)
    
    try:
        # Connect
        print("Connecting to IB Gateway...")
        if not broker.connect():
            print("❌ Failed to connect")
            return
        
        print("✅ Connected successfully!")
        
        # Set market data type
        broker.set_market_data_type(MarketDataType.DELAYED)
        
        # Create option contract
        print("\n1. Creating AAPL option contract...")
        option_contract = Contract(
            symbol="AAPL",
            security_type=SecurityType.OPTION,
            exchange="SMART",
            currency="USD",
            expiry="20250117",  # January 17, 2025
            strike=150.0,
            right=OptionRight.CALL,
            multiplier="100"
        )
        
        print(f"   Symbol: {option_contract.symbol}")
        print(f"   Strike: {option_contract.strike}")
        print(f"   Right: {option_contract.right.value}")
        print(f"   Expiry: {option_contract.expiry}")
        print(f"   Exchange: {option_contract.exchange}")
        
        # Define comprehensive tick list for options
        print("\n2. Setting up comprehensive tick list...")
        options_tick_list = [
            "100",  # Option bid price
            "101",  # Option ask price
            "104",  # Option last price
            "105",  # Option last size
            "106",  # Option high price
            "107",  # Option low price
            "108",  # Option volume
            "109",  # Option close price
            "110",  # Option open price
            "21",   # Open interest
            "22"   # Historical volatility
        ]
        
        print(f"   Tick types: {len(options_tick_list)} total")
        print(f"   Includes: Prices, Greeks, Volume, Open Interest, Sizes")
        
        # Subscribe to market data
        print("\n3. Subscribing to options market data...")
        try:
            subscription_id = broker.subscribe_market_data(
                contract=option_contract,
                callback=options_callback,
                market_data_type=MarketDataType.DELAYED,
                generic_tick_list=options_tick_list
            )
            print(f"✅ Subscription successful: {subscription_id}")
        except Exception as e:
            print(f"❌ Subscription failed: {e}")
            print("\nTrying with basic tick list...")
            
            # Fallback to basic tick list
            basic_tick_list = ["100", "101", "104", "108", "21"]  # Basic prices, volume, open interest
            try:
                subscription_id = broker.subscribe_market_data(
                    contract=option_contract,
                    callback=options_callback,
                    market_data_type=MarketDataType.DELAYED,
                    generic_tick_list=basic_tick_list
                )
                print(f"✅ Basic subscription successful: {subscription_id}")
            except Exception as e2:
                print(f"❌ Basic subscription also failed: {e2}")
                return
        
        # Let data flow
        print("\n4. Receiving market data for 60 seconds...")
        print("(Press Ctrl+C to stop early)")
        
        try:
            time.sleep(60)
        except KeyboardInterrupt:
            print("\nStopping early...")
        
        # Cleanup
        print("\n5. Cleaning up...")
        try:
            broker.unsubscribe_market_data(subscription_id)
            print("✅ Subscription cancelled")
        except Exception as e:
            print(f"⚠️ Error cancelling subscription: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Disconnect
        print("\n6. Disconnecting...")
        broker.disconnect()
        print("✅ Disconnected")

if __name__ == "__main__":
    main()
