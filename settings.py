import json
from pathlib import Path

SETTINGS_FILE = Path(__file__).parent / "settings.json"
DEFAULTS = {"skin": "skins/default.png"}


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return data


def save(data):
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")