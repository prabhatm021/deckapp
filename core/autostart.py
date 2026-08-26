"""The 'start on login' entry — a .desktop file in ~/.config/autostart."""
import logging
import os
import shutil
import sys
from pathlib import Path

from deckapp.core.paths import get_app_icon_file, is_installed

logger = logging.getLogger(__name__)

FILENAME = "io.github.prabhatm021.deckapp-tray.desktop"


def autostart_dir() -> Path:
    xdg = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return xdg / "autostart"


def autostart_file() -> Path:
    return autostart_dir() / FILENAME


def launch_command() -> str:
    """How to start *this* copy of DeckApp in the background.

    Never trust `which deckapp`: an older packaged version may be first on
    PATH, and it would not understand --tray.
    """
    if is_installed():
        launcher = shutil.which("deckapp")
        if launcher:
            return f"{launcher} --tray"
    run_py = Path(__file__).resolve().parent.parent / "run.py"
    return f"{sys.executable} {run_py} --tray"


def is_enabled() -> bool:
    return autostart_file().is_file()


def set_enabled(enabled: bool) -> bool:
    """Create or remove the autostart entry. Returns True on success."""
    path = autostart_file()
    if not enabled:
        try:
            path.unlink(missing_ok=True)
            return True
        except OSError as e:
            logger.warning("Could not remove %s: %s", path, e)
            return False

    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=DeckApp Tray\n"
        "Comment=Keep decks one click away in the top bar\n"
        f"Exec={launch_command()}\n"
        f"Icon={get_app_icon_file()}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
        "NoDisplay=true\n"
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return True
    except OSError as e:
        logger.warning("Could not write %s: %s", path, e)
        return False
