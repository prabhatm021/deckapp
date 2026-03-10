import re
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

from deckapp.core.deck_loader import create_empty_deck
from deckapp.core.paths import get_decks_dir
from deckapp.ui import load_css


def _sanitize_filename(name: str) -> str:
    """Convert a deck name into a safe filename (no path separators or special chars)."""
    return re.sub(r'[^\w\-. ]', '', name).strip()


class DeckCreateDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="New Deck", transient_for=parent, modal=True)

        load_css()
        self.set_default_size(380, -1)

        content = self.get_content_area()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(12)
        box.set_margin_bottom(0)
        box.set_margin_start(16)
        box.set_margin_end(16)
        content.append(box)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        box.append(listbox)

        self.name_row = Adw.EntryRow()
        self.name_row.set_title("Deck name")
        listbox.append(self.name_row)

        self.error_label = Gtk.Label()
        self.error_label.add_css_class("error")
        self.error_label.set_halign(Gtk.Align.START)
        self.error_label.set_visible(False)
        box.append(self.error_label)

        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.ok_btn = self.add_button("Create", Gtk.ResponseType.OK)
        self.ok_btn.add_css_class("suggested-action")

        self.name_row.connect("changed", self._on_name_changed)

    def _on_name_changed(self, row):
        self.error_label.set_visible(False)

    def _validate(self) -> str | None:
        """Return an error message, or None if valid."""
        name = self.name_row.get_text().strip()
        if not name:
            return "Deck name cannot be empty."
        safe = _sanitize_filename(name)
        if not safe:
            return "Name contains only special characters."
        dest = get_decks_dir() / f"{safe}.json"
        if dest.exists():
            return f'A deck named "{safe}" already exists.'
        return None

    def create_deck(self) -> bool:
        """Validate and create the deck. Returns True on success."""
        error = self._validate()
        if error:
            self.error_label.set_text(error)
            self.error_label.set_visible(True)
            return False
        name = self.name_row.get_text().strip()
        safe = _sanitize_filename(name)
        create_empty_deck(get_decks_dir() / f"{safe}.json", name, rows=4, cols=4)
        return True
