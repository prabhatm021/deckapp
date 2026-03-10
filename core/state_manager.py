import json
from pathlib import Path


class StateManager:
    def __init__(self, app_name="deckapp"):
        self.base_dir = Path.home() / ".config" / app_name
        self.state_file = self.base_dir / "state.json"

        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._state = {}

        self.load()

    def load(self):
        if self.state_file.exists():
            try:
                with self.state_file.open("r", encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception:
                self._state = {}
        else:
            self._state = {}

    def save(self):
        tmp = self.state_file.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(self._state, f, indent=2)
        tmp.replace(self.state_file)

    def get(self, deck_id, position, default="off"):
        pos_key = f"{position[0]},{position[1]}"
        return self._state.get(deck_id, {}).get(pos_key, default)

    def set(self, deck_id, position, value):
        pos_key = f"{position[0]},{position[1]}"

        if deck_id not in self._state:
            self._state[deck_id] = {}

        self._state[deck_id][pos_key] = value
        self.save()

