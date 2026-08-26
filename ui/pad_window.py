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

# The close button only appears while the pointer is in this corner, measured
# from the top right. Window-wide :hover would show it the whole time the pad
# is in use, which defeats the point of a bare window.
CORNER_WIDTH = 96
CORNER_HEIGHT = 64


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
        self._watch_pointer()
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
        button.set_margin_top(4)
        button.set_margin_end(4)
        button.set_tooltip_text(f"Close “{self.deck.name}” (Esc)")
        button.connect("clicked", lambda *_: self.close())
        return button

    def _watch_pointer(self):
        motion = Gtk.EventControllerMotion()
        motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        motion.connect("motion", self._on_pointer_moved)
        motion.connect("leave", lambda *_: self._show_close(False))
        self.add_controller(motion)

        # Belt and braces: a pointer that leaves without a leave event, or a
        # window that loses focus, must not strand the button on screen.
        self.connect("notify::is-active",
                     lambda *_: None if self.is_active() else self._show_close(False))

    def _on_pointer_moved(self, _controller, x, y):
        in_corner = (x >= self.get_width() - CORNER_WIDTH
                     and y <= CORNER_HEIGHT)
        self._show_close(in_corner)

    def _show_close(self, visible):
        if visible:
            self.close_button.add_css_class("visible")
        else:
            self.close_button.remove_css_class("visible")

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
