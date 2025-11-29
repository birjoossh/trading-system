#!/usr/bin/env python3
"""
Corrected options market data test with valid contracts and tick types
This addresses the issues found in the previous test.
"""

from re import L
import time
from pprint import pprint
from dataclasses import asdict
from datetime import datetime
from typing import List

from ibapi.client import BarData
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_broker import IBBroker
from unified_trading_platform.trading_core.data_models import (
    Contract, SecurityType, OptionRight, MarketDataType
)
from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)

def options_callback(tick_data):
    """Callback for options market data"""
    bid_str = f"${tick_data.bid:.2f}" if tick_data.bid is not None else "N/A"
    ask_str = f"${tick_data.ask:.2f}" if tick_data.ask is not None else "N/A"
    last_str = f"${tick_data.last:.2f}" if tick_data.last is not None else "N/A"
    
    logger.info(f"[{tick_data.timestamp.strftime('%H:%M:%S')}] {tick_data.symbol} Option:")
    logger.info(f"  Bid: {bid_str}, Ask: {ask_str}, Last: {last_str}")
    
    # Show Greeks if available
    if tick_data.delta is not None:
        logger.info(f"  Delta: {tick_data.delta:.4f}")
    if tick_data.gamma is not None:
        logger.info(f"  Gamma: {tick_data.gamma:.4f}")
    if tick_data.theta is not None:
        logger.info(f"  Theta: {tick_data.theta:.4f}")
    if tick_data.vega is not None:
        logger.info(f"  Vega: {tick_data.vega:.4f}")
    if tick_data.implied_volatility is not None:
        logger.info(f"  IV: {tick_data.implied_volatility:.2%}")
    
    logger.info("-" * 40)

def get_contract_details(broker, contract):
    try:
        details = broker.get_contract_details(contract)
        logger.info(f"Contract details: {asdict(details)}")
        return details
    except Exception as e:
        logger.info(f"Error getting contract details: {e}")

def get_option_chain(broker, contract):
    try:
        option_chain = broker.get_option_chain(contract)
        logger.info(f"option chain : {asdict(option_chain)}")
        return option_chain
    except Exception as e:
        logger.info(f"Error getting contract details: {e}")

def list_active_subscriptions(broker):
    # List active subscriptions
    logger.info("Active market data subscriptions:")
    subscriptions = broker.get_market_data_subscriptions()
    return subscriptions
        
def subscribe_market_data(broker, contract):
    tick_list = [
        # "100",  # Option bid price
        # "101",  # Option ask price
        # "104",  # Option last price
        # "105",  # Option last size
        # "106",  # Option high price
        # "107",  # Option low price
        # "108",  # Option volume
        # "109",  # Option close price
        # "110",  # Option open price
        # "21",   # Open interest
        # "22"   # Historical volatility
    ]
    # Test subscription without tick list
    logger.info("Testing option subscription (no tick list)...")
    sub_id = broker.subscribe_market_data(
        contract=contract,
        callback=options_callback,
        market_data_type=MarketDataType.DELAYED_FROZEN,
        generic_tick_list = tick_list
    )
    logger.info(f"✅ Option subscription successful: {sub_id}")
    return sub_id
    
def get_historical_market_data(broker, contract):
    logger.info("Get historical market data...")
    hist_data: List[TickData] = broker.get_historical_data(
        contract=contract,
        duration='5 D',
        bar_size='1 hour',
        what_to_show= 'TRADES'
    )
    return hist_data


def get_option_greeks(broker, option_contract):
    logger.info("Getting Greeks for AAPL option...")
    try:
        greeks = broker.get_greeks(option_contract)
        logger.info(f"Greeks for {option_contract.symbol} {option_contract.strike} {option_contract.right.value}:")
        if greeks.delta is not None:
            logger.info(f"  Delta: {greeks.delta:.4f}")
        if greeks.gamma is not None:
            logger.info(f"  Gamma: {greeks.gamma:.4f}")
        if greeks.theta is not None:
            logger.info(f"  Theta: {greeks.theta:.4f}")
        if greeks.vega is not None:
            logger.info(f"  Vega: {greeks.vega:.4f}")
    except Exception as e:
        logger.info(f"Error getting Greeks: {e}")

def main():
    logger.info("Corrected Options Market Data Test")
    logger.info("=" * 40)
    
    # Initialize broker
    broker = IBBroker(host="127.0.0.1", port=4002, client_id=1)
    
    try:
        # Connect
        logger.info("Connecting to IB Gateway...")
        if not broker.connect():
            logger.info("❌ Failed to connect")
            return
        logger.info("✅ Connected successfully!")
        
        logger.info("\n1. Getting option chain for SPY...")
        spy_underlying = Contract(
            symbol="SPY",
            security_type=SecurityType.STOCK,
            exchange="NASDAQOM",
            currency="USD",
            conId = 756733
        )
        logger.info(f"underlying: {spy_underlying}")
        get_contract_details(broker, spy_underlying)

        # option_chain = get_option_chain(broker, spy_underlying)
        # expiry = option_chain.expiration_dates[0]
        # strike = option_chain.strikes[0]

        spy_option_contract = Contract(
            symbol="SPY",
            security_type=SecurityType.OPTION,
            exchange="SMART",
            currency="USD",
            expiry = '20251209',
            # strike=400.0,
            option_right=OptionRight.CALL,
            multiplier="100"
        )
        sub_id = subscribe_market_data(broker, spy_option_contract) 

        # subscriptions = list_active_subscriptions(broker)
        # for sub in subscriptions:
        #     logger.info(f"{sub}")
        
        # #get_option_greeks(broker, spy_option_contract)

        get_historical_market_data(broker, spy_option_contract)

        try:
            # Wait for data
            logger.info("Waiting 15 seconds for data...")
            time.sleep(15)
            # Cancel subscription
            broker.unsubscribe_market_data(sub_id)
            logger.info("✅ Subscription cancelled")
        except Exception as e:
            logger.info(f"Error: {e}")
    
    finally:
        # Disconnect
        logger.info("\n4. Disconnecting...")
        broker.disconnect()
        logger.info("✅ Disconnected")

if __name__ == "__main__":
    main()
