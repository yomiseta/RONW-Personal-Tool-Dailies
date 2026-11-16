import screen

screen.enable_dpi_awareness()  # must happen before any window exists

from console import Console  # noqa: E402

if __name__ == "__main__":
    Console().run()