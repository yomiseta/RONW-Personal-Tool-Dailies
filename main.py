"""Entry point: starts the console window."""
import screen

screen.enable_dpi_awareness()  # must run before any window is created

from console import Console  # noqa: E402

if __name__ == "__main__":
    Console().run()