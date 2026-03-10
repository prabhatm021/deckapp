from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk, Gdk

_css_loaded = False


def load_css():
    """Load the minimal app-specific CSS once per process."""
    global _css_loaded
    if _css_loaded:
        return
    css_path = Path(__file__).resolve().parent / "style.css"
    provider = Gtk.CssProvider()
    provider.load_from_path(str(css_path))
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(),
        provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )
    _css_loaded = True
