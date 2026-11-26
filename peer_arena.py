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
RESULT_POLL = 0.25   # seconds between looks at the result screen after a sweep
EVENT_SCANS = 3    # scans of the open Event list for Peer Arena before it counts as not available
LIST_SETTLE = 1.0  # seconds for the Event list to fill after the window opens


def _scan_event_list(bot, hwnd):
    """Scans the open Event list for the word 'arena', EVENT_SCANS times, half a second apart.
    Returns its rectangle, or None when it was not found in any scan."""
    bot.sleep(LIST_SETTLE)
    for scan in range(1, EVENT_SCANS + 1):
        rect = ingame.find_word(ingame.read_words(bot, hwnd, EVENT_LIST_AREA), "arena")
        if rect:
            bot.sleep(0.3)   # look once more, so a moving screen cannot cause a misplaced click
            rect = ingame.find_word(ingame.read_words(bot, hwnd, EVENT_LIST_AREA), "arena")
            if rect:
                return rect
        bot.log(f"Peer Arena: not found in the Event list (scan {scan} of {EVENT_SCANS}).")
        if scan < EVENT_SCANS:
            ingame.clear_loot(bot, hwnd)
            bot.sleep(ingame.POLL)
    return None


def run(bot, hwnd, daily):
    ingame.require_assets()

    ingame.begin(bot, hwnd, "Peer Arena: opening the Event window.")
    ingame.click_fraction(bot, hwnd, ingame.EVENT_ICON, "Event icon")

    ingame.begin(bot, hwnd, "Peer Arena: looking for it in the Event list.")
    word = _scan_event_list(bot, hwnd)
    if word is None:
        # This account does not have Peer Arena yet. It is counted as done for today only, so it is
        # looked for again after the next daily reset, in case it has appeared by then.
        ingame.leave_windows(bot, hwnd)
        daily.peer_arena = 1
        bot.log("Peer Arena is not in the Event list of this account. Marked as done for today.", "WARN")
        return
    ingame.click_word(bot, hwnd, word, "Peer Arena")

    ingame.begin(bot, hwnd, "Peer Arena: checking the info window.")
    ingame.wait_word(bot, hwnd, POPUP_AREA, "arena", "Peer Arena info window")
    ingame.click_fraction(bot, hwnd, GO, "Go")

    attempts = None   # known after the first read, and then from each result screen
    for _ in range(MAX_ROUNDS):
        ingame.begin(bot, hwnd, "Peer Arena: checking the main window.")
        ingame.wait_word(bot, hwnd, MAIN_AREA, "arena", "Peer Arena main window")

        if attempts is None:
            attempts, total = ingame.wait_ratio(bot, hwnd, ATTEMPT_AREA, "Peer Arena attempts")
        bot.log(f"Peer Arena attempts left: {attempts}/{total}.")
        if attempts == 0:
            break

        # Nothing can pop up between the last look and this click, so it follows straight away.
        ingame.click_fraction(bot, hwnd, SWEEP, "Sweep")

        # The result screen shows the attempts left. One must have been used.
        left, _ = ingame.wait_ratio(bot, hwnd, REMAINING_AREA, "Peer Arena attempts remaining",
                                    accept=lambda first, second, before=attempts: first < before,
                                    poll=RESULT_POLL)
        bot.log(f"Attempts remaining: {left}/{total}.")
        if left == 0:
            ingame.begin(bot, hwnd, "Peer Arena: no attempts left, leaving.")
            ingame.click_fraction(bot, hwnd, EXIT, "Exit")
            break
        attempts = left
        ingame.click_fraction(bot, hwnd, CONTINUE, "Continue")

    ingame.leave_windows(bot, hwnd)
    daily.peer_arena = 1
    bot.log("Peer Arena done.", "OK")