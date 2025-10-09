"""Constants for the Russound integration."""

# Integration metadata
DRIVER_ID = "uc_russound_rio"
DRIVER_VERSION = "1.0.21"

# Default connection settings
DEFAULT_PORT = 9621
DEFAULT_CONTROLLER_ID = 1
DEFAULT_ZONES = 8
DEFAULT_RECONNECT_DELAY = 5

# Russound volume mapping (internal 0-50 -> UI 0-100)
RUSSOUND_VOL_MAX = 50
UI_VOL_MAX = 100

# Zone attributes
MIN_VOLUME = 0
MAX_VOLUME = 100
MIN_BASS = -10
MAX_BASS = 10
MIN_TREBLE = -10
MAX_TREBLE = 10
MIN_BALANCE = -10
MAX_BALANCE = 10

# Reconnection settings
RECONNECT_DELAY_MIN = 1
RECONNECT_DELAY_MAX = 60
KEEPALIVE_INTERVAL = 180  # 3 minutes

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_CONTROLLER_ID = "controller_id"
CONF_ZONES = "zones"
