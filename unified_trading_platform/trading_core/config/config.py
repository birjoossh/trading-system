"""
Configuration management for the trading system.
Handles broker credentials and system settings.
"""

import json
import os
import yaml
from typing import Dict, Any, Optional

from unified_trading_platform.trading_core.utils import get_logger

# Initialize logger
logger = get_logger(__name__)


class Config:
    """Configuration manager"""

    def __init__(self, config_file: Optional[str] = None):
        # Priority:
        # 1. Constructor arg
        # 2. config.yaml (new standard)
        # 3. config.json (legacy fallback)
        if config_file:
            self.config_file = config_file
        elif os.path.exists("config.yaml"):
            self.config_file = "config.yaml"
        else:
            self.config_file = "config.json"

        self.config = self._load_config()
        self._apply_env_overrides()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file (YAML or JSON)"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    if self.config_file.endswith((".yaml", ".yml")):
                        return yaml.safe_load(f) or {}
                    else:
                        return json.load(f)
            except Exception as e:
                logger.error(f"Error loading config {self.config_file}: {e}", exc_info=True)
                return self._default_config()
        else:
            # If default file name doesn't exist, create default config (as YAML)
            logger.warning(f"Config file {self.config_file} not found. Creating default.")
            config = self._default_config()
            self.save_config(config)
            return config

    def _apply_env_overrides(self):
        """
        Apply environment variable overrides.
        Format: TRADING_CONFIG__SECTION__KEY=value
        Example: TRADING_CONFIG__LOGGING__LEVEL=DEBUG overrides logging.level
        """
        prefix = "TRADING_CONFIG__"
        for env_key, env_val in os.environ.items():
            if env_key.startswith(prefix):
                # Remove prefix and lower case the rest
                key_path = env_key[len(prefix) :].lower().replace("__", ".")

                # Convert value types if possible
                if env_val.lower() == "true":
                    val = True
                elif env_val.lower() == "false":
                    val = False
                elif env_val.isdigit():
                    val = int(env_val)
                else:
                    try:
                        val = float(env_val)
                    except ValueError:
                        val = env_val

                self.set(key_path, val)
                logger.info(f"Overridden config {key_path} from environment variable")

    def _default_config(self) -> Dict[str, Any]:
        """Default configuration structure"""
        return {
            "brokers": {
                "interactive_brokers": {
                    "enabled": True,
                    "host": "127.0.0.1",
                    "port": 7497,
                    "client_id": 1,
                    "timeout": 10,
                },
                "paper_broker": {"enabled": True, "data_dir": "data/paper"},
            },
            "database": {"path": "trading_system.db", "type": "sqlite"},
            "logging": {"level": "INFO", "file": "trading_system.log", "console": True},
            "system": {"max_concurrent_orders": 100, "order_timeout": 30, "data_cache_ttl": 300},
            "api": {"title": "Unified Trading Platform API", "version": "0.1.0"},
            "defaults": {
                "contract": {"security_type": "STK", "currency": "USD"},
                "data": {"bar_size": "1 hour"},
                "portfolio": {"total_pnl": 0.0},
            },
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split(".")
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        keys = key.split(".")
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            if not isinstance(config[k], dict):
                # Config structure mismatch vs value being set (trying to traverse a leaf)
                # Force convert to dict to allow setting deep key?
                # Or just overwrite. Safe to overwrite for now.
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file (preserves format based on extension)"""
        config_to_save = config or self.config

        # If writing to new default
        target_file = self.config_file
        if target_file == "config.json" and os.path.exists("config.yaml"):
            # If we loaded standard config.yaml but save is called without arg?
            # Actually self.config_file would be config.yaml in that case.
            pass

        try:
            with open(target_file, "w") as f:
                if target_file.endswith((".yaml", ".yml")):
                    yaml.dump(config_to_save, f, sort_keys=False, indent=2)
                else:
                    json.dump(config_to_save, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving config: {e}", exc_info=True)

    def get_broker_config(self, broker_name: str) -> Dict[str, Any]:
        """Get broker configuration"""
        return self.get(f"brokers.{broker_name}", {})


# Global instance for easy access
settings = Config()
