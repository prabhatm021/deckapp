"""The single application window. Pages are swapped inside a stack so the
window never jumps around the screen while navigating."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, Gtk

from deckapp.ui import confirm, load_css

WINDOW_MIN_WIDTH = 360
WINDOW_MIN_HEIGHT = 400


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.app = app

        load_css()
        self.set_title("DeckApp")
        # Tall and narrow: a deck list is a column, not a table
        self.set_default_size(520, 620)
        self.set_size_request(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.stack.set_transition_duration(120)

        self.set_content(self.stack)

        self._pages = {}
        self._install_actions()
        self.connect("close-request", self._on_close_request)

        self.show_deck_list()

    # ── Actions & shortcuts ──

    def _install_actions(self):
        for name, handler in (
            ("back", lambda *_: self._page_action("on_back")),
            ("save", lambda *_: self._page_action("on_save")),
            ("primary", lambda *_: self._page_action("on_primary")),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

    def _page_action(self, method_name):
        page = self.current_page()
        handler = getattr(page, method_name, None)
        if callable(handler):
            handler()

    # ── Page management ──

    def current_page(self):
        return self.stack.get_visible_child()

    def _swap(self, page, name):
        old = self._pages.get(name)
        if old is not None and old is not page:
            self.stack.remove(old)
        self._pages[name] = page
        if page.get_parent() is None:
            self.stack.add_named(page, name)
        self.stack.set_visible_child(page)

        # Drop pages we navigated away from so stale widgets don't linger
        for other_name, other in list(self._pages.items()):
            if other_name != name:
                self.stack.remove(other)
                del self._pages[other_name]

    def show_deck_list(self):
        from deckapp.ui.deck_list_page import DeckListPage
        self.set_title("DeckApp")
        self._swap(DeckListPage(self), "decks")

    def edit_deck(self, deck):
        from deckapp.ui.editor_page import EditorPage
        self.set_title(f"Editing {deck.name}")
        self._swap(EditorPage(self, deck), "editor")

    def open_pad(self, deck):
        """Open this deck in its own bare window, leaving the manager open."""
        self.get_application().open_pad(deck)

    # ── Closing ──

    def _on_close_request(self, *_args):
        """Never lose unsaved edits to a window close."""
        page = self.current_page()
        if getattr(page, "is_dirty", lambda: False)():
            confirm(
                self,
                "Unsaved changes",
                f"“{page.deck.name}” has unsaved changes.",
                "Discard & Close",
                self.destroy,
                destructive=True,
                cancel_label="Keep Editing",
            )
            return True  # stop the close for now
        return False
