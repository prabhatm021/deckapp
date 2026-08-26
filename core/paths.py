"""
Centralised path resolution for DeckApp.

Dev mode  : data lives next to the source tree (so a git clone is self-contained)
Installed : data lives in $XDG_DATA_HOME/deckapp (the install dir is read-only)

Set DECKAPP_DATA_DIR to override both.
"""
import os
from pathlib import Path

# The package root (where app.py / ui/ / core/ live)
_PKG_DIR = Path(__file__).resolve().parent.parent  # deckapp/

# Prefixes that mean "installed system-wide, do not write here"
_SYSTEM_PREFIXES = ("/usr/", "/opt/", "/nix/store/", "/app/")


def is_installed() -> bool:
    """True when running from a read-only system location or a site-packages dir."""
    p = str(_PKG_DIR)
    if p.startswith(_SYSTEM_PREFIXES):
        return True
    if "site-packages" in _PKG_DIR.parts or "dist-packages" in _PKG_DIR.parts:
        return True
    return not os.access(_PKG_DIR, os.W_OK)


def get_data_dir() -> Path:
    """User-writable data directory."""
    override = os.environ.get("DECKAPP_DATA_DIR")
    if override:
        d = Path(override).expanduser()
    elif is_installed():
        xdg = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
        d = xdg / "deckapp"
    else:
        # Running from a writable source tree — keep data next to the source
        d = _PKG_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_dir() -> Path:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    d = xdg / "deckapp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_decks_dir() -> Path:
    d = get_data_dir() / "decks"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_assets_dir() -> Path:
    d = get_data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_icons_dir() -> Path:
    d = get_assets_dir() / "icons"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_asset(relative: str) -> str:
    """Turn a stored relative asset path (e.g. 'icons/x.png') into an absolute path."""
    return str((get_assets_dir() / relative).resolve())


def to_relative_asset(absolute: str) -> str:
    """Inverse of resolve_asset(). Returns the input unchanged if it is outside assets/."""
    try:
        return str(Path(absolute).resolve().relative_to(get_assets_dir().resolve()))
    except ValueError:
        return absolute


def is_stored_asset(path: str) -> bool:
    """True if `path` already lives inside the managed assets directory."""
    try:
        Path(path).resolve().relative_to(get_assets_dir().resolve())
        return True
    except (ValueError, OSError):
        return False


def atomic_write_text(path: Path, text: str) -> None:
    """Write a file atomically so a crash mid-write cannot corrupt it."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def get_app_icon_dir() -> Path:
    """Where DeckApp's own icons live (works from a checkout or an install)."""
    return _PKG_DIR / "assets" / "app"


def get_app_icon_file() -> Path:
    return get_app_icon_dir() / "io.github.prabhatm021.deckapp.svg"


def get_menu_play_icon() -> bytes:
    """PNG bytes for the tray menu's play glyph (empty if it is missing)."""
    try:
        return (get_app_icon_dir() / "deck-play.png").read_bytes()
    except OSError:
        return b""
