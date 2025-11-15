"""
Example usage of the StrategyManager for both live trading and backtesting.
"""

from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager
from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)

def live_trading_example():
    """Example of live trading with StrategyManager"""
    logger.info("=== Live Trading Example ===")
    
    # Create strategy manager for live trading
    manager = StrategyManager(
        venue="interactive_brokers",  # Use paper trading broker
        strategy_name="atm_short_straddle_1100_1515"
    )
    
    try:
        # Initialize the manager
        logger.info("Initializing strategy manager...")
        if manager.initialize():
            logger.info("✓ Strategy manager initialized successfully")
            logger.info(f"Run ID: {manager.run_id}")
            logger.info(f"Strategy: {manager.strategy_name}")
            logger.info(f"Venue: {manager.venue}")
        else:
            logger.error("✗ Failed to initialize strategy manager")
            return
        
        # Start live trading
        logger.info("Starting live trading..........")
        if manager.start():
            logger.info("✓ Live trading started")
            
            # Let it run for a while (in real usage, this would be until exit_time)
            import time
            time.sleep(10)  # Run for 10 seconds as example
            
            # Stop trading
            logger.info("Stopping trading...")
            manager.stop()
            logger.info("✓ Trading stopped")
        else:
            logger.error("✗ Failed to start live trading")

    except Exception as e:
        logger.error(f"Error in live trading: {e}", exc_info=True)
        manager.stop()

def backtesting_example():
    """Example of backtesting with StrategyManager"""
    logger.info("\n=== Backtesting Example ===")
    
    # Create strategy manager for backtesting
    manager = StrategyManager(
        venue="paper",  # Use paper trading broker
        strategy_name="atm_short_straddle_1100_1515",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    
    try:
        # Initialize the manager
        logger.info("Initializing strategy manager for backtesting...")
        if manager.initialize():
            logger.info("✓ Strategy manager initialized successfully")
            logger.info(f"Run ID: {manager.run_id}")
            logger.info(f"Strategy: {manager.strategy_name}")
            logger.info(f"Backtest period: {manager.start_date} to {manager.end_date}")
        else:
            logger.error("✗ Failed to initialize strategy manager")
            return
        
        # Start backtesting
        # print("Starting backtesting...")
        # if manager.start():
        #     print("✓ Backtesting completed")
            
        #     # Get portfolio summary
        #     portfolio_summary = manager.get_portfolio_summary()
        #     print(f"Portfolio Summary: {portfolio_summary}")
        # else:
        #     print("✗ Failed to start backtesting")
    
    except Exception as e:
        logger.error(f"Error in backtesting: {e}", exc_info=True)
        manager.stop()

def check_strategy_status():
    """Example of checking strategy status"""
    logger.info("\n=== Strategy Status Check ===")
    
    # This would typically be used to check status of a running strategy
    manager = StrategyManager(
        venue="paper",
        strategy_name="atm_short_straddle_1100_1515"
    )
    
    # Get status information
    status = manager.get_status()
    logger.info(f"Strategy Status: {status}")
    
    # Get portfolio summary
    portfolio = manager.get_portfolio_summary()
    logger.info(f"Portfolio: {portfolio}")

if __name__ == "__main__":
    logger.info("Strategy Manager Examples")
    logger.info("=" * 50)
    
    # Run examples
    live_trading_example()
    # backtesting_example()
    # check_strategy_status()
    
    logger.info("\n" + "=" * 50)
    logger.info("Examples completed!")