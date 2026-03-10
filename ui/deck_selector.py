import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
from pathlib import Path

from deckapp.core.deck_loader import load_deck
from deckapp.core.paths import get_decks_dir
from deckapp.ui import load_css


class DeckSelector(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app)
        self.app = app
        self._deck_rows = []

        load_css()
        self.set_title("DeckApp")
        self.set_default_size(400, 520)

        # Adw: header bar lives INSIDE the content, not as titlebar
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="DeckApp", subtitle="Select a deck"))
        outer.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(560)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        inner.set_margin_top(18)
        inner.set_margin_bottom(18)
        inner.set_margin_start(18)
        inner.set_margin_end(18)

        self.group = Adw.PreferencesGroup()
        self.group.set_title("Decks")
        inner.append(self.group)

        new_btn = Gtk.Button(label="New Deck")
        new_btn.add_css_class("suggested-action")
        new_btn.add_css_class("pill")
        new_btn.set_halign(Gtk.Align.CENTER)
        new_btn.connect("clicked", self.on_new_deck)
        inner.append(new_btn)

        clamp.set_child(inner)
        scroll.set_child(clamp)
        outer.append(scroll)

        self.set_content(outer)
        self._load_decks()

    # ── Deck list ──

    def _load_decks(self):
        for deck_file in sorted(get_decks_dir().glob("*.json")):
            self._add_row(deck_file)

    def _add_row(self, deck_file):
        row = Adw.ActionRow()
        row.set_title(deck_file.stem)
        row.set_activatable(True)
        row.connect("activated", self.on_deck_selected, deck_file)

        row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))

        del_btn = Gtk.Button()
        del_btn.set_icon_name("user-trash-symbolic")
        del_btn.add_css_class("flat")
        del_btn.add_css_class("destructive-action")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.set_tooltip_text("Delete deck")
        del_btn.connect("clicked", self.on_delete_deck, deck_file)
        row.add_suffix(del_btn)

        self.group.add(row)
        self._deck_rows.append(row)

    def _reload(self):
        for row in self._deck_rows:
            self.group.remove(row)
        self._deck_rows.clear()
        self._load_decks()

    # ── Actions ──

    def on_new_deck(self, widget):
        from deckapp.ui.deck_create_dialog import DeckCreateDialog
        dialog = DeckCreateDialog(self)
        dialog.connect("response", self.on_new_deck_response)
        dialog.present()

    def on_new_deck_response(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            if dialog.create_deck():
                self._reload()
                dialog.close()
            # Validation failed — keep dialog open so user can correct it
        else:
            dialog.close()

    def on_deck_selected(self, row, deck_path):
        from deckapp.ui.layout_window import LayoutWindow
        deck = load_deck(deck_path)
        win = LayoutWindow(self.app, deck)
        win.present()
        self.close()

    def on_delete_deck(self, widget, deck_path):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=f"Delete \"{deck_path.stem}\"?",
            body="This action cannot be undone.",
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("delete", "Delete")
        dialog.set_response_appearance("delete", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_delete_response, deck_path)
        dialog.present()

    def _on_delete_response(self, dialog, response, deck_path):
        if response == "delete":
            try:
                deck_path.unlink()
            except OSError as e:
                print(f"[DeckApp] Failed to delete {deck_path.name}: {e}")
            self._reload()
