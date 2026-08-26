"""Dialogs for creating a deck and for editing its name and grid size."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from deckapp.core.deck_store import (DeckError, MAX_NAME_LEN, create_deck,
                                     validate_name)
from deckapp.core.models import (DEFAULT_COLS, DEFAULT_ROWS, MAX_GRID,
                                 MIN_GRID)
from deckapp.ui import confirm


class _DeckFormDialog(Adw.Window):
    """Shared name + grid-size form."""

    def __init__(self, window, title, action_label, name="",
                 rows=DEFAULT_ROWS, cols=DEFAULT_COLS):
        super().__init__(transient_for=window, modal=True)
        self.window = window

        self.set_title(title)
        self.set_default_size(420, -1)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_show_start_title_buttons(False)
        header.set_show_end_title_buttons(False)
        header.set_title_widget(Adw.WindowTitle(title=title))

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel_btn)

        self.action_btn = Gtk.Button(label=action_label)
        self.action_btn.add_css_class("suggested-action")
        self.action_btn.connect("clicked", lambda *_: self._submit())
        header.pack_end(self.action_btn)
        outer.append(header)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        body.set_margin_top(18)
        body.set_margin_bottom(18)
        body.set_margin_start(18)
        body.set_margin_end(18)

        group = Adw.PreferencesGroup()

        self.name_row = Adw.EntryRow()
        self.name_row.set_title("Deck name")
        self.name_row.set_text(name)
        self.name_row.connect("changed", lambda *_: self._clear_error())
        self.name_row.connect("entry-activated", lambda *_: self._submit())
        group.add(self.name_row)

        self.rows_row, self.rows_spin = self._spin_row("Rows", rows)
        self.cols_row, self.cols_spin = self._spin_row("Columns", cols)
        group.add(self.rows_row)
        group.add(self.cols_row)
        body.append(group)

        self.error_label = Gtk.Label()
        self.error_label.add_css_class("error")
        self.error_label.set_halign(Gtk.Align.START)
        self.error_label.set_wrap(True)
        self.error_label.set_visible(False)
        body.append(self.error_label)

        outer.append(body)
        self.set_content(outer)
        self._install_keys()

    def _spin_row(self, title, value):
        row = Adw.ActionRow()
        row.set_title(title)
        spin = Gtk.SpinButton.new_with_range(MIN_GRID, MAX_GRID, 1)
        spin.set_value(value)
        spin.set_valign(Gtk.Align.CENTER)
        spin.connect("value-changed", lambda *_: self._clear_error())
        row.add_suffix(spin)
        row.set_activatable_widget(spin)
        return row, spin

    def _install_keys(self):
        keys = Gtk.EventControllerKey()

        def _pressed(_controller, keyval, _keycode, _state):
            if keyval == Gdk.KEY_Escape:
                self.close()
                return True
            return False

        keys.connect("key-pressed", _pressed)
        self.add_controller(keys)

    # ── Helpers ──

    def _values(self):
        return (
            self.name_row.get_text().strip(),
            int(self.rows_spin.get_value()),
            int(self.cols_spin.get_value()),
        )

    def _show_error(self, message):
        self.error_label.set_text(message)
        self.error_label.set_visible(True)
        self.name_row.add_css_class("error")

    def _clear_error(self):
        self.error_label.set_visible(False)
        self.name_row.remove_css_class("error")

    def _submit(self):
        raise NotImplementedError


class DeckCreateDialog(_DeckFormDialog):
    def __init__(self, window, on_created=None):
        super().__init__(window, "New Deck", "Create")
        self.on_created = on_created

    def _submit(self):
        name, rows, cols = self._values()
        error = validate_name(name)
        if error:
            self._show_error(error)
            return
        try:
            deck = create_deck(name, rows, cols)
        except DeckError as e:
            self._show_error(str(e))
            return
        self.close()
        if self.on_created:
            self.on_created(deck)


class DeckPropertiesDialog(_DeckFormDialog):
    def __init__(self, window, deck, on_apply=None):
        super().__init__(
            window, "Deck Properties", "Apply",
            name=deck.name, rows=deck.rows, cols=deck.cols,
        )
        self.deck = deck
        self.on_apply = on_apply

    def _submit(self):
        name, rows, cols = self._values()
        error = validate_name(name)
        if error:
            self._show_error(error)
            return

        lost = self.deck.buttons_lost_by_resize(rows, cols)
        if lost:
            names = ", ".join(f"“{b.display_label()}”" for b in lost[:3])
            if len(lost) > 3:
                names += f" and {len(lost) - 3} more"
            confirm(
                self,
                f"Remove {len(lost)} button{'s' if len(lost) != 1 else ''}?",
                f"The smaller grid has no room for {names}.",
                "Shrink Grid",
                lambda: self._apply(name, rows, cols),
            )
            return
        self._apply(name, rows, cols)

    def _apply(self, name, rows, cols):
        self.close()
        if self.on_apply:
            self.on_apply(name[:MAX_NAME_LEN], rows, cols)
