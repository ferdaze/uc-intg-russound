```python
"""Configuration handling for Russound integration."""
import json
import logging
import os
from pathlib import Path
from typing import Any

_LOG = logging.getLogger(__name__)


class RussoundConfig:
    """Configuration manager for Russound integration."""

    def __init__(self):
        """Initialize configuration manager."""
        self.config_dir = os.getenv("UC_CONFIG_HOME", Path.home())
        self.config_file = Path(self.config_dir) / "russound.json"
        self.config = {}

    def load(self) -> dict[str, Any]:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    self.config = json.load(f)
                    _LOG.info("Configuration loaded from %s", self.config_file)
            except Exception as ex:
                _LOG.error("Failed to load configuration: %s", ex)
                self.config = {}
        return self.config

    def save(self, config: dict[str, Any]) -> bool:
        """Save configuration to file."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
            self.config = config
            _LOG.info("Configuration saved to %s", self.config_file)
            return True
        except Exception as ex:
            _LOG.error("Failed to save configuration: %s", ex)
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        return self.config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set configuration value."""
        self.config[key] = value
```
