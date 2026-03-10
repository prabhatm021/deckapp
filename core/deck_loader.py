import json
import re
from pathlib import Path

from deckapp.core.paths import resolve_icon_path


class Button:
    def __init__(self, row, col, data):
        self.row = row
        self.col = col

        self.label = data.get("label", "")
        self.behavior = data.get("behavior", "single")

        icon = data.get("icon")
        self.icon = resolve_icon_path(icon) if icon else None

        if self.behavior == "single":
            self.command = data.get("command", "")
        else:
            self.state = data.get("state", "off")
            self.on_command = data.get("on", {}).get("command", "")
            self.off_command = data.get("off", {}).get("command", "")


class Deck:
    def __init__(self, deck_id, deck_name, rows, cols):
        self.deck_id = deck_id
        self.deck_name = deck_name
        self.rows = rows
        self.cols = cols
        self.buttons = {}
        self.path = None


def load_deck(path):
    path = Path(path)

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise ValueError(f"Could not load deck '{path.name}': {e}") from e

    grid = data.get("grid", {})
    deck = Deck(
        deck_id=data.get("deck_id", path.stem),
        deck_name=data.get("deck_name", path.stem),
        rows=grid.get("rows", 4),
        cols=grid.get("cols", 4),
    )

    for key, btn_data in data.get("buttons", {}).items():
        try:
            row, col = map(int, key.split(","))
        except ValueError:
            continue
        deck.buttons[(row, col)] = Button(row, col, btn_data)

    deck.path = path
    return deck


def create_empty_deck(path, name, rows, cols):
    deck_id = re.sub(r'\s+', '-', name.lower().strip())
    data = {
        "deck_id": deck_id,
        "deck_name": name,
        "grid": {"rows": rows, "cols": cols},
        "buttons": {},
    }
    path = Path(path)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
