"""Reading and writing Accounts.ini, and the saved choice of which accounts are automated.

File layout, one numbered section per account, the first section being the first in line:

    [1]
    Account=NAME
    Password=SECRET

The file keeps the encoding it already has (UTF-16 with a BOM or UTF-8). Passwords are only
ever held in memory and written back to this file, never logged or shown.
"""
import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

from errors import StepFailed

ACCOUNTS_FILE = Path(__file__).parent / "Accounts.ini"
DISABLED_KEY = "disabled_accounts"   # settings.json: names of the accounts that are unchecked


class AccountsError(StepFailed):
    """Accounts.ini is missing, unreadable or incomplete."""


@dataclass
class Account:
    name: str
    password: str
    extra: dict = field(default_factory=dict)   # any other keys of the section, kept as they were


def _decode(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    return raw.decode("utf-8"), "utf-8"


def _current_encoding():
    try:
        return _decode(ACCOUNTS_FILE.read_bytes())[1]
    except (OSError, UnicodeDecodeError):
        return "utf-8"


def load_all():
    """All accounts in file order. An empty list when the file does not exist yet."""
    if not ACCOUNTS_FILE.exists():
        return []
    try:
        text, _ = _decode(ACCOUNTS_FILE.read_bytes())
    except (OSError, UnicodeDecodeError):
        raise AccountsError("Accounts.ini could not be read. Save it as UTF-8 or UTF-16.")
    cfg = configparser.ConfigParser(interpolation=None)   # passwords may contain '%'
    cfg.optionxform = str                                  # keep the key spelling
    try:
        cfg.read_string(text)
    except configparser.Error:
        raise AccountsError("Accounts.ini has a layout problem. Each account needs its own [number] section.")
    result = []
    for section in cfg.sections():
        values = dict(cfg[section])
        name = values.pop("Account", "").strip()
        password = values.pop("Password", "")
        if name and password:
            result.append(Account(name, password, values))
    return result


def save_all(accounts):
    """Writes the accounts back in the given order, numbering the sections 1, 2, 3...
    The file is replaced in one step, so a crash cannot leave it half written."""
    lines = []
    for number, acc in enumerate(accounts, 1):
        lines.append(f"[{number}]")
        lines.append(f"Account={acc.name}")
        lines.append(f"Password={acc.password}")
        lines.extend(f"{key}={value}" for key, value in acc.extra.items())
        lines.append("")
    data = "\r\n".join(lines).encode(_current_encoding() if ACCOUNTS_FILE.exists() else "utf-8")
    temp = ACCOUNTS_FILE.with_suffix(".tmp")
    temp.write_bytes(data)
    os.replace(temp, ACCOUNTS_FILE)


def disabled_names(settings):
    return set(settings.get(DISABLED_KEY, []))


def set_enabled(settings, name, enabled):
    """Checks or unchecks an account. The choice is stored by name in settings.json."""
    names = [n for n in settings.get(DISABLED_KEY, []) if n != name]
    if not enabled:
        names.append(name)
    settings[DISABLED_KEY] = names


def rename_in_settings(settings, old, new):
    """Keeps the checked state when an account is renamed."""
    if old in settings.get(DISABLED_KEY, []):
        set_enabled(settings, old, True)
        set_enabled(settings, new, False)


def enabled(settings):
    """The checked accounts, in file order. These are the ones the bot works through."""
    skipped = disabled_names(settings)
    return [acc for acc in load_all() if acc.name not in skipped]