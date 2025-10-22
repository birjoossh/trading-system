#!/usr/bin/env python3
"""
Simple script to test Interactive Brokers connection
This helps diagnose connection issues before running the full example.
"""

import socket
import time
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker

def test_port_connectivity(host, port, timeout=5):
    """Test if a port is open and accepting connections"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False

def main():
    print("Interactive Brokers Connection Test")
    print("=" * 50)
    
    host = "127.0.0.1"
    ports_to_test = [
        (4002, "IB Gateway Simulated Trading"),
        (4001, "IB Gateway Live Trading"),
        (7497, "TWS Simulated Trading"),
        (7496, "TWS Live Trading")
    ]
    
    print(f"Testing connectivity to {host}...")
    print()
    
    available_ports = []
    
    for port, description in ports_to_test:
        print(f"Testing port {port} ({description})...", end=" ")
        if test_port_connectivity(host, port):
            print("✅ OPEN")
            available_ports.append((port, description))
        else:
            print("❌ CLOSED")
    
    print()
    
    if not available_ports:
        print("❌ NO PORTS AVAILABLE")
        print("\nTroubleshooting steps:")
        print("1. Make sure TWS or IB Gateway is running")
        print("2. Check if the application is listening on the expected ports")
        print("3. Try starting IB Gateway instead of TWS")
        print("4. Check firewall settings")
        return
    
    print(f"✅ Found {len(available_ports)} available port(s)")
    print()
    
    # Try to connect to the first available port
    for port, description in available_ports:
        print(f"Attempting to connect to {description} on port {port}...")
        
        try:
            broker = IBBroker(host=host, port=port, client_id=1)
            
            if broker.connect():
                print(f"✅ Successfully connected to {description}!")
                print("Connection test passed. You can now run the full example.")
                
                # Test basic functionality
                print("\nTesting basic broker functionality...")
                try:
                    # Test market data type setting
                    broker.set_market_data_type(broker.market_data_type)
                    print("✅ Market data type setting works")
                    
                    # Test getting subscriptions (should be empty)
                    subscriptions = broker.get_market_data_subscriptions()
                    print(f"✅ Subscription management works ({len(subscriptions)} active)")
                    
                except Exception as e:
                    print(f"⚠️  Warning: Some functionality may not work: {e}")
                
                broker.disconnect()
                print("✅ Disconnected successfully")
                return
            else:
                print(f"❌ Failed to connect to {description}")
                
        except Exception as e:
            print(f"❌ Error connecting to {description}: {e}")
    
    print("\n❌ All connection attempts failed")
    print("\nTroubleshooting steps:")
    print("1. Make sure TWS or IB Gateway is running")
    print("2. Check API settings in TWS:")
    print("   - Edit → Global Configuration → API → Settings")
    print("   - Enable 'ActiveX and Socket EClients'")
    print("   - Note the 'Socket Port' number")
    print("3. Try restarting TWS/Gateway")
    print("4. Check if another application is using the same client ID")

if __name__ == "__main__":
    main()
