"""
Example usage of the modular trading system.
Demonstrates basic functionality with Interactive Brokers.
"""
import threading
import time
import json
from datetime import datetime, timedelta
from unified_trading_platform.trading_core.trading_system import TradingSystem
from unified_trading_platform.trading_core.config.config import Config
from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.brokers.base_broker import (
    Contract, SecurityType, OptionRight, MarketDataType
)

# Initialize logger
logger = get_logger(__name__)

def print_section(title):
    """Print a formatted section header"""
    logger.info("\n" + "="*60)
    logger.info(f" {title}")
    logger.info("="*60)

def on_order_filled(order):
    """Callback for when an order is filled"""
    logger.info(f"ORDER FILLED: {order.contract.symbol} - {order.filled_quantity} shares")

def on_order_cancelled(order):
    """Callback for trade cancellation"""
    logger.info(f"ORDER CANCELLED: {order.contract.symbol} - {order.order.quantity} shares side: ${order.order.action}")

def on_trade_executed(trade):
    """Callback for trade execution"""
    logger.info(f"TRADE EXECUTED: {trade.contract.symbol} - {trade.quantity} @ ${trade.price}")

def on_market_data(tick_data):
    """Callback for market data updates"""
    logger.info(f"Market Data: {tick_data.symbol} - Bid: {tick_data.bid}, Ask: {tick_data.ask}, Last: {tick_data.last}")

def main():
    """Main example function"""

    print_section("Modular Trading System Example")

    # Initialize the trading system
    config = Config()
    trading_system = TradingSystem()

    # Add Interactive Brokers
    paper_config = config.get_broker_config("paper")
    import os
    h5_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "2024-01-02.h5")
    paper_config.update({"h5_path": h5_path})
    print(f"Using H5 file at: {h5_path}")

    success = trading_system.add_broker(
        name="paper",
        broker_type="paper",
        **paper_config
    )
    if not success:
        logger.error("Failed to connect to Paper Broker")
        return

    # Register callbacks
    trading_system.register_order_callback('order_filled', on_order_filled)
    trading_system.register_order_callback('order_cancelled', on_order_cancelled)
    trading_system.register_order_callback('trade_executed', on_trade_executed)

    try:
        # Get Option chain
        print_section("Getting Option Chain")
        logger.info("Fetching option chain...")
        option_chain = trading_system.get_option_chain("paper", contract=Contract(
            symbol="NIFTY",
            exchange="NSE",
            expiry = "2024-01-04"
        ))
        if option_chain:
            logger.info(f"Retrieved option chain:")
            logger.info(f"\n{option_chain}")

        # Get Historical Data
        print_section("Getting Historical Data")

        logger.info("Fetching historical data...")
        hist_data = trading_system.get_historical_data(
            symbol="NIFTY 50",
            exchange="NSE",
            security_type="STK",
            currency="INR",
            duration="5 D",  # 5 days
            bar_size="1H",
            broker_name="paper"
        )
        if hist_data:
            logger.info(f"Retrieved {len(hist_data)} bars")
            logger.info(f"Latest 5 bars: {hist_data[-5:]}\n")

        # Subscribe to Market Data
        print_section("Subscribing to Market Data")
        trading_system.subscribe_market_data(
            symbol="NIFTY 50",
            exchange="NSE",
            callback=on_market_data,
            broker_name="paper"
        )
        # time.sleep(100)

        #Submit Orders
        print_section("Order Management Examples")

        # Submit a limit buy order
        logger.info("Submitting limit buy order...")
        limit_price = 255.46 #current_price #* 0.99  # 1% below current price

        buy_order_id = trading_system.submit_limit_order(
            symbol="NIFTY 50",
            exchange="NSE",
            action="BUY",
            quantity=100,
            limit_price=limit_price,
            broker_name="paper"
        )

        # Submit a limit sell order
        logger.info("Submitting limit sell order...")
        sell_limit_price = 255.46 #current_price * 1.01  # 1% above current price
        sell_order_id = trading_system.submit_limit_order(
            symbol="NIFTY 50",
            exchange="NSE",
            action="SELL",
            quantity=50,
            limit_price=sell_limit_price,
            broker_name="paper"
        )
        # Check order status
        logger.info("\nChecking order status...")
        buy_status = trading_system.get_order_status(buy_order_id)
        sell_status = trading_system.get_order_status(sell_order_id)
        logger.info(f"Buy Order Status: {buy_status.get('status', 'Unknown')}")
        logger.info(f"Sell Order Status: {sell_status.get('status', 'Unknown')}")

        # Get all orders
        all_orders = trading_system.get_all_orders()
        logger.info(f"\nTotal orders in system: {len(all_orders)}")

        # Example 4: Cancel Orders
        print_section("Cancelling Orders")
        
        print(f"Cancelling buy order {buy_order_id}...")
        cancel_success = trading_system.cancel_order(buy_order_id)
        print(f"Cancel result: {'Success' if cancel_success else 'Failed'}")
        
        print(f"Cancelling sell order {sell_order_id}...")
        cancel_success = trading_system.cancel_order(sell_order_id)
        print(f"Cancel result: {'Success' if cancel_success else 'Failed'}")

        # Account Information
        print_section("Account Information")

        account_info = trading_system.get_account_info("paper")
        if account_info:
            logger.info(f"Account Information: ${json.dumps(account_info)}")

        # Positions
        positions = trading_system.get_positions()
        logger.info(f"\nCurrent Positions: {json.dumps(positions)}")
       
        # Order History
        print_section("Order History")
        order_history = trading_system.get_order_history()
        logger.info(f"All orders in history: {json.dumps(order_history)}")

        # Wait a moment for order updates
        time.sleep(100)
    #     market_data_thread.join()

    except Exception as e:
        logger.error(f"Error during example execution: {e}", exc_info=True)
    finally:
        # Clean shutdown
        print_section("Shutting Down")
        trading_system.shutdown()

if __name__ == "__main__":
    main()