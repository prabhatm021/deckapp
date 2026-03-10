"""
Centralised path resolution for DeckApp.

Dev mode  : data lives next to the source tree  (~/.local/share/deckapp NOT used)
Installed : data lives in ~/.local/share/deckapp  (install dir is read-only)
"""
import os
from pathlib import Path

# The package root (where app.py / ui/ / core/ live)
_PKG_DIR = Path(__file__).resolve().parent.parent  # deckapp/


def _is_installed() -> bool:
    """True when running from a system path like /usr/lib/…"""
    return str(_PKG_DIR).startswith("/usr/")


def get_data_dir() -> Path:
    """User-writable data directory (XDG_DATA_HOME / deckapp)."""
    if _is_installed():
        xdg = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        d = xdg / "deckapp"
    else:
        # Running from source tree — keep data next to source
        d = _PKG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_decks_dir() -> Path:
    d = get_data_dir() / "decks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_icons_dir() -> Path:
    d = get_data_dir() / "assets" / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_icon_path(relative: str) -> str:
    """Turn a stored relative icon path into an absolute path."""
    return str((get_data_dir() / "assets" / relative).resolve())
