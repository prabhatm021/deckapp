"""The pad — a deck on its own, with no window chrome around it.

Opened by clicking a deck in DeckApp, or from the command line with
`deckapp --deck <name>`, which is what a dock launcher runs.
"""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from deckapp.ui import load_css
from deckapp.ui.deck_grid import DeckGrid

MIN_WIDTH = 160
MIN_HEIGHT = 120

# The close button is invisible until the pointer is over it. Its hit area is
# larger than the glyph so the corner is easy to find, but small enough that it
# does not swallow presses meant for the key underneath.
CLOSE_HIT_SIZE = 34


class PadWindow(Adw.ApplicationWindow):
    def __init__(self, app, deck):
        super().__init__(application=app)
        self.deck = deck

        load_css()
        self.set_title(deck.name)
        self.add_css_class("deck-pad")

        # No title bar: the deck is the window
        self.set_decorated(False)
        self.set_resizable(False)

        self.grid = DeckGrid(
            deck, on_failure=lambda title, body: app.notify(title, body),
        )

        overlay = Gtk.Overlay()
        overlay.set_child(self.grid)
        self.close_button = self._build_close_button()
        overlay.add_overlay(self.close_button)
        self._overlay = overlay

        # Dragging anywhere that is not a deck button moves the pad
        handle = Gtk.WindowHandle()
        handle.set_child(overlay)

        self.set_content(handle)
        self.set_size_request(MIN_WIDTH, MIN_HEIGHT)
        self._install_keys()

    def _build_close_button(self):
        button = Gtk.Button()
        button.set_icon_name("window-close-symbolic")
        button.add_css_class("deck-pad-close")
        button.add_css_class("flat")
        button.add_css_class("circular")
        button.set_halign(Gtk.Align.END)
        button.set_valign(Gtk.Align.START)
        button.set_margin_top(2)
        button.set_margin_end(2)
        button.set_size_request(CLOSE_HIT_SIZE, CLOSE_HIT_SIZE)
        button.set_tooltip_text(f"Close “{self.deck.name}” (Esc)")
        # Never take keyboard focus. On a deck with no buttons every tile is an
        # insensitive placeholder, so this would be the only focusable widget in
        # the window: GTK would focus it on open and the focus ring would light
        # it up wherever the pointer was. Escape closes the pad anyway.
        button.set_can_focus(False)
        button.set_focus_on_click(False)
        button.connect("clicked", lambda *_: self.close())
        return button

    def _install_keys(self):
        keys = Gtk.EventControllerKey()

        def _pressed(_controller, keyval, _keycode, _state):
            if keyval == Gdk.KEY_Escape:
                self.close()
                return True
            return False

        keys.connect("key-pressed", _pressed)
        self.add_controller(keys)

    def reload(self, deck):
        """Rebuild for a deck that was just edited, keeping the window put."""
        self.deck = deck
        self.set_title(deck.name)
        self.grid = DeckGrid(
            deck,
            on_failure=lambda title, body: self.get_application().notify(
                title, body),
        )
        self._overlay.set_child(self.grid)
