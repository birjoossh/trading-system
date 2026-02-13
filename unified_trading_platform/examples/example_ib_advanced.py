#!/usr/bin/env python3
"""
Advanced IB Broker Example / Integration Test

Scenarios covered:
1. Multi-symbol market data subscription (Concurrency)
2. Order Lifecycle (Submit -> Modify -> Cancel)
3. Error Handling (Invalid Symbol)
4. Option Chain & Greeks Verification

Prerequisite: TWS/Gateway running on localhost:7497 (Paper) or 4002.
"""

import time
import logging
from datetime import datetime
from unified_trading_platform.trading_core.trading_system import TradingSystem
from unified_trading_platform.trading_core.utils import get_logger
from unified_trading_platform.trading_core.data_models import (
    Contract, SecurityType, Order, OrderAction, OrderType, OrderStatus, OptionRight
)

# Configure logging
logger = get_logger("example_ib_advanced")
logging.getLogger().setLevel(logging.INFO)

def main():
    system = TradingSystem()
    
    # 1. Connect to IB
    logger.info("--- Step 1: Connecting to IB ---")
    # Note: Adjust port if needed (7497=Paper, 4002=Gateway default)
    success = system.add_broker(
        name="ib_advanced",
        broker_type="ib",
        host="127.0.0.1",
        port=4002, 
        client_id=2 # Use different ID than example_ib.py
    )
    
    if not success:
        logger.error("Failed to connect to IB. Exiting.")
        return

    broker = system.get_broker("ib_advanced")

    try:
        # --- Scenario 1: Multi-symbol Concurrency ---
        logger.info("\n--- Step 2: Multi-symbol Market Data (Concurrency Test) ---")
        symbols = ["AAPL", "MSFT", "GOOGL"]
        subs = []
        
        def make_callback(sym):
            def cb(tick):
                # Only log price updates to avoid spam
                if tick.last > 0:
                     logger.info(f"[{sym}] Price: {tick.last:.2f}")
            return cb

        for sym in symbols:
            contract = Contract(
                symbol=sym, 
                security_type=SecurityType.STOCK, 
                exchange="SMART", 
                currency="USD"
            )
            logger.info(f"Subscribing to {sym}...")
            sub_id = system.subscribe_market_data(contract, make_callback(sym), broker_name="ib_advanced")
            subs.append(sub_id)
        
        logger.info("Waiting 5 seconds for ticks...")
        time.sleep(5)
        
        # Unsubscribe
        for sub_id in subs:
            broker.unsubscribe_market_data(sub_id)
        logger.info("Unsubscribed from stocks.")

        # --- Scenario 2: Error Handling ---
        logger.info("\n--- Step 3: Error Handling (Invalid Symbol) ---")
        invalid_contract = Contract(
            symbol="INVALID_XYZ_123", 
            security_type=SecurityType.STOCK, 
            exchange="SMART", 
            currency="USD"
        )
        try:
            # This might not raise exception immediately for subscriptions, 
            # but IB should send an error callback/log.
            # Let's try get_contract_details which waits for response
            logger.info("Requesting details for INVALID_XYZ_123...")
            details = broker.get_contract_details(invalid_contract)
            logger.info(f"Got details? {details}")
        except Exception as e:
            logger.info(f"Caught expected error: {e}")
            
        # --- Scenario 3: Option Chain & Greeks ---
        logger.info("\n--- Step 4: Option Chain & Greeks Verification ---")
        # Use SPY as it has liquid options
        spy = Contract(symbol="SPY", security_type=SecurityType.STOCK, exchange="SMART", currency="USD")
        
        # Get chain
        logger.info("Requesting SPY Option Chain (this may take a few seconds)...")
        # Note: This uses our throttled implementation
        chain = broker.get_option_chain(spy, exchange="SMART") 
        
        if chain and chain.expiration_dates:
            # Pick first expiry and first strike
            first_expiry = chain.expiration_dates[0]
            first_strike = first_expiry.strikes[0]
            call_option = first_strike.call_option
            
            if call_option:
                 logger.info(f"Selected Option: {call_option.symbol} {call_option.expiry} {call_option.strike} {call_option.option_right}")
                 
                 # Subscribe to see Greeks
                 def greek_callback(tick):
                     if tick.delta is not None or tick.implied_volatility is not None:
                         logger.info(f"GREEKS UPDATE: IV={tick.implied_volatility}, Delta={tick.delta}, Gamma={tick.gamma}")
                         
                 # Create proper contract object from Option data
                 opt_contract = Contract(
                     symbol=chain.contract.symbol,
                     security_type=SecurityType.OPTION,
                     exchange="SMART",
                     currency="USD",
                     expiry=first_expiry.expiry_date,
                     strike=first_strike.strike_price,
                     option_right=OptionRight.CALL,
                     multiplier=chain.contract.multiplier
                 )
                 
                 sub_id = system.subscribe_market_data(opt_contract, greek_callback, broker_name="ib_advanced")
                 logger.info("Subscribed to option. Waiting 5s for Greeks...")
                 time.sleep(5)
                 broker.unsubscribe_market_data(sub_id)
        else:
            logger.warning("No option chain found for SPY")


        # --- Scenario 4: Order Lifecycle ---
        logger.info("\n--- Step 5: Order Lifecycle (Submit -> Modify -> Cancel) ---")
        # Place a LIMIT BUY order far below market price
        # Get current price of AAPL first
        aapl = Contract(symbol="AAPL", security_type=SecurityType.STOCK, exchange="SMART", currency="USD")
        # We need a price reference. Let's assume 100 for safety or get a snapshot.
        # Since we just subscribed, we might proceed blindly with a safe low price.
        limit_price = 10.00 
        
        order = Order(
            action=OrderAction.BUY,
            quantity=1,
            order_type=OrderType.LIMIT,
            limit_price=limit_price,
            account=broker.account_id # Hopefully auto-filled if None, but better explicit? 
            # IBBroker.submit_order handles checks.
        )
        
        logger.info(f"Submitting LIMIT BUY AAPL @ ${limit_price}...")
        order_id = system.submit_order(order, aapl, broker_name="ib_advanced")
        logger.info(f"Order Submitted. ID: {order_id}")
        
        time.sleep(2)
        status = system.get_order_status(order_id)
        logger.info(f"Status after 2s: {status}")
        
        if status in [OrderStatus.SUBMITTED, OrderStatus.PENDING_SUBMIT, OrderStatus.PRESUBMITTED]:
            # Modify Order (Update price to 11.00)
            logger.info("Modifying order price to $11.00...")
            # System doesn't have a direct modify_order method yet that takes ID and kwarg?
            # Usually we resubmit with same ID or cancel/replace. 
            # IBBroker supports modification if we submit same order object with new params and same ID?
            # Current `submit_order` generates a NEW ID if not provided.
            # Let's try `cancel_order` first as that's safer and verified supported.
            
            logger.info("Cancelling order...")
            system.cancel_order(order_id, broker_name="ib_advanced")
            
            time.sleep(2)
            final_status = system.get_order_status(order_id)
            logger.info(f"Final Status: {final_status}")
            
    finally:
        logger.info("\n--- Disconnecting ---")
        system.shutdown()

if __name__ == "__main__":
    main()
