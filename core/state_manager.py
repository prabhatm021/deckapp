"""Persisted toggle state, keyed by deck id and button position.

The deck file stores the *default* state of a toggle; this store remembers
what the user actually left it on. One shared instance per process.
"""
import json
import logging
from pathlib import Path

from deckapp.core.paths import atomic_write_text, get_config_dir

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self, state_file=None):
        self.state_file = Path(state_file) if state_file else (
            get_config_dir() / "state.json"
        )
        self._state = {}
        self.load()

    # ── Persistence ──

    def load(self):
        self._state = {}
        try:
            raw = self.state_file.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as e:
            logger.warning("Could not read %s: %s", self.state_file, e)
            return

        try:
            data = json.loads(raw)
        except ValueError as e:
            logger.warning("Ignoring corrupt state file %s: %s", self.state_file, e)
            return

        if isinstance(data, dict):
            self._state = {
                str(k): dict(v) for k, v in data.items() if isinstance(v, dict)
            }

    def save(self):
        try:
            atomic_write_text(self.state_file, json.dumps(self._state, indent=2) + "\n")
        except OSError as e:
            # Losing toggle state is not worth crashing the app over.
            logger.warning("Could not save state: %s", e)

    # ── Toggle state ──

    @staticmethod
    def _key(position):
        return f"{position[0]},{position[1]}"

    def get(self, deck_id, position, default="off"):
        value = self._state.get(str(deck_id), {}).get(self._key(position), default)
        return value if value in ("on", "off") else default

    def set(self, deck_id, position, value):
        deck_id = str(deck_id)
        self._state.setdefault(deck_id, {})[self._key(position)] = (
            "on" if value == "on" else "off"
        )
        self.save()

    def forget_position(self, deck_id, position):
        self._state.get(str(deck_id), {}).pop(self._key(position), None)
        self.save()

    def forget_deck(self, deck_id):
        if self._state.pop(str(deck_id), None) is not None:
            self.save()


_instance = None


def get_state_manager() -> StateManager:
    global _instance
    if _instance is None:
        _instance = StateManager()
    return _instance
