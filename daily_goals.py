"""The in-game daily activities, each one a goal for the goal loop."""
from dataclasses import dataclass

import actions
import guild_dailies
import peer_arena
import progress
from errors import StepFailed
from goals import Goal, game_window


@dataclass
class DailyState:
    """What has been finished for one account today. 1 means done."""
    account: str
    peer_arena: int = 0
    guild: int = 0

    @classmethod
    def load(cls, account):
        """The state of an account, with what was already recorded earlier today."""
        return cls(account, **progress.get(account))


class _InGameGoal(Goal):
    timeout = 900
    key = ""   # name used in progress.py

    def __init__(self, daily):
        self.daily = daily

    def _window(self):
        hwnd = game_window()
        if hwnd is None:
            raise StepFailed("The game window was not found.")
        return hwnd

    def _record(self):
        """Saves the activity as finished, so later runs skip it."""
        if getattr(self.daily, self.key) == 1:
            progress.mark(self.daily.account, self.key)


class PeerArenaGoal(_InGameGoal):
    title = actions.PEER_ARENA
    key = "peer_arena"

    def is_done(self, bot):
        return self.daily.peer_arena == 1

    def step(self, bot):
        peer_arena.run(bot, self._window(), self.daily)
        self._record()


class GuildGoal(_InGameGoal):
    title = actions.GUILD
    key = "guild"
    timeout = 1500   # includes the long wait while the character plays the quests

    def is_done(self, bot):
        return self.daily.guild == 1

    def step(self, bot):
        guild_dailies.run(bot, self._window(), self.daily)
        self._record()