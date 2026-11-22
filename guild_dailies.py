"""Guild Dailies: accepts the daily guild quests and waits for the character to finish them."""
import config
import ingame
from pathlib import Path

EVENT_LIST_AREA = (0.048, 0.281, 0.652, 0.765)   # the list of daily events
POPUP_AREA = (0.388, 0.206, 0.588, 0.315)        # title of the Guild Dailies info window
ATTEMPT_AREA = (0.19, 0.30, 0.45, 0.38)          # "Attempts:0/1" in the info window
TALK_KEY_AREA = (0.501, 0.517, 0.592, 0.591)     # where the "F" key hint appears next to Talk
TALK_KEY_ICON = Path(__file__).parent / "assets" / "talk_key.png"
ACCEPT_AREA = (0.689, 0.632, 0.899, 0.702)       # the Accept button
SHOP_AREA = (0.060, 0.051, 0.131, 0.100)         # title of the Shop window

GO = (0.499, 0.745)
TALK = (0.607, 0.556)
ACCEPT = (0.774, 0.674)
TELEPORT_WAIT = 10        # seconds for the character to arrive after pressing Go
LOOT_CHECK_EVERY = 10     # seconds between item pop-up checks while waiting


def _open_and_read(bot, hwnd):
    """Opens the Guild Dailies info window and returns its attempts as (done, total)."""
    ingame.begin(bot, hwnd, "Guild Dailies: opening the Event window.")
    ingame.click_fraction(bot, hwnd, ingame.EVENT_ICON, "Event icon")

    ingame.begin(bot, hwnd, "Guild Dailies: looking for it in the Event list.")
    word = ingame.wait_word(bot, hwnd, EVENT_LIST_AREA, "guild", "Event list", confirm=0.3)
    ingame.click_word(bot, hwnd, word, "Guild Dailies")

    ingame.begin(bot, hwnd, "Guild Dailies: checking the info window.")
    ingame.wait_word(bot, hwnd, POPUP_AREA, "guild", "Guild Dailies info window")
    done, total = ingame.wait_ratio(bot, hwnd, ATTEMPT_AREA, "Guild Dailies attempts")
    bot.log(f"Guild Dailies attempts: {done}/{total}.")
    return done, total


def _finish(bot, hwnd, daily):
    ingame.leave_windows(bot, hwnd)
    daily.guild = 1
    bot.log("Guild Dailies done.", "OK")


def _wait_for_quests(bot, hwnd):
    """Waits while the character plays the quests by itself, closing item pop-ups on the way."""
    total = config.GUILD_WAIT_SECONDS
    bot.log(f"Guild Dailies: waiting {total} seconds for the quests to finish.")
    waited = last_report = 0
    while waited < total:
        step = min(LOOT_CHECK_EVERY, total - waited)
        bot.sleep(step)
        waited += step
        if waited < total:
            ingame.clear_loot(bot, hwnd)
            if waited - last_report >= 60:
                last_report = waited
                bot.log(f"Guild Dailies: {total - waited} seconds left.")


def run(bot, hwnd, daily):
    ingame.require_assets(TALK_KEY_ICON)

    done, total = _open_and_read(bot, hwnd)
    if done >= total:
        _finish(bot, hwnd, daily)
        return

    ingame.begin(bot, hwnd, "Guild Dailies: pressing Go.")
    ingame.click_fraction(bot, hwnd, GO, "Go")
    bot.sleep(TELEPORT_WAIT)

    ingame.begin(bot, hwnd, "Guild Dailies: looking for the Talk prompt.")
    ingame.wait_image(bot, hwnd, TALK_KEY_AREA, TALK_KEY_ICON, "Talk key hint")
    ingame.click_fraction(bot, hwnd, TALK, "Talk")

    ingame.begin(bot, hwnd, "Guild Dailies: looking for the Accept button.")
    ingame.wait_word(bot, hwnd, ACCEPT_AREA, "accept", "Accept button")
    ingame.click_fraction(bot, hwnd, ACCEPT, "Accept")

    _wait_for_quests(bot, hwnd)

    # The Shop window is sometimes left open after the quests.
    ingame.begin(bot, hwnd, "Guild Dailies: checking for a left-open Shop window.")
    if ingame.find_word(ingame.read_words(bot, hwnd, SHOP_AREA), "shop"):
        bot.log("The Shop window is open. Closing it.")
        ingame.press_esc(bot, hwnd)
        bot.sleep(0.6)
    ingame.ensure_world(bot, hwnd)

    done, total = _open_and_read(bot, hwnd)
    if done >= total:
        _finish(bot, hwnd, daily)
        return
    raise ingame.Halt("Stopped: the Guild Dailies still show "
                      f"{done}/{total} after waiting. The quests may need more time (see GUILD_WAIT_SECONDS in main.py).")