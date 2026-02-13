"""
Example usage of the modular trading system.
Demonstrates basic functionality with Interactive Brokers.
"""

import threading
import time
from unified_trading_platform.trading_core.trading_system import TradingSystem
from unified_trading_platform.trading_core.config.config import settings
from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.data_models import SecurityType

# Initialize logger
logger = get_logger(__name__)


def print_section(title):
    """Print a formatted section header"""
    logger.info("\n" + "=" * 60)
    logger.info(f" {title}")
    logger.info("=" * 60)


def on_order_filled(order):
    """Callback for when an order is filled"""
    logger.info(f"ORDER FILLED: {order.contract.symbol} - {order.filled_quantity} shares")


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
    # config = Config() # No longer needed, use settings
    trading_system = TradingSystem()

    # Add Interactive Brokers
    print_section("Adding Interactive Brokers")
    ib_config = settings.get_broker_config("interactive_brokers")
    logger.debug(f"ib_config = {ib_config}")
    success = trading_system.add_broker(
        name="ib",
        broker_type="ib",
        host=ib_config.get("host", "127.0.0.1"),
        port=ib_config.get("port", 4002),
        client_id=ib_config.get("client_id", 1),
    )

    if not success:
        logger.error("Failed to connect to Interactive Brokers. Make sure TWS/Gateway is running.")
        return

    # Register callbacks
    trading_system.register_order_callback("order_filled", on_order_filled)
    trading_system.register_order_callback("trade_executed", on_trade_executed)

    try:
        # Get Historical Data
        print_section("Getting Historical Data")

        logger.info("Fetching historical data for AAPL...")
        hist_data = trading_system.get_historical_data(
            symbol="AAPL",
            exchange="NASDAQ",
            security_type=SecurityType.STOCK,
            currency="USD",
            duration="5 D",  # 5 days
            bar_size="1 hour",
            broker_name="ib",
        )
        if len(hist_data) > 0:
            logger.info(f"Retrieved {len(hist_data)} bars")
            logger.info("Latest 5 bars:")
            logger.info(f"\n{hist_data[:-5]}")

        # Subscribe to Market Data
        print_section("Subscribing to Market Data")

        def start_market_data_subscription():
            trading_system.subscribe_market_data(
                symbol="AAPL", exchange="NASDAQ", callback=on_market_data, broker_name="ib"
            )

        market_data_thread = threading.Thread(target=start_market_data_subscription, daemon=False)
        market_data_thread.start()

        # Submit Orders
        print_section("Order Management Examples")

        # Submit a limit buy order
        logger.info("Submitting limit buy order for 100 AAPL shares...")
        limit_price = 255.46  # current_price #* 0.99  # 1% below current price

        buy_order_id = trading_system.submit_limit_order(
            symbol="AAPL", exchange="SMART", action="BUY", quantity=100, limit_price=limit_price, broker_name="ib"
        )
        logger.info(f"Buy order submitted with ID: {buy_order_id}")

        # Submit a limit sell order
        logger.info("Submitting limit sell order for 50 AAPL shares...")
        sell_limit_price = 255.46  # current_price * 1.01  # 1% above current price

        sell_order_id = trading_system.submit_limit_order(
            symbol="AAPL", exchange="SMART", action="SELL", quantity=50, limit_price=sell_limit_price, broker_name="ib"
        )

        logger.info(f"Sell order submitted with ID: {sell_order_id}")

        # Wait a moment for order updates
        time.sleep(3)

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
        # print_section("Account Information")

        # account_info = trading_system.get_account_info("ib")
        # if account_info:
        #     logger.info(f"Account Information: ${json.dump()}")

        # # Positions
        # positions = trading_system.get_positions()
        # logger.info(f"\nCurrent Positions: {json.dumps(positions)}")

        # # Order History
        # print_section("Order History")
        # order_history = trading_system.get_order_history()
        # logger.info(f"All orders in history: {json.dumps(order_history)}")

        time.sleep(15)
        market_data_thread.join()

    except Exception as e:
        logger.error(f"Error during example execution: {e}", exc_info=True)
    finally:
        # Clean shutdown
        print_section("Shutting Down")
        trading_system.shutdown()


if __name__ == "__main__":
    main()
