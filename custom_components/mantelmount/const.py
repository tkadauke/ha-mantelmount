"""Constants for the MantelMount integration."""

from datetime import timedelta

DOMAIN = "mantelmount"
MANUFACTURER = "MantelMount"

IDLE_INTERVAL = timedelta(seconds=5)
MOVING_INTERVAL = timedelta(seconds=1)
COMMAND_FOLLOW_UP = timedelta(seconds=60)
SETTINGS_INTERVAL = timedelta(minutes=5)
POSITION_TOLERANCE = 0.05
