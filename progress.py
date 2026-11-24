"""Remembers which daily activities each account has finished today.

Stored in daily_progress.json, separate from Accounts.ini. The file starts empty again
when the day changes, so every account begins the new day with everything pending.
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import config

FILE = Path(__file__).parent / "daily_progress.json"

# The in-game activities that count towards "finished for today".
# When a new activity is added, add its name here and as a field of DailyState (daily_goals.py).
GOALS = ("peer_arena", "guild", "quest_board")


def today():
    """Date of the current game day. The day starts at config.DAILY_RESET_HOUR."""
    return (datetime.now() - timedelta(hours=config.DAILY_RESET_HOUR)).strftime("%Y-%m-%d")


def _load():
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or data.get("date") != today():
        data = {"date": today(), "accounts": {}}
    data.setdefault("accounts", {})
    return data


def _save(data):
    temp = FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, FILE)   # replaced in one step, so a crash cannot leave half a file


def get(account):
    """Dict like {"peer_arena": 1, "guild": 0} with what the account has finished today."""
    saved = _load()["accounts"].get(account, {})
    return {goal: int(saved.get(goal, 0)) for goal in GOALS}


def mark(account, goal):
    """Records an activity as finished for this account."""
    data = _load()
    data["accounts"].setdefault(account, {})[goal] = 1
    _save(data)


def is_complete(account):
    """True when every activity is finished for this account today."""
    return all(value == 1 for value in get(account).values())