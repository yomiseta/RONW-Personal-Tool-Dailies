"""Entry point: starts the console window."""
import config
import screen

# ----- adjustable values -----
GUILD_WAIT_SECONDS = 200   # how long to wait after accepting the Guild Dailies quests (the character plays them itself)
DAILY_RESET_HOUR = 6       # the hour (0-23, on this PC's clock) when the game's dailies reset. 0 = midnight

config.GUILD_WAIT_SECONDS = GUILD_WAIT_SECONDS
config.DAILY_RESET_HOUR = DAILY_RESET_HOUR

screen.enable_dpi_awareness()  # must run before any window is created

from console import Console  # noqa: E402

if __name__ == "__main__":
    Console().run()