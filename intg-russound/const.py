"""Constants for the Russound integration."""

DRIVER_ID = "russound_rio"
DRIVER_VERSION = "1.0.0"

# Default connection settings
DEFAULT_PORT = 9621
DEFAULT_NAME = "Russound"

# Zone configuration
MAX_ZONES = 8
MAX_SOURCES = 8

# Volume settings
MIN_VOLUME = 0
MAX_VOLUME = 50
VOLUME_STEP = 2

# Media player states
STATE_ON = "ON"
STATE_OFF = "OFF"
STATE_PLAYING = "PLAYING"
STATE_PAUSED = "PAUSED"
STATE_IDLE = "IDLE"

# Features
FEATURES = [
    "on_off",
    "volume",
    "volume_up_down",
    "mute_toggle",
    "select_source",
    "media_title",
    "media_artist",
    "media_album",
    "media_image_url"
]

# Commands
CMD_ON = "on"
CMD_OFF = "off"
CMD_TOGGLE = "toggle"
CMD_VOLUME = "volume"
CMD_VOLUME_UP = "volume_up"
CMD_VOLUME_DOWN = "volume_down"
CMD_MUTE_TOGGLE = "mute_toggle"
CMD_SELECT_SOURCE = "select_source"

# Tone controls
MIN_BASS = -10
MAX_BASS = 10
MIN_TREBLE = -10
MAX_TREBLE = 10
MIN_BALANCE = -10
MAX_BALANCE = 10
