import json
from pathlib import Path

from deckapp.core.paths import get_data_dir


def save_deck(deck, path):
    data = {
        "deck_id": deck.deck_id,
        "deck_name": deck.deck_name,
        "grid": {
            "rows": deck.rows,
            "cols": deck.cols,
        },
        "buttons": {},
    }

    assets_prefix = str(get_data_dir() / "assets") + "/"

    for (row, col), button in deck.buttons.items():
        key = f"{row},{col}"

        btn_data = {
            "label": button.label,
            "behavior": button.behavior,
        }

        if getattr(button, "icon", None):
            # Store path relative to the data/assets dir
            btn_data["icon"] = button.icon.replace(assets_prefix, "")

        if button.behavior == "single":
            btn_data["command"] = button.command
        else:
            btn_data["state"] = button.state
            btn_data["on"] = {"command": button.on_command}
            btn_data["off"] = {"command": button.off_command}

        data["buttons"][key] = btn_data

    path = Path(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
