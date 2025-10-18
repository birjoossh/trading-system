"""
Example usage of the StrategyManager for both live trading and backtesting.
"""

from unified_trading_platform.trading_core.strategy_engine.strategy_manager import StrategyManager

def live_trading_example():
    """Example of live trading with StrategyManager"""
    print("=== Live Trading Example ===")
    
    # Create strategy manager for live trading
    manager = StrategyManager(
        venue="paper",  # Use paper trading broker
        strategy_name="atm_short_straddle_1100_1515"
    )
    
    try:
        # Initialize the manager
        print("Initializing strategy manager...")
        if manager.initialize():
            print("✓ Strategy manager initialized successfully")
            print(f"Run ID: {manager.run_id}")
            print(f"Strategy: {manager.strategy_name}")
            print(f"Venue: {manager.venue}")
        else:
            print("✗ Failed to initialize strategy manager")
            return
        
        # Start live trading
        print("Starting live trading...")
        if manager.start():
            print("✓ Live trading started")
            
            # Let it run for a while (in real usage, this would be until exit_time)
            import time
            time.sleep(10)  # Run for 10 seconds as example
            
            # Stop trading
            print("Stopping trading...")
            manager.stop()
            print("✓ Trading stopped")
        else:
            print("✗ Failed to start live trading")
    
    except Exception as e:
        print(f"Error in live trading: {e}")
        manager.stop()

def backtesting_example():
    """Example of backtesting with StrategyManager"""
    print("\n=== Backtesting Example ===")
    
    # Create strategy manager for backtesting
    manager = StrategyManager(
        venue="paper",  # Use paper trading broker
        strategy_name="atm_short_straddle_1100_1515",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
    
    try:
        # Initialize the manager
        print("Initializing strategy manager for backtesting...")
        if manager.initialize():
            print("✓ Strategy manager initialized successfully")
            print(f"Run ID: {manager.run_id}")
            print(f"Strategy: {manager.strategy_name}")
            print(f"Backtest period: {manager.start_date} to {manager.end_date}")
        else:
            print("✗ Failed to initialize strategy manager")
            return
        
        # Start backtesting
        print("Starting backtesting...")
        if manager.start():
            print("✓ Backtesting completed")
            
            # Get portfolio summary
            portfolio_summary = manager.get_portfolio_summary()
            print(f"Portfolio Summary: {portfolio_summary}")
        else:
            print("✗ Failed to start backtesting")
    
    except Exception as e:
        print(f"Error in backtesting: {e}")
        manager.stop()

def check_strategy_status():
    """Example of checking strategy status"""
    print("\n=== Strategy Status Check ===")
    
    # This would typically be used to check status of a running strategy
    manager = StrategyManager(
        venue="paper",
        strategy_name="atm_short_straddle_1100_1515"
    )
    
    # Get status information
    status = manager.get_status()
    print(f"Strategy Status: {status}")
    
    # Get portfolio summary
    portfolio = manager.get_portfolio_summary()
    print(f"Portfolio: {portfolio}")

if __name__ == "__main__":
    print("Strategy Manager Examples")
    print("=" * 50)
    
    # Run examples
    live_trading_example()
    backtesting_example()
    check_strategy_status()
    
    print("\n" + "=" * 50)
    print("Examples completed!")
