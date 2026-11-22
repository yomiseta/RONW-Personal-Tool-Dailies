"""Peer Arena: sweeps every remaining daily attempt."""
import ingame

EVENT_LIST_AREA = (0.048, 0.281, 0.652, 0.765)   # the list of daily events
POPUP_AREA = (0.388, 0.206, 0.588, 0.315)        # title of the Peer Arena info window
MAIN_AREA = (0.017, 0.033, 0.224, 0.134)         # title of the Peer Arena main window
ATTEMPT_AREA = (0.682, 0.112, 0.992, 0.223)      # "Challenges Left Today: 5/5"
REMAINING_AREA = (0.64, 0.62, 0.90, 0.70)        # "Attempts remaining: 4/5" on the result screen

GO = (0.499, 0.745)
SWEEP = (0.695, 0.737)
CONTINUE = (0.753, 0.726)
EXIT = (0.494, 0.724)
MAX_ROUNDS = 10


def run(bot, hwnd, daily):
    ingame.require_assets()

    ingame.begin(bot, hwnd, "Peer Arena: opening the Event window.")
    ingame.click_fraction(bot, hwnd, ingame.EVENT_ICON, "Event icon")

    ingame.begin(bot, hwnd, "Peer Arena: looking for it in the Event list.")
    word = ingame.wait_word(bot, hwnd, EVENT_LIST_AREA, "arena", "Event list", confirm=0.3)
    ingame.click_word(bot, hwnd, word, "Peer Arena")

    ingame.begin(bot, hwnd, "Peer Arena: checking the info window.")
    ingame.wait_word(bot, hwnd, POPUP_AREA, "arena", "Peer Arena info window")
    ingame.click_fraction(bot, hwnd, GO, "Go")

    for _ in range(MAX_ROUNDS):
        ingame.begin(bot, hwnd, "Peer Arena: checking the main window.")
        ingame.wait_word(bot, hwnd, MAIN_AREA, "arena", "Peer Arena main window")

        attempts, total = ingame.wait_ratio(bot, hwnd, ATTEMPT_AREA, "Peer Arena attempts")
        bot.log(f"Peer Arena attempts left: {attempts}/{total}.")
        if attempts == 0:
            break

        ingame.begin(bot, hwnd, "Peer Arena: sweeping.")
        ingame.click_fraction(bot, hwnd, SWEEP, "Sweep")

        # The result screen shows the attempts left. One must have been used.
        ingame.begin(bot, hwnd, "Peer Arena: checking the result screen.")
        left, _ = ingame.wait_ratio(bot, hwnd, REMAINING_AREA, "Peer Arena attempts remaining",
                                    accept=lambda first, second, before=attempts: first < before)
        bot.log(f"Attempts remaining: {left}/{total}.")
        if left == 0:
            ingame.begin(bot, hwnd, "Peer Arena: no attempts left, leaving.")
            ingame.click_fraction(bot, hwnd, EXIT, "Exit")
            break
        ingame.click_fraction(bot, hwnd, CONTINUE, "Continue")

    ingame.leave_windows(bot, hwnd)
    daily.peer_arena = 1
    bot.log("Peer Arena done.", "OK")