"""
API Configuration Loader
Wraps the unified settings from trading_core.config.config
Maintains backward compatibility for key extraction.
"""

from typing import Any, Dict, Optional
from pathlib import Path
from unified_trading_platform.trading_core.config.config import settings


class APIConfig:
    """API Configuration manager wrapper"""

    # Map legacy short keys to new unified config paths
    KEY_MAPPING = {
        # Broker defaults
        "broker.default_host": "brokers.interactive_brokers.host",
        "broker.default_port": "brokers.interactive_brokers.port",
        "broker.default_client_id": "brokers.interactive_brokers.client_id",
        # Contract defaults
        "contract.default_security_type": "defaults.contract.security_type",
        "contract.default_currency": "defaults.contract.currency",
        "contract.default_exchange": "defaults.contract.exchange",
        "contract.default_time_in_force": "defaults.contract.time_in_force",
        # Data defaults
        "data.default_duration": "defaults.data.duration",
        "data.default_bar_size": "defaults.data.bar_size",
        "data.default_market_data_type": "defaults.data.market_data_type",
        "data.default_snapshot": "defaults.data.snapshot",
        # Strategy defaults
        "strategy.default_status": "defaults.strategy.status",
        "strategy.default_db_path": "defaults.strategy.db_path",
        # Portfolio defaults
        "portfolio.default_total_pnl": "defaults.portfolio.total_pnl",
        "portfolio.default_open_positions": "defaults.portfolio.open_positions",
        "portfolio.default_closed_positions": "defaults.portfolio.closed_positions",
        "portfolio.default_total_positions": "defaults.portfolio.total_positions",
        "portfolio.default_pending_reentries": "defaults.portfolio.pending_reentries",
    }

    @classmethod
    def get_config(cls, config_path: Optional[str] = None, reload: bool = False) -> Dict[str, Any]:
        """Get full configuration dictionary"""
        return settings.config

    @classmethod
    def get(cls, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        Transparently maps legacy key paths to new unified structure.
        """
        # specialized mapping for mapped keys
        if key_path in cls.KEY_MAPPING:
            remapped_key = cls.KEY_MAPPING[key_path]
            return settings.get(remapped_key, default)

        # Fallback for keys that match (e.g. from api section)
        return settings.get(key_path, default)

    @classmethod
    def reload(cls):
        """Force reload"""
        settings._load_config()


# Convenience functions
def get_config_path() -> Path:
    """Get the path to the config file"""
    return Path("config.yaml").absolute()


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration"""
    return settings.config


def get_config_value(key_path: str, default: Any = None) -> Any:
    """Get a configuration value by key path"""
    return APIConfig.get(key_path, default)
