"""Entry point: starts the console window."""
import config
import screen

# ----- adjustable values -----
DAILY_RESET_HOUR = 6   # the hour (0-23, on this PC's clock) when the game's dailies reset. 0 = midnight
# Other settings are in config.ini.

config.DAILY_RESET_HOUR = DAILY_RESET_HOUR

screen.enable_dpi_awareness()  # must run before any window is created

from console import Console  # noqa: E402

if __name__ == "__main__":
    Console().run()