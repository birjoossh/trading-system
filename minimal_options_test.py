#!/usr/bin/env python3
"""
Minimal test to isolate the options market data issue
This will help identify what's causing the "not supported" error.
"""

import time
from datetime import datetime
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

def simple_callback(tick_data):
    """Simple callback for market data"""
    bid_str = f"${tick_data.bid:.2f}" if tick_data.bid is not None else "N/A"
    ask_str = f"${tick_data.ask:.2f}" if tick_data.ask is not None else "N/A"
    last_str = f"${tick_data.last:.2f}" if tick_data.last is not None else "N/A"
    
    print(f"[{tick_data.timestamp.strftime('%H:%M:%S')}] {tick_data.symbol}: "
          f"Bid={bid_str} Ask={ask_str} Last={last_str}")

def main():
    print("Minimal Options Market Data Test")
    print("=" * 40)
    
    # Initialize broker
    broker = IBBroker(host="127.0.0.1", port=4002, client_id=1)
    
    try:
        # Connect
        print("Connecting to IB Gateway...")
        if not broker.connect():
            print("❌ Failed to connect")
            return
        
        print("✅ Connected successfully!")
        
        # Test 1: Try without any generic tick list
        print("\n1. Testing option subscription WITHOUT generic tick list...")
        option_contract = Contract(
            symbol="AAPL",
            security_type=SecurityType.OPTION,
            exchange="SMART",
            currency="USD",
            expiry="20250117",  # January 17, 2025
            str
            ike=150.0,
            right=OptionRight.CALL,
            multiplier="100"
        )
        
        try:
            sub_id_1 = broker.subscribe_market_data(
                contract=option_contract,
                callback=simple_callback,
                market_data_type=MarketDataType.DELAYED
                # No generic_tick_list at all
            )
            print(f"✅ Option subscription successful (no ticks): {sub_id_1}")
            
            # Wait a bit for data
            print("Waiting 10 seconds for data...")
            time.sleep(10)
            
            # Cancel this subscription
            broker.unsubscribe_market_data(sub_id_1)
            print("✅ Cancelled subscription")
            
        except Exception as e:
            print(f"❌ Option subscription failed (no ticks): {e}")
            print("This suggests the contract itself is invalid or not supported")
            return
        
        # Test 2: Try with minimal tick list
        print("\n2. Testing option subscription WITH minimal tick list...")
        try:
            sub_id_2 = broker.subscribe_market_data(
                contract=option_contract,
                callback=simple_callback,
                market_data_type=MarketDataType.DELAYED,
                generic_tick_list=["100", "101", "104"]  # Just basic prices
            )
            print(f"✅ Option subscription successful (basic ticks): {sub_id_2}")
            
            # Wait a bit for data
            print("Waiting 10 seconds for data...")
            time.sleep(10)
            
            # Cancel this subscription
            broker.unsubscribe_market_data(sub_id_2)
            print("✅ Cancelled subscription")
            
        except Exception as e:
            print(f"❌ Option subscription failed (basic ticks): {e}")
            print("This suggests the tick types are not supported for this contract")
        
        # Test 3: Try different option contract
        print("\n3. Testing different option contract...")
        option_contract_2 = Contract(
            symbol="SPY",  # Try SPY instead of AAPL
            security_type=SecurityType.OPTION,
            exchange="SMART",
            currency="USD",
            expiry="20250117",
            strike=400.0,  # SPY strike
            right=OptionRight.CALL,
            multiplier="100"
        )
        
        try:
            sub_id_3 = broker.subscribe_market_data(
                contract=option_contract_2,
                callback=simple_callback,
                market_data_type=MarketDataType.DELAYED,
                generic_tick_list=["100", "101", "104"]
            )
            print(f"✅ SPY option subscription successful: {sub_id_3}")
            
            # Wait a bit for data
            print("Waiting 10 seconds for data...")
            time.sleep(10)
            
            # Cancel this subscription
            broker.unsubscribe_market_data(sub_id_3)
            print("✅ Cancelled subscription")
            
        except Exception as e:
            print(f"❌ SPY option subscription failed: {e}")
        
        # Test 4: Try stock for comparison
        print("\n4. Testing stock subscription for comparison...")
        stock_contract = Contract(
            symbol="AAPL",
            security_type=SecurityType.STOCK,
            exchange="SMART",
            currency="USD"
        )
        
        try:
            sub_id_4 = broker.subscribe_market_data(
                contract=stock_contract,
                callback=simple_callback,
                market_data_type=MarketDataType.DELAYED
            )
            print(f"✅ Stock subscription successful: {sub_id_4}")
            
            # Wait a bit for data
            print("Waiting 10 seconds for data...")
            time.sleep(10)
            
            # Cancel this subscription
            broker.unsubscribe_market_data(sub_id_4)
            print("✅ Cancelled subscription")
            
        except Exception as e:
            print(f"❌ Stock subscription failed: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Disconnect
        print("\n5. Disconnecting...")
        broker.disconnect()
        print("✅ Disconnected")

if __name__ == "__main__":
    main()
