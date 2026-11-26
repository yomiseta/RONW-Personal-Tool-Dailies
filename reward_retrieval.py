"""Retrieve from Events: claims the daily Retrieve Rewards when the Event window shows they are waiting."""
import ingame
import steps

# ----- areas, as fractions of the game window: (left, top, right, bottom) -----
EVENT_TITLE_AREA = (0.055, 0.045, 0.160, 0.105)    # "Event" title of the window
BADGE_AREA = (0.964, 0.509, 0.989, 0.546)          # red "!" on the Retrieve icon
RETRIEVE_AREA = (0.412, 0.765, 0.511, 0.803)       # "Retrieve All" button of the Retrieve window
CONGRATS_AREA = (0.435, 0.377, 0.565, 0.422)       # "Congrats" banner

# ----- points, as fractions of the game window -----
RETRIEVE_POINT = (0.951, 0.564)    # the Retrieve icon at the right of the Event window
RETRIEVE_ALL = (0.483, 0.784)
CONGRATS_CLOSE = (0.493, 0.889)    # empty space, closes the Congrats window

BADGE_ICON = steps.ASSETS / "retrieve_badge.png"
BADGE_LOOKS = 3        # looks for the badge before the rewards count as already retrieved
LOOT_WAIT = 1.0        # seconds for a reward pop-up to appear after the Congrats window closes


def run(bot, hwnd, daily):
    steps.need_assets(BADGE_ICON.name)

    ingame.begin(bot, hwnd, "Retrieve: opening the Event window.")
    ingame.click_fraction(bot, hwnd, ingame.EVENT_ICON, "Event icon")
    steps.wait_text(bot, hwnd, EVENT_TITLE_AREA, "event", "Event window")

    found = None
    for look in range(1, BADGE_LOOKS + 1):
        found, score = steps.look(bot, hwnd, BADGE_AREA, BADGE_ICON, 0.85)
        if found:
            break
        if look < BADGE_LOOKS:
            bot.sleep(ingame.POLL)
    if not found:
        bot.log(f"Retrieve: nothing to retrieve (marker not found, best score {score:.2f}).")
        ingame.leave_windows(bot, hwnd)
        daily.retrieval = 1
        bot.log("Retrieve from Events done.", "OK")
        return

    bot.log(f"Retrieve: rewards are waiting (marker score {score:.2f}).")
    ingame.begin(bot, hwnd, "Retrieve: opening the Retrieve window.")
    ingame.click_fraction(bot, hwnd, RETRIEVE_POINT, "Retrieve")
    steps.wait_text(bot, hwnd, RETRIEVE_AREA, "retrieve", "Retrieve window")

    ingame.begin(bot, hwnd, "Retrieve: pressing Retrieve All.")
    ingame.click_fraction(bot, hwnd, RETRIEVE_ALL, "Retrieve All")
    steps.wait_text(bot, hwnd, CONGRATS_AREA, "congrats", "Congrats window")

    ingame.click_fraction(bot, hwnd, CONGRATS_CLOSE, "Close the Congrats window")
    bot.sleep(LOOT_WAIT)
    ingame.clear_loot(bot, hwnd)       # a reward pop-up may follow
    ingame.leave_windows(bot, hwnd)

    daily.retrieval = 1
    bot.log("Retrieve from Events done.", "OK")