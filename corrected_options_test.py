#!/usr/bin/env python3
"""
Corrected options market data test with valid contracts and tick types
This addresses the issues found in the previous test.
"""

import time
from datetime import datetime
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

def options_callback(tick_data):
    """Callback for options market data"""
    bid_str = f"${tick_data.bid:.2f}" if tick_data.bid is not None else "N/A"
    ask_str = f"${tick_data.ask:.2f}" if tick_data.ask is not None else "N/A"
    last_str = f"${tick_data.last:.2f}" if tick_data.last is not None else "N/A"
    
    print(f"[{tick_data.timestamp.strftime('%H:%M:%S')}] {tick_data.symbol} Option:")
    print(f"  Bid: {bid_str}, Ask: {ask_str}, Last: {last_str}")
    
    # Show Greeks if available
    if tick_data.delta is not None:
        print(f"  Delta: {tick_data.delta:.4f}")
    if tick_data.gamma is not None:
        print(f"  Gamma: {tick_data.gamma:.4f}")
    if tick_data.theta is not None:
        print(f"  Theta: {tick_data.theta:.4f}")
    if tick_data.vega is not None:
        print(f"  Vega: {tick_data.vega:.4f}")
    if tick_data.implied_volatility is not None:
        print(f"  IV: {tick_data.implied_volatility:.2%}")
    
    print("-" * 40)

def main():
    print("Corrected Options Market Data Test")
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
        
        # Test 1: Try to get option chain first to find valid contracts
        print("\n1. Getting option chain for SPY...")
        spy_underlying = Contract(
            symbol="SPY",
            security_type=SecurityType.STOCK,
            exchange="SMART",
            currency="USD"
        )
        
        try:
            option_chain = broker.get_option_chain(spy_underlying)
            print(f"✅ Option chain retrieved:")
            print(f"  Available expirations: {len(option_chain.expiration_dates)}")
            print(f"  Available strikes: {len(option_chain.strikes)}")
            
            if option_chain.expiration_dates and option_chain.strikes:
                # Use the first available expiration and strike
                expiry = option_chain.expiration_dates[0]
                strike = option_chain.strikes[0]
                print(f"  Using expiry: {expiry}, strike: {strike}")
                
                # Create option contract with valid details
                option_contract = Contract(
                    symbol="AAPL",
                    security_type=SecurityType.OPTION,
                    exchange="SMART",
                    currency="USD",
                    expiry=expiry,
                    strike=strike,
                    right=OptionRight.CALL,
                    multiplier="100"
                )
                
                # Test subscription without tick list
                print("\n2. Testing option subscription (no tick list)...")
                try:
                    sub_id = broker.subscribe_market_data(
                        contract=option_contract,
                        callback=options_callback,
                        market_data_type=MarketDataType.DELAYED
                    )
                    print(f"✅ Option subscription successful: {sub_id}")
                    
                    # Wait for data
                    print("Waiting 15 seconds for data...")
                    time.sleep(15)
                    
                    # Cancel subscription
                    broker.unsubscribe_market_data(sub_id)
                    print("✅ Subscription cancelled")
                    
                except Exception as e:
                    print(f"❌ Option subscription failed: {e}")
                
                # Test with correct tick types for options
                print("\n3. Testing option subscription with correct tick types...")
                try:
                    # Use the correct tick types for options
                    correct_tick_list = [
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
                        "22",   # Historical volatility
                    ]
                    
                    sub_id = broker.subscribe_market_data(
                        contract=option_contract,
                        callback=options_callback,
                        market_data_type=MarketDataType.DELAYED,
                        generic_tick_list=correct_tick_list
                    )
                    print(f"✅ Option subscription with ticks successful: {sub_id}")
                    
                    # Wait for data
                    print("Waiting 15 seconds for data...")
                    time.sleep(15)
                    
                    # Cancel subscription
                    broker.unsubscribe_market_data(sub_id)
                    print("✅ Subscription cancelled")
                    
                except Exception as e:
                    print(f"❌ Option subscription with ticks failed: {e}")
                
            else:
                print("❌ No option chain data available")
                
        except Exception as e:
            print(f"❌ Failed to get option chain: {e}")
            
            # Fallback: try with a known liquid option
            print("\nFallback: Trying with known liquid option...")
            fallback_contract = Contract(
                symbol="SPY",
                security_type=SecurityType.OPTION,
                exchange="SMART",
                currency="USD",
                expiry="20250117",  # January 17, 2025
                strike=400.0,  # Near current SPY price
                right=OptionRight.CALL,
                multiplier="100"
            )
            
            try:
                sub_id = broker.subscribe_market_data(
                    contract=fallback_contract,
                    callback=options_callback,
                    market_data_type=MarketDataType.DELAYED
                )
                print(f"✅ Fallback option subscription successful: {sub_id}")
                
                # Wait for data
                print("Waiting 15 seconds for data...")
                time.sleep(15)
                
                # Cancel subscription
                broker.unsubscribe_market_data(sub_id)
                print("✅ Subscription cancelled")
                
            except Exception as e:
                print(f"❌ Fallback option subscription failed: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        # Disconnect
        print("\n4. Disconnecting...")
        broker.disconnect()
        print("✅ Disconnected")

if __name__ == "__main__":
    main()
