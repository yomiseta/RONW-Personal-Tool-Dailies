"""The in-game daily activities, each one a goal for the goal loop."""
from dataclasses import dataclass

import actions
import guild_dailies
import peer_arena
from errors import StepFailed
from goals import Goal, game_window


@dataclass
class DailyState:
    """What has been finished for the current account. 1 means done."""
    peer_arena: int = 0
    guild: int = 0


class _InGameGoal(Goal):
    timeout = 900

    def __init__(self, daily):
        self.daily = daily

    def _window(self):
        hwnd = game_window()
        if hwnd is None:
            raise StepFailed("The game window was not found.")
        return hwnd


class PeerArenaGoal(_InGameGoal):
    title = actions.PEER_ARENA

    def is_done(self, bot):
        return self.daily.peer_arena == 1

    def step(self, bot):
        peer_arena.run(bot, self._window(), self.daily)


class GuildGoal(_InGameGoal):
    title = actions.GUILD
    timeout = 1500   # includes the long wait while the character plays the quests

    def is_done(self, bot):
        return self.daily.guild == 1

    def step(self, bot):
        guild_dailies.run(bot, self._window(), self.daily)