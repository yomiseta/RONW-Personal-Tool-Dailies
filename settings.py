"""Small JSON-backed store for user preferences such as the skin and the launcher location."""
import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"
DEFAULTS = {"skin": "skins/default.png", "launcher_path": ""}


def load():
    """Returns the saved settings, falling back to defaults for anything missing or unreadable."""
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return data


def save(data):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")