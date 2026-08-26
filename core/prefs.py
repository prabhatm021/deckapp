"""Small user preferences that are not deck data — currently the deck order.

Stored in ~/.config/deckapp/prefs.json, separate from deck files so that
reordering the list never rewrites a deck.
"""
import json
import logging

from deckapp.core.paths import atomic_write_text, get_config_dir

logger = logging.getLogger(__name__)

_ORDER_KEY = "deck_order"
_BACKGROUND_KEY = "run_in_background"


def _prefs_file():
    return get_config_dir() / "prefs.json"


def load() -> dict:
    try:
        data = json.loads(_prefs_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as e:
        logger.warning("Ignoring unreadable prefs file: %s", e)
        return {}
    return data if isinstance(data, dict) else {}


def save(prefs: dict) -> None:
    try:
        atomic_write_text(_prefs_file(), json.dumps(prefs, indent=2) + "\n")
    except OSError as e:
        logger.warning("Could not save prefs: %s", e)


def get_deck_order() -> list:
    order = load().get(_ORDER_KEY)
    return [str(key) for key in order] if isinstance(order, list) else []


def set_deck_order(keys) -> None:
    prefs = load()
    prefs[_ORDER_KEY] = [str(key) for key in keys]
    save(prefs)


def deck_key(deck) -> str:
    """Stable identity for ordering: the deck's file name."""
    return deck.path.stem if deck.path else deck.deck_id


def apply_deck_order(decks) -> list:
    """Sort decks by the saved order; anything new keeps its alphabetical spot."""
    order = get_deck_order()
    if not order:
        return list(decks)
    rank = {key: index for index, key in enumerate(order)}
    return sorted(decks, key=lambda d: (rank.get(deck_key(d), len(rank)),
                                        d.name.lower()))


def get_run_in_background() -> bool:
    return bool(load().get(_BACKGROUND_KEY, False))


def set_run_in_background(enabled: bool) -> None:
    prefs = load()
    prefs[_BACKGROUND_KEY] = bool(enabled)
    save(prefs)
