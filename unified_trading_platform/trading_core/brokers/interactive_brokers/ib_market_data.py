from __future__ import annotations

from typing import Dict, List, Callable, Any
from unified_trading_platform.trading_core.brokers.interactive_brokers.common import CommonMixin
from unified_trading_platform.trading_core.data_models.contract import Contract
from .ib_client import IBClient
from unified_trading_platform.trading_core.data_models import MarketDataType
from unified_trading_platform.trading_core.utils.utils import generate_unique_id

from unified_trading_platform.trading_core.utils.logger import get_logger
logger = get_logger(__name__)

class IBMarketDataMixin:
    def __init__(self, client: IBClient, market_data_subscriptions: Dict[str, Dict[str, Any]]) -> None:
        self.client = client
        self.market_data_subscriptions = market_data_subscriptions

    def subscribe_market_data(self, contract: Contract, callback: Callable, **kwargs):
        """Subscribe to market data with enhanced options support"""
        req_id, _ = generate_unique_id(prefix="sub_")

        market_data_type = kwargs.get('market_data_type', MarketDataType.DELAYED)
        snapshot = kwargs.get('snapshot', False)
        regulatory_snapshot = kwargs.get('regulatory_snapshot', False)
        generic_tick_list = kwargs.get('generic_tick_list', [])
        mdoff = "" if not generic_tick_list else "mdoff"  # Check if list is empty

        self.market_data_subscriptions[req_id] = {
            'contract': contract,
            'callback': callback,
            'is_active': False,
            'data': {}
        }
        ib_contract = CommonMixin.create_ib_contract(contract)
        logger.info(f"IB contract created: {ib_contract}")
        try:
            ib_market_data_type = CommonMixin.ib_market_data_type_mapping().get(market_data_type, 3)

            logger.info("Requesting market data market_data_type: %s, req_id: %s, snapshot: %s, \
                regulatory_snapshot: %s, generic_tick_list: %s", ib_market_data_type, req_id, snapshot, \
                    regulatory_snapshot, generic_tick_list)

            self.client.reqMarketDataType(ib_market_data_type)
            self.client.reqMktData(req_id, ib_contract, mdoff, snapshot, regulatory_snapshot, generic_tick_list)

            self.market_data_subscriptions[req_id]['is_active'] = True
            logger.info(f"Market data subscribed, req_id: {req_id}")
            return req_id
        except Exception as e:
            logger.error(f"Error subscribing to market data: {e}", exc_info=True)
            if req_id in self.market_data_subscriptions:
                del self.market_data_subscriptions[req_id]
            raise e

    def unsubscribe_market_data(self, subscription_id: str) -> bool:
        """Unsubscribe from market data using subscription ID"""
        if subscription_id not in self.market_data_subscriptions:
            return False
        try:
            logger.info(f"Unsubscribing from market data: {subscription_id}")
            self.client.cancelMktData(subscription_id)
            del self.market_data_subscriptions[subscription_id]
        except Exception as e:
            logger.error(f"Error unsubscribing from market data: {e}", exc_info=True)
            return False
        return True

    def get_market_data_subscriptions(self) -> List[Dict[str, Any]]:
        """Get all active market data subscriptions"""
        return [sub for sub in self.market_data_subscriptions.values() if sub['is_active']]