# ib_broker_options.py
from __future__ import annotations

import threading
import time
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Set
from unified_trading_platform.trading_core.utils.utils import generate_unique_id
from unified_trading_platform.trading_core.data_models.option_chain import (
    OptionChain,
    StrikeGroup,
    ExpirationGroup,
    UnderlyingInfo,
)
from unified_trading_platform.trading_core.data_models.option_contract import OptionContract
from unified_trading_platform.trading_core.data_models import OptionRight
from unified_trading_platform.trading_core.data_models.contract import Contract, SecurityType
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_client import IBClient
from unified_trading_platform.trading_core.brokers.interactive_brokers.ib_market_data import IBMarketDataMixin
from unified_trading_platform.trading_core.utils.logger import get_logger

logger = get_logger(__name__)


class IBOptionsMixin:
    def __init__(self, client: IBClient, market_data: IBMarketDataMixin) -> None:
        self.client = client
        self.market_data = market_data

    def get_option_chain(
        self,
        underlying_contract: Contract,
        expiration_dates: Optional[List[str]] = None,
        strikes: Optional[List[float]] = None,
    ) -> OptionChain:
        logger.info(f"Requesting option chain for {underlying_contract.symbol}")
        req_id, _ = generate_unique_id(prefix="sub_")

        response_received = threading.Event()
        response_received.clear()
        self.client.pending_option_chains[req_id] = {
            "event": response_received,
            "underlying_contract": underlying_contract,
            "params": [],
            "error": None,
        }
        try:
            logger.info(
                f"Requesting option parameters for {underlying_contract.symbol} on exchange \
                {underlying_contract.exchange}"
            )

            # Request option chain parameters
            self.client.reqSecDefOptParams(
                req_id,
                underlying_contract.symbol,
                "",  # fixme: somehow exchange value is not working, so we get all options and filter later underlying_contract.exchange or "",
                underlying_contract.security_type.value,
                getattr(underlying_contract, "conId", 0),
            )

            # Wait for response with timeout
            if not response_received.wait(timeout=30):
                self.client.pending_option_chains.pop(req_id, None)
                raise TimeoutError("Timeout waiting for option chain parameters")

            entry = self.client.pending_option_chains.pop(req_id, None)
            if not entry:
                raise RuntimeError("Option chain request entry missing after completion")

            if entry.get("error"):
                raise RuntimeError(f"IB returned error: {entry['error']}")

            params = entry.get("params") or []
            if not params:
                raise ValueError("IB did not return any option chain parameters")

            # Build the option chain from the parameters
            option_chain = self._build_option_chain_from_params(
                underlying_contract=underlying_contract,
                params=params,
                requested_expirations=expiration_dates,
                requested_strikes=strikes,
            )
            # Just get the last traded price for each option
            logger.info("Requesting LTP for option chain")
            self._request_option_ltp(option_chain)
            return option_chain
        except Exception as e:
            logger.error(f"Error getting option chain: {e}", exc_info=True)
            raise
        finally:
            self.client.pending_option_chains.pop(req_id, None)

    def _request_option_ltp(self, option_chain: OptionChain):
        # Create a list to track active subscriptions
        active_subscriptions = []

        # Create an event to track completion
        completion_event = threading.Event()
        pending_requests = 0

        def on_market_data_update(sub_id, tick_data):
            """Callback for market data updates"""
            nonlocal pending_requests

            # Find the option for this subscription
            for i, (sub_id_stored, option, req_time) in enumerate(active_subscriptions):
                if sub_id_stored == sub_id:
                    # Update the option with the last price if available
                    if tick_data.last is not None:
                        option.ltp = tick_data.last
                        option.last_updated = datetime.utcnow()

                    # Unsubscribe and clean up
                    try:
                        self.market_data.unsubscribe_market_data(sub_id)
                    except Exception as e:
                        logger.warning(f"Error unsubscribing from market data: {e}")

                    # Remove from active subscriptions
                    active_subscriptions.pop(i)
                    pending_requests -= 1

                    # If all requests are done, signal completion
                    if pending_requests <= 0:
                        completion_event.set()
                    break

        # Request LTP for each option
        for exp_group in option_chain.expiration_dates:
            expiry_date = exp_group.expiry_date
            for strike_group in exp_group.strikes:
                strike_price = strike_group.strike_price
                for option in [strike_group.call_option, strike_group.put_option]:
                    if option is not None:
                        try:
                            # Create a contract for the option
                            contract = Contract(
                                symbol=option_chain.contract.symbol,
                                exchange=option_chain.contract.exchange,
                                security_type=SecurityType.OPTION,
                                currency=option_chain.contract.currency,
                                expiry=expiry_date,
                                strike=strike_price,
                                option_right=option.option_right,
                                multiplier=option_chain.contract.multiplier,
                            )

                            # Subscribe with snapshot=True
                            sub_id = self.market_data.subscribe_market_data(
                                contract=contract, callback=on_market_data_update, snapshot=True
                            )

                            # Track this subscription
                            active_subscriptions.append((sub_id, option, time.time()))
                            pending_requests += 1
                        except Exception as e:
                            logger.warning(f"Failed to request LTP for {option.option_ticker}: {e}")

        # Wait for all requests to complete or timeout
        if pending_requests > 0:
            if not completion_event.wait(timeout=15):  # 15 second timeout
                logger.warning("Timeout waiting for LTP updates")

                # Clean up any remaining subscriptions
                for sub_id, _, _ in active_subscriptions:
                    try:
                        self.unsubscribe_market_data(sub_id)
                    except:
                        pass

            # Clear any remaining subscriptions
            active_subscriptions.clear()

    def _build_option_chain_from_params(
        self,
        underlying_contract: Contract,
        params: List[Dict[str, Any]],
        requested_expirations: Optional[List[str]],
        requested_strikes: Optional[List[float]],
    ) -> OptionChain:
        """Transform IB option parameters into our OptionChain data model."""
        combined_expirations: Set[str] = set()
        combined_strikes: Set[float] = set()
        for entry in params:
            combined_expirations.update(entry.get("expirations", []))
            combined_strikes.update(float(strike) for strike in entry.get("strikes", []) if strike is not None)

        if not combined_expirations:
            raise ValueError("IB did not return any expirations for option chain")
        if not combined_strikes:
            raise ValueError("IB did not return any strikes for option chain")

        logger.info(
            "IB option chain params received: expirations=%d, strikes=%d",
            len(combined_expirations),
            len(combined_strikes),
        )
        expiration_list = self._filter_expirations(combined_expirations, requested_expirations)
        strike_list = self._filter_strikes(combined_strikes, requested_strikes)
        lot_size = self._parse_multiplier(params)
        logger.info(
            "Building option chain with %d expirations and up to %d strikes per expiry",
            len(expiration_list),
            len(strike_list),
        )
        expiration_groups: List[ExpirationGroup] = []
        for expiry_str in expiration_list:
            expiry_date = self._parse_expiry_date(expiry_str)
            days_to_expiry = max((expiry_date - datetime.utcnow().date()).days, 0)
            strike_groups = self._build_strike_groups(
                strike_values=strike_list,
                expiry_str=expiry_str,
                lot_size=lot_size,
                underlying_symbol=underlying_contract.symbol,
            )
            if strike_groups:
                expiration_groups.append(
                    ExpirationGroup(
                        expiry_date=expiry_date,
                        days_to_expiry=days_to_expiry,
                        strikes=strike_groups,
                    )
                )

        if not expiration_groups:
            raise ValueError("No expiration groups constructed from IB data")
        underlying_info = UnderlyingInfo(
            underlying_symbol=underlying_contract.symbol,
            underlying_contract=underlying_contract,
        )
        return OptionChain(
            contract=underlying_contract,
            underlying_info=underlying_info,
            expiration_dates=expiration_groups,
            last_updated=datetime.utcnow(),
        )

    def _parse_multiplier(self, params: List[Dict[str, Any]]) -> int:
        for entry in params:
            multiplier = entry.get("multiplier")
            if not multiplier:
                continue
            try:
                return max(int(float(multiplier)), 1)
            except (TypeError, ValueError):
                continue
        return 1

    def _filter_expirations(self, expirations: Set[str], requested: Optional[List[str]], limit: int = 4) -> List[str]:
        normalized = sorted(expirations)
        if requested:
            requested_set = {exp.replace("-", "") for exp in requested}
            filtered = [exp for exp in normalized if exp.replace("-", "") in requested_set]
            if filtered:
                return filtered[:limit]
        return normalized[:limit]

    def _filter_strikes(self, strikes: Set[float], requested: Optional[List[float]], limit: int = 20) -> List[float]:
        sorted_strikes = sorted(strikes)
        if requested:
            requested_set = {float(value) for value in requested}
            filtered = [strike for strike in sorted_strikes if strike in requested_set]
            if filtered:
                return filtered

        if len(sorted_strikes) <= limit:
            return sorted_strikes

        mid = len(sorted_strikes) // 2
        half = limit // 2
        start = max(mid - half, 0)
        end = min(start + limit, len(sorted_strikes))
        return sorted_strikes[start:end]

    def _build_strike_groups(
        self,
        strike_values: List[float],
        expiry_str: str,
        lot_size: int,
        underlying_symbol: str,
    ) -> List[StrikeGroup]:
        strike_groups: List[StrikeGroup] = []
        for strike in strike_values:
            call_option = self._create_option_contract(
                symbol=underlying_symbol,
                expiry_str=expiry_str,
                strike=strike,
                right=OptionRight.CALL,
                lot_size=lot_size,
            )
            put_option = self._create_option_contract(
                symbol=underlying_symbol,
                expiry_str=expiry_str,
                strike=strike,
                right=OptionRight.PUT,
                lot_size=lot_size,
            )
            strike_groups.append(
                StrikeGroup(
                    strike_price=float(strike),
                    call_option=call_option,
                    put_option=put_option,
                )
            )
        return strike_groups

    def _create_option_contract(
        self,
        symbol: str,
        expiry_str: str,
        strike: float,
        right: OptionRight,
        lot_size: int,
    ) -> OptionContract:
        ticker = self._format_option_symbol(symbol, expiry_str, strike, right)
        return OptionContract(
            option_ticker=ticker,
            ltp=0.0,  # Will be updated by market data
            option_right=right,
            lot=lot_size,
            last_updated=datetime.utcnow(),
        )

    def _format_option_symbol(self, symbol: str, expiry_str: str, strike: float, right: OptionRight) -> str:
        try:
            expiry_fmt = datetime.strptime(expiry_str, "%Y%m%d").strftime("%y%m%d")
        except ValueError:
            expiry_fmt = expiry_str
        strike_fmt = f"{strike:08.3f}".replace(".", "")
        return f"{symbol}{expiry_fmt}{right.value}{strike_fmt}"

    def _parse_expiry_date(self, expiry_str: str) -> date:
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                return datetime.strptime(expiry_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Unable to parse expiry date: {expiry_str}")
