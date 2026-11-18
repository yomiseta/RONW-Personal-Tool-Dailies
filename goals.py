"""Goals the bot works towards.

A goal is an objective, not a status. While it is the current goal the worker keeps looking
at the screen and acting (step) until the result can be verified (is_done). Only then does the
ACTION bar move on to the next goal.
"""
import os

import actions
import character
import launcher
import login
import winutil


def game_window():
    """The game window, or None. The launcher shares the game's name, so it is excluded explicitly."""
    pid = os.getpid()
    hwnd = winutil.find_game_window(pid)
    if hwnd is None or hwnd == winutil.find_launcher_window(pid):
        return None
    return hwnd


class Goal:
    title = ""

    def is_done(self, bot):
        raise NotImplementedError

    def step(self, bot):
        raise NotImplementedError


class LoginGoal(Goal):
    """Account signed in, character in the game world, pop-ups closed, Game Menu closed."""

    def __init__(self, account, password):
        self.account, self.password = account, password
        self.title = actions.logging_in(account)
        self.state = character.CharacterState()

    def is_done(self, bot):
        return self.state.ready and game_window() is not None

    def step(self, bot):
        hwnd = game_window()
        if hwnd is None:
            # No game yet (or it closed): go through the launcher.
            self.state = character.CharacterState()
            if not winutil.find_launcher_window(os.getpid()):
                launcher.open_and_arrange(bot, bot.launcher_path)
            bot.log("Game is not open. Starting the launcher login...")
            login.run(bot, self.account, self.password)
            return
        if not self.state.ready:
            character.advance(bot, hwnd, self.state)