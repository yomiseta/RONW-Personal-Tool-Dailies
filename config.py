"""Settings shared by the whole program.

config.ini (next to main.py) holds the values the user may change, either by editing the file or in
the CONFIG window. It is read every time a value is asked for, so a change takes effect at the next
START without restarting the program. To add a setting, add it to SETTINGS and ask for it with get().
DAILY_RESET_HOUR is not in config.ini yet: main.py sets it.
"""
import configparser
import os
import re
from dataclasses import dataclass
from pathlib import Path

FILE = Path(__file__).parent / "config.ini"
DAILY_RESET_HOUR = 0   # replaced from main.py


@dataclass(frozen=True)
class Setting:
    name: str        # the key in config.ini
    label: str       # the title shown in the CONFIG window
    help: str        # one line of explanation, also written into config.ini
    default: int
    minimum: int
    maximum: int


SETTINGS = (
    Setting("GUILD_DAILIES_WAIT_SECONDS", "Guild Dailies wait (seconds)",
            "Seconds to wait for the character to finish the Guild Dailies quests after accepting them.",
            200, 0, 1200),
)
BY_NAME = {s.name: s for s in SETTINGS}


def _template():
    lines = ["; Settings for the bot. Change a value, save the file and press START.",
             "; The file is read at every start. Lines beginning with ; or # are notes.", ""]
    for s in SETTINGS:
        lines += [f"; {s.help}", f"{s.name} = {s.default}", ""]
    return "\n".join(lines)


def _read_raw():
    """The text values of config.ini as a dict with lower-case keys. The file is created when it is missing."""
    if not FILE.exists():
        try:
            FILE.write_text(_template(), encoding="utf-8")
        except OSError:
            pass
    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"), interpolation=None)
    try:
        parser.read_string("[settings]\n" + FILE.read_text(encoding="utf-8-sig"))
    except (OSError, configparser.Error):
        return {}
    return dict(parser["settings"])


def parse(setting, text):
    """The whole number in `text`, or None when it is not a number within the allowed range."""
    try:
        value = int(str(text).strip())
    except ValueError:
        return None
    return value if setting.minimum <= value <= setting.maximum else None


def get(name):
    """The current value of a setting. A missing or invalid value gives the default."""
    setting = BY_NAME[name]
    value = parse(setting, _read_raw().get(name.lower()))
    return setting.default if value is None else value


def all_values():
    return {s.name: get(s.name) for s in SETTINGS}


def evaluate(texts, saved):
    """Compares what is typed in the CONFIG window with what is saved.
    `texts` maps names to typed text, `saved` maps names to saved numbers.
    Returns (changed, valid, problems): `changed` is True when something differs from the saved
    value (typing the saved value again is not a change), `valid` is False when a field cannot be
    saved, and `problems` maps names to a message."""
    changed, problems = False, {}
    for s in SETTINGS:
        value = parse(s, texts[s.name])
        if value is None:
            changed = True
            problems[s.name] = f"Enter a whole number from {s.minimum} to {s.maximum}."
        elif value != saved[s.name]:
            changed = True
    return changed, not problems, problems


def save(values):
    """Writes the values to config.ini. Other lines of the file, such as the user's notes, stay as they are."""
    _read_raw()   # makes sure the file exists
    text = FILE.read_text(encoding="utf-8-sig")
    for name, value in values.items():
        line = f"{name} = {value}"
        pattern = re.compile(rf"^[ \t]*{re.escape(name)}[ \t]*=.*$", re.IGNORECASE | re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(lambda m: line, text, count=1)
        else:
            text = text.rstrip("\n") + f"\n\n; {BY_NAME[name].help}\n{line}\n"
    temp = FILE.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, FILE)   # replaced in one step, so a crash cannot leave half a file


def guild_dailies_wait_seconds():
    return get("GUILD_DAILIES_WAIT_SECONDS")