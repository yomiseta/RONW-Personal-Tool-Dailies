"""Check Inventory: makes sure the bag has room before anything else is done. When less than
MIN_FREE capacity is left, the Blue and Purple gear is recycled."""
import ingame
import scene
import steps

# ----- areas, as fractions of the game window: (left, top, right, bottom) -----
TITLE_AREA = (0.062, 0.057, 0.156, 0.094)        # "Inventory" title of the window
CAPACITY_AREA = (0.607, 0.810, 0.701, 0.847)     # "7762/13360"
MENU_AREA = (0.447, 0.544, 0.524, 0.766)         # the menu that opens from the clean-up button
LIST_TITLE_AREA = (0.113, 0.241, 0.242, 0.293)   # "Recycle List" title
PURPLE_AREA = (0.288, 0.710, 0.340, 0.735)       # "Purple Gear", which moves here once Blue is ticked

# ----- points, as fractions of the game window -----
BAG_POINT = (0.953, 0.964)       # inventory icon
CLEAN_POINT = (0.525, 0.828)     # opens the inventory menu
RECYCLE_POINT = (0.487, 0.625)   # Recycle in that menu
BLUE_BOX = (0.132, 0.749)        # "<= Blue" checkbox
PURPLE_BOX = (0.279, 0.722)      # "Purple Gear" checkbox
SKILL_POINT = (0.287, 0.762)     # purple special-skill filter
CONFIRM_POINT = (0.393, 0.818)   # Confirm Recycling
BACK_POINT = (0.042, 0.074)      # back arrow that closes the inventory

MIN_FREE = 1000        # the bag is cleaned when less capacity than this is left
RECYCLE_WAIT = 3.0     # seconds after Confirm Recycling
CLOSE_WAIT = 5.0       # seconds for the game world to return after closing the inventory


def _close(bot, hwnd):
    ingame.begin(bot, hwnd, "Inventory: closing the window.")
    ingame.click_fraction(bot, hwnd, BACK_POINT, "Close the inventory")
    bot.sleep(CLOSE_WAIT)
    ingame.ensure_world(bot, hwnd)


def _recycle(bot, hwnd):
    ingame.begin(bot, hwnd, "Inventory: opening the inventory menu.")
    ingame.click_fraction(bot, hwnd, CLEAN_POINT, "Inventory menu")
    steps.wait_text(bot, hwnd, MENU_AREA, "recycle", "Inventory menu")
    ingame.click_fraction(bot, hwnd, RECYCLE_POINT, "Recycle")

    ingame.begin(bot, hwnd, "Inventory: checking the recycle list.")
    steps.wait_text(bot, hwnd, LIST_TITLE_AREA, "recycle", "Recycle List window")
    ingame.click_fraction(bot, hwnd, BLUE_BOX, "Blue checkbox")

    # Once Blue is ticked the layout moves, and "Purple" shows in its new place.
    ingame.begin(bot, hwnd, "Inventory: checking that Blue is ticked.")
    steps.wait_text(bot, hwnd, PURPLE_AREA, "purple", "Purple Gear option")
    ingame.click_fraction(bot, hwnd, PURPLE_BOX, "Purple checkbox")
    ingame.click_fraction(bot, hwnd, SKILL_POINT, "Special skill filter")
    ingame.click_fraction(bot, hwnd, CONFIRM_POINT, "Confirm Recycling")
    bot.sleep(RECYCLE_WAIT)
    ingame.clear_loot(bot, hwnd)
    bot.log("Inventory: recycled.")


def run(bot, hwnd, daily):
    steps.need_assets(scene.BAG_ICON.name)

    ingame.begin(bot, hwnd, "Inventory: looking for the inventory icon.")
    steps.wait_icon(bot, hwnd, scene.BAG_AREA, scene.BAG_ICON, "inventory icon",
                    scene.BAG_THRESHOLD, scene.BAG_REF_WIDTH)
    ingame.click_fraction(bot, hwnd, BAG_POINT, "Inventory icon")

    ingame.begin(bot, hwnd, "Inventory: checking the window.")
    steps.wait_text(bot, hwnd, TITLE_AREA, "inventory", "Inventory window")
    used, total = ingame.wait_ratio(bot, hwnd, CAPACITY_AREA, "Inventory capacity")
    free = total - used
    bot.log(f"Inventory capacity: {used}/{total}, {free} left.")

    if free < MIN_FREE:
        bot.log(f"Less than {MIN_FREE} capacity left. Cleaning the inventory.", "WARN")
        _recycle(bot, hwnd)
    else:
        bot.log("The inventory has enough room.")
    _close(bot, hwnd)

    daily.inventory = 1
    bot.log("Inventory check done.", "OK")