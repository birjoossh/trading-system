"""
Configuration management for the trading system.
Handles broker credentials and system settings.
"""

import json
import os
from typing import Dict, Any, Optional

class Config:
    """Configuration manager"""

    def __init__(self, config_file: str = "config.json"):
        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                return self._default_config()
        else:
            config = self._default_config()
            self.save_config(config)
            return config

    def _default_config(self) -> Dict[str, Any]:
        """Default configuration"""
        return {
            "brokers": {
                "interactive_brokers": {
                    "host": "127.0.0.1",
                    "port": 7498,  # Paper trading port
                    "client_id": 1
                }
            },
            "database": {
                "path": "trading_system.db"
            },
            "logging": {
                "level": "INFO",
                "file": "trading_system.log"
            },
            "system": {
                "max_concurrent_orders": 100,
                "order_timeout": 30,
                "data_cache_ttl": 300
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation"""
        keys = key.split('.')
        value = self.config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save_config(self, config: Optional[Dict[str, Any]] = None):
        """Save configuration to file"""
        config_to_save = config or self.config

        try:
            with open(self.config_file, 'w') as f:
                json.dump(config_to_save, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_broker_config(self, broker_name: str) -> Dict[str, Any]:
        """Get broker configuration"""
        return self.get(f"brokers.{broker_name}", {})