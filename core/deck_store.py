"""Loading, saving, creating and deleting deck files.

Every function raises DeckError (never a bare OSError/JSONDecodeError) so the
UI has exactly one exception type to catch.
"""
import json
import logging
import re
import unicodedata
from pathlib import Path

from deckapp.core.models import Deck, DEFAULT_COLS, DEFAULT_ROWS, clamp_grid
from deckapp.core.paths import atomic_write_text, get_decks_dir

logger = logging.getLogger(__name__)

MAX_NAME_LEN = 60


class DeckError(Exception):
    """Anything that stopped a deck from being read or written."""


def slugify(name: str) -> str:
    """A filesystem- and id-safe slug. Returns '' if nothing usable is left."""
    normalised = unicodedata.normalize("NFKD", name)
    ascii_only = normalised.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug[:MAX_NAME_LEN]


def validate_name(name: str) -> str:
    """Return an error message, or '' if the name is usable."""
    name = (name or "").strip()
    if not name:
        return "Deck name cannot be empty."
    if len(name) > MAX_NAME_LEN:
        return f"Deck name must be {MAX_NAME_LEN} characters or fewer."
    if not slugify(name):
        return "Deck name must contain at least one letter or number."
    return ""


def _unique_path(slug: str, exclude: Path | None = None) -> Path:
    """decks/<slug>.json, with -2, -3 … appended if that name is taken."""
    decks_dir = get_decks_dir()
    candidate = decks_dir / f"{slug}.json"
    counter = 2
    while candidate.exists() and candidate != exclude:
        candidate = decks_dir / f"{slug}-{counter}.json"
        counter += 1
    return candidate


def list_deck_paths():
    try:
        return sorted(get_decks_dir().glob("*.json"), key=lambda p: p.name.lower())
    except OSError as e:
        raise DeckError(f"Could not read the decks folder: {e}") from e


def load_deck(path) -> Deck:
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as e:
        raise DeckError(f"Could not open “{path.name}”: {e.strerror or e}") from e

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DeckError(f"“{path.name}” is not valid JSON (line {e.lineno}).") from e
    except ValueError as e:
        raise DeckError(f"“{path.name}” could not be parsed: {e}") from e

    if not isinstance(data, dict):
        raise DeckError(f"“{path.name}” does not contain a deck.")

    return Deck.from_dict(data, path=path, fallback_id=path.stem)


def load_all_decks():
    """Returns (decks, errors) — a bad file never hides the good ones."""
    decks, errors = [], []
    try:
        paths = list_deck_paths()
    except DeckError as e:
        return decks, [str(e)]

    for path in paths:
        try:
            decks.append(load_deck(path))
        except DeckError as e:
            logger.warning("Skipping deck %s: %s", path.name, e)
            errors.append(str(e))
    return decks, errors


def save_deck(deck, path=None) -> Path:
    path = Path(path or deck.path or _unique_path(slugify(deck.name) or "deck"))
    try:
        atomic_write_text(path, json.dumps(deck.to_dict(), indent=2) + "\n")
    except OSError as e:
        raise DeckError(f"Could not save “{deck.name}”: {e.strerror or e}") from e
    deck.path = path
    return path


def create_deck(name, rows=DEFAULT_ROWS, cols=DEFAULT_COLS) -> Deck:
    error = validate_name(name)
    if error:
        raise DeckError(error)

    name = name.strip()
    slug = slugify(name)
    deck = Deck(
        deck_id=slug,
        name=name,
        rows=clamp_grid(rows, DEFAULT_ROWS),
        cols=clamp_grid(cols, DEFAULT_COLS),
    )
    path = _unique_path(slug)
    # deck_id follows the filename so two decks named the same never share state
    deck.deck_id = path.stem
    save_deck(deck, path)
    return deck


def delete_deck(path) -> None:
    try:
        Path(path).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        raise DeckError(f"Could not delete “{Path(path).name}”: {e.strerror or e}") from e
