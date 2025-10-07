"""Configuration management for Russound integration."""
import json
import logging
import os
from typing import Any, Dict, Optional

from const import (
    CONF_HOST,
    CONF_PORT,
    CONF_CONTROLLER_ID,
    CONF_ZONES,
    DEFAULT_PORT,
    DEFAULT_CONTROLLER_ID,
    DEFAULT_ZONES,
)

_LOG = logging.getLogger(__name__)


class RussoundConfig:
    """Manage Russound integration configuration."""

    def __init__(self, config_dir: str):
        """Initialize configuration manager.
        
        Args:
            config_dir: Directory to store configuration files
        """
        self._config_dir = config_dir
        self._config_file = os.path.join(config_dir, "config.json")
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file."""
        if os.path.exists(self._config_file):
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    self._config = json.load(f)
                _LOG.info("Configuration loaded from %s", self._config_file)
            except Exception as e:
                _LOG.error("Failed to load configuration: %s", e)
                self._config = {}
        else:
            _LOG.info("No existing configuration found")
            self._config = {}

    def save(self, config: Dict[str, Any]) -> bool:
        """Save configuration to file.
        
        Args:
            config: Configuration dictionary to save
            
        Returns:
            True if successful, False otherwise
        """
        try:
            os.makedirs(self._config_dir, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            self._config = config
            _LOG.info("Configuration saved to %s", self._config_file)
            return True
        except Exception as e:
            _LOG.error("Failed to save configuration: %s", e)
            return False

    @property
    def host(self) -> Optional[str]:
        """Get Russound device IP address."""
        return self._config.get(CONF_HOST)

    @property
    def port(self) -> int:
        """Get Russound device port."""
        return self._config.get(CONF_PORT, DEFAULT_PORT)

    @property
    def controller_id(self) -> int:
        """Get controller ID."""
        return self._config.get(CONF_CONTROLLER_ID, DEFAULT_CONTROLLER_ID)

    @property
    def zones(self) -> int:
        """Get number of zones."""
        return self._config.get(CONF_ZONES, DEFAULT_ZONES)

    @property
    def is_configured(self) -> bool:
        """Check if integration is configured."""
        return self.host is not None

    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self._config.copy()

    def validate(self, config: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate configuration values.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check required fields
        if not config.get(CONF_HOST):
            return False, "IP address is required"
        
        # Validate port
        port = config.get(CONF_PORT, DEFAULT_PORT)
        if not isinstance(port, int) or port < 1 or port > 65535:
            return False, "Port must be between 1 and 65535"
        
        # Validate controller ID
        controller_id = config.get(CONF_CONTROLLER_ID, DEFAULT_CONTROLLER_ID)
        if not isinstance(controller_id, int) or controller_id < 1 or controller_id > 6:
            return False, "Controller ID must be between 1 and 6"
        
        # Validate zones
        zones = config.get(CONF_ZONES, DEFAULT_ZONES)
        if not isinstance(zones, int) or zones < 1 or zones > 8:
            return False, "Number of zones must be between 1 and 8"
        
        return True, None
