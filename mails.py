"""Check and Read Mails: claims the System and Guild mails and frees mail space when it runs low."""
import ingame
import steps

# ----- areas, as fractions of the game window: (left, top, right, bottom) -----
MAIL_TITLE_AREA = (0.175, 0.163, 0.234, 0.207)     # "Mail"
FRIENDS_AREA = (0.172, 0.110, 0.234, 0.142)        # "Friends" of the Friends window
CHAT_BACK_AREA = (0.052, 0.049, 0.102, 0.084)      # "Back" of the Chat window
SYSTEM_BADGE_AREA = (0.204, 0.252, 0.231, 0.285)   # red "!" on the System tab
GUILD_BADGE_AREA = (0.299, 0.261, 0.327, 0.288)    # red "!" on the Guild tab
COUNTER_AREA = (0.205, 0.721, 0.274, 0.749)        # "158/200"

# ----- points, as fractions of the game window -----
CHAT_MAIL_ICON = (0.019, 0.876)    # Chat and Mail icon, first of the icons at the bottom left
GUILD_TAB = (0.287, 0.284)
CLAIM_ALL = (0.295, 0.777)
DELETE_READ = (0.183, 0.775)
MAIL_CLOSE = (0.907, 0.185)
HIDE_FRIENDS = (0.462, 0.515)
HIDE_CHAT = (0.461, 0.516)

MAIL_BADGE = steps.ASSETS / "mail_badge.png"
MIN_SPACE = 10         # mails are deleted when this many places or fewer are free
CLAIM_WAIT = 1.0       # seconds after Claim All for the reward pop-up
DELETE_WAIT = 1.0      # seconds after Delete Read
FRIENDS_LOOKS = 3      # looks for the Friends window after the Mail window is closed


def _which_window(bot, hwnd):
    """The window the Chat and Mail icon opened: "mail", "friends" or "chat". The Mail window is
    checked first, because the Friends window can be seen dimmed behind it."""
    checks = (("mail", MAIL_TITLE_AREA, "mail"), ("friends", FRIENDS_AREA, "friends"),
              ("chat", CHAT_BACK_AREA, "back"))
    for attempt in range(1, ingame.TRIES + 1):
        for name, area, target in checks:
            if steps.has_text(bot, hwnd, area, target):
                return name
        if attempt < ingame.TRIES:
            ingame.clear_loot(bot, hwnd)
            bot.sleep(ingame.POLL)
    raise ingame.Halt("Stopped: no Mail, Friends or Chat window was detected after the Chat and Mail icon was clicked.")


def _check_space(bot, hwnd, name):
    """Reads the mail counter and presses Delete Read when MIN_SPACE places or fewer are free."""
    counter = steps.try_ratio(bot, hwnd, COUNTER_AREA)
    if counter is None:
        bot.log(f"Mail ({name}): the mail counter could not be read.", "WARN")
        return
    count, total = counter
    bot.log(f"Mail ({name}): {count}/{total} mails.")
    if total - count > MIN_SPACE:
        return
    bot.log(f"Mail ({name}): the mailbox is almost full. Deleting the read mails.", "WARN")
    ingame.click_fraction(bot, hwnd, DELETE_READ, "Delete Read")
    bot.sleep(DELETE_WAIT)
    ingame.clear_loot(bot, hwnd)
    counter = steps.try_ratio(bot, hwnd, COUNTER_AREA)
    if counter is None:
        bot.log(f"Mail ({name}): the counter could not be read after deleting.", "WARN")
    elif counter[1] - counter[0] > MIN_SPACE:
        bot.log(f"Mail ({name}): now {counter[0]}/{counter[1]} mails.")
    else:
        bot.log(f"Mail ({name}): still {counter[0]}/{counter[1]} mails after deleting.", "WARN")


def _claim(bot, hwnd, name, badge_area, tab_point):
    """Claims the mails of one tab when its red marker shows."""
    ingame.begin(bot, hwnd, f"Mail: checking the {name} mails.")
    found, score = steps.look(bot, hwnd, badge_area, MAIL_BADGE)
    if found:
        bot.log(f"Mail ({name}): unread mails (marker score {score:.2f}). Claiming.")
        if tab_point:
            ingame.click_fraction(bot, hwnd, tab_point, f"{name} tab")
            bot.sleep(0.5)
        ingame.click_fraction(bot, hwnd, CLAIM_ALL, "Claim All")
        bot.sleep(CLAIM_WAIT)
        ingame.clear_loot(bot, hwnd)    # a reward pop-up may appear
    else:
        bot.log(f"Mail ({name}): no unread mails (best score {score:.2f}).")
    _check_space(bot, hwnd, name)


def _close_mail(bot, hwnd):
    """Closes the Mail window. The Friends window behind it may show next."""
    ingame.begin(bot, hwnd, "Mail: closing the window.")
    ingame.click_fraction(bot, hwnd, MAIL_CLOSE, "Close the mail window")
    bot.sleep(0.8)
    for look in range(1, FRIENDS_LOOKS + 1):
        if steps.has_text(bot, hwnd, FRIENDS_AREA, "friends"):
            ingame.click_fraction(bot, hwnd, HIDE_FRIENDS, "Hide the Friends window")
            bot.sleep(1.0)
            break
        if look < FRIENDS_LOOKS:
            bot.sleep(ingame.POLL)
    ingame.ensure_world(bot, hwnd)    # presses Esc only while the game world is not showing


def run(bot, hwnd, daily):
    steps.need_assets(MAIL_BADGE.name)

    ingame.begin(bot, hwnd, "Mail: clicking the Chat and Mail icon.")
    ingame.click_fraction(bot, hwnd, CHAT_MAIL_ICON, "Chat and Mail icon")
    window = _which_window(bot, hwnd)
    bot.log(f"Mail: the {window} window opened.")

    if window == "mail":
        _claim(bot, hwnd, "System", SYSTEM_BADGE_AREA, None)
        _claim(bot, hwnd, "Guild", GUILD_BADGE_AREA, GUILD_TAB)
        _close_mail(bot, hwnd)
    elif window == "friends":
        # No new mails: the Friends window opens instead.
        ingame.click_fraction(bot, hwnd, HIDE_FRIENDS, "Hide the Friends window")
        bot.sleep(1.0)
        ingame.ensure_world(bot, hwnd)
    else:
        # The Chat window opens when the mails were already read.
        ingame.click_fraction(bot, hwnd, HIDE_CHAT, "Hide the Chat window")
        bot.sleep(1.0)
        ingame.ensure_world(bot, hwnd)

    daily.mail = 1
    bot.log("Check and read mails done.", "OK")