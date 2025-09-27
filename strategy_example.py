"""
Example usage of the modular trading system.
Demonstrates basic functionality with Interactive Brokers.
"""

import time
from datetime import datetime, timedelta
from trading_system.main import TradingSystem
from trading_system.config.config import Config

def print_section(title):
    """Print a formatted section header"""
    print("\n" + "="*60)
    print(f" {title}")
    print("="*60)

def on_order_filled(order):
    """Callback for when an order is filled"""
    print(f"ORDER FILLED: {order.contract.symbol} - {order.filled_quantity} shares")

def on_trade_executed(trade):
    """Callback for trade execution"""
    print(f"TRADE EXECUTED: {trade.contract.symbol} - {trade.quantity} @ ${trade.price}")

def on_market_data(tick_data):
    """Callback for market data updates"""
    print(f"Market Data: {tick_data.symbol} - Bid: {tick_data.bid}, Ask: {tick_data.ask}, Last: {tick_data.last}")

def main():
    """Main example function"""

    print_section("Modular Trading System Example")

    # Initialize the trading system
    config = Config()
    trading_system = TradingSystem()

    # Add Interactive Brokers
    print_section("Adding Interactive Brokers")
    ib_config = config.get_broker_config("interactive_brokers")

    success = trading_system.add_broker(
        name="ib_paper",
        broker_type="ib",
        host=ib_config.get("host", "127.0.0.1"),
        port=ib_config.get("port", 7498),
        client_id=ib_config.get("client_id", 1)
    )

    if not success:
        print("Failed to connect to Interactive Brokers. Make sure TWS/Gateway is running.")
        return

    # Register callbacks
    trading_system.register_order_callback('order_filled', on_order_filled)
    trading_system.register_order_callback('trade_executed', on_trade_executed)

    try:
        # Example 1: Get Historical Data
        print_section("Getting Historical Data")

        print("Fetching historical data for AAPL...")
        hist_data = trading_system.get_historical_data(
            symbol="AAPL",
            exchange="SMART",
            security_type="STK",
            currency="USD",
            duration="5 D",  # 5 days
            bar_size="1 hour",
            broker_name="ib_paper"
        )

        if not hist_data.empty:
            print(f"Retrieved {len(hist_data)} bars")
            print("Latest 5 bars:")
            print(hist_data.tail())

            # Calculate some simple statistics
            print(f"\nPrice Statistics:")
            print(f"Current Price: ${hist_data['close'].iloc[-1]:.2f}")
            print(f"5-Day High: ${hist_data['high'].max():.2f}")
            print(f"5-Day Low: ${hist_data['low'].min():.2f}")
            print(f"Average Volume: {hist_data['volume'].mean():.0f}")
        else:
            print("No historical data received")

        # Example 2: Subscribe to Market Data
        print_section("Subscribing to Market Data")

        print("Subscribing to AAPL market data...")
        trading_system.subscribe_market_data(
            symbol="AAPL",
            exchange="SMART",
            callback=on_market_data,
            broker_name="ib_paper"
        )

        # Let it run for a few seconds to see market data
        print("Receiving market data for 10 seconds...")
        time.sleep(10)

        # Example 3: Submit Orders
        print_section("Order Management Examples")

        # Submit a limit buy order
        print("Submitting limit buy order for 100 AAPL shares...")
        current_price = hist_data['close'].iloc[-1] if not hist_data.empty else 150.0
        limit_price = current_price * 0.99  # 1% below current price

        buy_order_id = trading_system.submit_limit_order(
            symbol="AAPL",
            exchange="SMART",
            action="BUY",
            quantity=100,
            limit_price=limit_price,
            broker_name="ib_paper"
        )

        print(f"Buy order submitted with ID: {buy_order_id}")

        # Submit a limit sell order
        print("Submitting limit sell order for 50 AAPL shares...")
        sell_limit_price = current_price * 1.01  # 1% above current price

        sell_order_id = trading_system.submit_limit_order(
            symbol="AAPL",
            exchange="SMART",
            action="SELL",
            quantity=50,
            limit_price=sell_limit_price,
            broker_name="ib_paper"
        )

        print(f"Sell order submitted with ID: {sell_order_id}")

        # Wait a moment for order updates
        time.sleep(3)

        # Check order status
        print("\nChecking order status...")
        buy_status = trading_system.get_order_status(buy_order_id)
        sell_status = trading_system.get_order_status(sell_order_id)

        print(f"Buy Order Status: {buy_status.get('status', 'Unknown')}")
        print(f"Sell Order Status: {sell_status.get('status', 'Unknown')}")

        # Get all orders
        all_orders = trading_system.get_all_orders()
        print(f"\nTotal orders in system: {len(all_orders)}")

        # Example 4: Cancel Orders
        print_section("Cancelling Orders")

        print(f"Cancelling buy order {buy_order_id}...")
        cancel_success = trading_system.cancel_order(buy_order_id)
        print(f"Cancel result: {'Success' if cancel_success else 'Failed'}")

        print(f"Cancelling sell order {sell_order_id}...")
        cancel_success = trading_system.cancel_order(sell_order_id)
        print(f"Cancel result: {'Success' if cancel_success else 'Failed'}")

        # Example 5: Account Information
        print_section("Account Information")

        account_info = trading_system.get_account_info("ib_paper")
        if account_info:
            print("Account Information:")
            for key, value in account_info.items():
                if isinstance(value, dict):
                    print(f"  {key}: {value.get('value', 'N/A')}")
                else:
                    print(f"  {key}: {value}")
        else:
            print("No account information available")

        # Example 6: Positions
        positions = trading_system.get_positions()
        print(f"\nCurrent Positions: {len(positions)}")
        for position in positions[:5]:  # Show first 5 positions
            print(f"  {position.get('symbol', 'N/A')}: {position.get('position', 0)} shares")

        # Example 7: Order History
        print_section("Order History")

        order_history = trading_system.get_order_history()
        print(f"Total orders in history: {len(order_history)}")

        # Show recent orders
        for order in order_history[:3]:
            print(f"  {order.get('symbol')} - {order.get('action')} {order.get('quantity')} - {order.get('status')}")

    except Exception as e:
        print(f"Error during example execution: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Clean shutdown
        print_section("Shutting Down")
        trading_system.shutdown()

if __name__ == "__main__":
    main()