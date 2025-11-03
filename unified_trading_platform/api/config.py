"""
API Configuration Loader
Loads default values from api_config.yaml
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional


class APIConfig:
    """API Configuration manager"""

    _config: Optional[Dict[str, Any]] = None
    _config_path: Optional[Path] = None

    @classmethod
    def _load_config(cls, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if cls._config is not None:
            return cls._config

        if config_path is None:
            # Default to api_config.yaml in the same directory
            current_dir = Path(__file__).parent
            config_path = current_dir / "api_config.yaml"
        else:
            config_path = Path(config_path)

        cls._config_path = config_path

        if not config_path.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {config_path}. "
                "Please create api_config.yaml in the api directory."
            )

        with open(config_path, "r") as f:
            cls._config = yaml.safe_load(f)

        return cls._config

    @classmethod
    def get_config(
        cls, config_path: Optional[str] = None, reload: bool = False
    ) -> Dict[str, Any]:
        """
        Get configuration dictionary.

        Args:
            config_path: Optional path to config file
            reload: Force reload of config

        Returns:
            Configuration dictionary
        """
        if reload:
            cls._config = None

        return cls._load_config(config_path)

    @classmethod
    def get(cls, key_path: str, default: Any = None) -> Any:
        """
        Get a configuration value by key path (e.g., 'api.title' or 'broker.default_host').

        Args:
            key_path: Dot-separated key path
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        config = cls.get_config()
        keys = key_path.split(".")

        value = config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    @classmethod
    def reload(cls):
        """Force reload of configuration"""
        cls._config = None
        cls._load_config()


# Convenience functions
def get_config_path() -> Path:
    """Get the path to the config file"""
    current_dir = Path(__file__).parent
    return current_dir / "api_config.yaml"


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load configuration from YAML file"""
    return APIConfig.get_config(config_path)


def get_config_value(key_path: str, default: Any = None) -> Any:
    """Get a configuration value by key path"""
    return APIConfig.get(key_path, default)
