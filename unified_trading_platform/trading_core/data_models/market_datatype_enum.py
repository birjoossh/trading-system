from enum import Enum


class MarketDataType(Enum):
    """Market data types"""

    LIVE = "LIVE"
    DELAYED = "DELAYED"
    FROZEN = "FROZEN"
    DELAYED_FROZEN = "DELAYED_FROZEN"
