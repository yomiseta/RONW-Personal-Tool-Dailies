"""Entry point: starts the console window."""
import config
import screen

# ----- adjustable values -----
GUILD_WAIT_SECONDS = 200   # how long to wait after accepting the Guild Dailies quests (the character plays them itself)

config.GUILD_WAIT_SECONDS = GUILD_WAIT_SECONDS

screen.enable_dpi_awareness()  # must run before any window is created

from console import Console  # noqa: E402

if __name__ == "__main__":
    Console().run()