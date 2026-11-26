"""The in-game daily activities, each one a goal for the goal loop."""
from dataclasses import dataclass

import actions
import guild_dailies
import inventory_check
import mails
import peer_arena
import progress
import quest_board
import reward_retrieval
from errors import StepFailed
from goals import Goal, game_window


@dataclass
class DailyState:
    """What has been finished for one account today. 1 means done."""
    account: str
    inventory: int = 0
    retrieval: int = 0
    mail: int = 0
    peer_arena: int = 0
    guild: int = 0
    quest_board: int = 0

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


class InventoryGoal(_InGameGoal):
    title = actions.INVENTORY
    key = "inventory"

    def is_done(self, bot):
        return self.daily.inventory == 1

    def step(self, bot):
        inventory_check.run(bot, self._window(), self.daily)
        self._record()


class RetrievalGoal(_InGameGoal):
    title = actions.EVENTS
    key = "retrieval"

    def is_done(self, bot):
        return self.daily.retrieval == 1

    def step(self, bot):
        reward_retrieval.run(bot, self._window(), self.daily)
        self._record()


class MailGoal(_InGameGoal):
    title = actions.MAILS
    key = "mail"

    def is_done(self, bot):
        return self.daily.mail == 1

    def step(self, bot):
        mails.run(bot, self._window(), self.daily)
        self._record()


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


class QuestBoardGoal(_InGameGoal):
    title = actions.QUEST_BOARD
    key = "quest_board"
    timeout = 3000   # the five commissions can take a long time to play

    def is_done(self, bot):
        return self.daily.quest_board == 1

    def step(self, bot):
        quest_board.run(bot, self._window(), self.daily)
        self._record()


# The order the goals are worked through for each account: (name in DailyState, goal, name for the log).
ORDER = (
    ("inventory", InventoryGoal, "Inventory check"),
    ("retrieval", RetrievalGoal, "Retrieve from Events"),
    ("mail", MailGoal, "Check and read mails"),
    ("peer_arena", PeerArenaGoal, "Peer Arena"),
    ("guild", GuildGoal, "Guild Dailies"),
    ("quest_board", QuestBoardGoal, "Quest Board"),
)