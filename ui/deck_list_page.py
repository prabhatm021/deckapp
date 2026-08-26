"""The deck chooser — the app's home page."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk

from deckapp.core import prefs
from deckapp.core.deck_store import DeckError, delete_deck, load_all_decks
from deckapp.core.state_manager import get_state_manager
from deckapp.ui import confirm, show_error

ROW_ACTION_SIZE = 34


class DeckListPage(Gtk.Box):
    def __init__(self, window):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self._decks = []
        self._reorder_mode = False
        self.listbox = None
        self.count_label = None
        self.reorder_switch = None
        self.reorder_box = None
        self._row_decks = {}
        self._drag_row = None
        self._pending_row = None

        app = window.get_application()
        # Guard the pad API: a plain Gtk.Application (tests, tooling) has none
        self._app = app if hasattr(app, "is_pad_open") else None
        if self._app is not None:
            self._app.add_pad_listener(self._on_pads_changed)
            self.connect("destroy", lambda *_: self._app.remove_pad_listener(
                self._on_pads_changed))

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="DeckApp"))

        new_btn = Gtk.Button()
        new_btn.set_icon_name("list-add-symbolic")
        new_btn.set_tooltip_text("New deck (Ctrl+N)")
        new_btn.connect("clicked", lambda *_: self.on_primary())
        header.pack_start(new_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("open-menu-symbolic")
        menu_btn.set_tooltip_text("Main menu")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)

        self.append(header)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.content.set_vexpand(True)
        self.append(self.content)

        self.refresh()

    def _build_menu(self):
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append("Open Decks Folder", "app.open-folder")
        menu.append_section(None, section)

        about = Gio.Menu()
        about.append("Preferences", "app.preferences")
        about.append("Keyboard Shortcuts", "app.shortcuts")
        about.append("About DeckApp", "app.about")
        about.append("Quit", "app.quit")
        menu.append_section(None, about)
        return menu

    # ── Content ──

    def refresh(self):
        """Reload decks from disk and rebuild the page."""
        child = self.content.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.content.remove(child)
            child = nxt

        decks, errors = load_all_decks()
        self._decks = prefs.apply_deck_order(decks)
        if len(self._decks) < 2:
            self._reorder_mode = False

        if self._decks:
            self.content.append(self._build_list())
        else:
            self.content.append(self._build_empty_state())

        for message in errors:
            if self._app is not None:
                self._app.notify("A deck file could not be read", message,
                                 ident="deckapp-deck-error")

    def _build_list(self):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(560)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        inner.set_margin_top(24)
        inner.set_margin_bottom(24)
        inner.set_margin_start(12)
        inner.set_margin_end(12)
        inner.append(self._build_heading())

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self._fill_rows()
        inner.append(self.listbox)

        clamp.set_child(inner)
        scroll.set_child(clamp)
        return scroll

    def _build_heading(self):
        """“Decks – 3 decks” on the left, the Reorder button on the right."""
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        heading.set_margin_bottom(12)

        title = Gtk.Label(label="Decks", xalign=0)
        title.add_css_class("heading")
        heading.append(title)

        separator = Gtk.Label(label="–", xalign=0)
        separator.add_css_class("dim-label")
        heading.append(separator)

        self.count_label = Gtk.Label(xalign=0)
        self.count_label.add_css_class("dim-label")
        heading.append(self.count_label)

        self.reorder_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.reorder_box.set_halign(Gtk.Align.END)
        self.reorder_box.set_hexpand(True)
        self.reorder_box.set_visible(len(self._decks) > 1)

        self.reorder_box.add_css_class("deck-reorder")

        reorder_label = Gtk.Label(label="Reorder")
        reorder_label.add_css_class("dim-label")
        reorder_label.add_css_class("caption")
        reorder_label.set_valign(Gtk.Align.CENTER)
        self.reorder_box.append(reorder_label)

        self.reorder_switch = Gtk.Switch()
        self.reorder_switch.set_valign(Gtk.Align.CENTER)
        self.reorder_switch.set_active(self._reorder_mode)
        self.reorder_switch.set_tooltip_text("Rearrange the deck list")
        self.reorder_switch.connect(
            "notify::active",
            lambda switch, _p: self._set_reorder_mode(switch.get_active()),
        )
        self.reorder_box.append(self.reorder_switch)
        heading.append(self.reorder_box)

        self._sync_heading()
        return heading

    def _sync_heading(self):
        count = len(self._decks)
        self.count_label.set_label(
            "drag to reorder" if self._reorder_mode
            else f"{count} deck{'s' if count != 1 else ''}"
        )
        self.reorder_switch.set_tooltip_text(
            "Finish reordering" if self._reorder_mode
            else "Rearrange the deck list"
        )

    def _fill_rows(self):
        child = self.listbox.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.listbox.remove(child)
            child = nxt
        self._row_decks.clear()
        for deck in self._decks:
            self.listbox.append(self._build_row(deck))

    def _on_pads_changed(self):
        """A pad opened or closed — swap the open/close buttons."""
        if self.listbox is not None:
            self._fill_rows()

    def _set_reorder_mode(self, active):
        if active == self._reorder_mode:
            return
        self._reorder_mode = active
        if self.reorder_switch.get_active() != active:
            self.reorder_switch.set_active(active)
        self._sync_heading()
        self._fill_rows()

    # ── Rows ──

    def _build_row(self, deck):
        row = Adw.ActionRow()
        # Row titles are Pango markup — escape so names like "R&D" work.
        row.set_title(GLib.markup_escape_text(deck.name))
        row.set_subtitle(f"{deck.rows} × {deck.cols}")

        if self._reorder_mode:
            return self._decorate_movable(row, deck)

        row.add_css_class("deck-row")
        row.set_activatable(True)
        row.set_tooltip_text(f"Open “{deck.name}”")
        row.connect("activated", lambda *_: self.window.open_pad(deck))

        # One box, equal cells: the icons end up evenly spaced whatever
        # padding the buttons carry.
        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        actions.set_valign(Gtk.Align.CENTER)

        edit_btn = self._row_action(
            "document-edit-symbolic", f"Edit “{deck.name}”",
            lambda *_: self.window.edit_deck(deck),
        )
        actions.append(edit_btn)

        del_btn = self._row_action(
            "user-trash-symbolic", f"Delete “{deck.name}”",
            lambda *_: self._confirm_delete(deck),
        )
        actions.append(del_btn)

        # While a deck is open as a pad, the same slot closes it again
        if self._app is not None and self._app.is_pad_open(deck.deck_id):
            row.add_css_class("deck-row-open")
            open_btn = self._row_action(
                "window-close-symbolic", f"Close “{deck.name}”",
                lambda *_, d=deck: self._app.close_pad(d.deck_id),
            )
        else:
            open_btn = self._row_action(
                "go-next-symbolic", f"Open “{deck.name}”",
                lambda *_: self.window.open_pad(deck),
            )
        actions.append(open_btn)

        row.add_suffix(actions)
        return row

    @staticmethod
    def _row_action(icon_name, tooltip, on_click):
        button = Gtk.Button()
        button.set_icon_name(icon_name)
        button.add_css_class("flat")
        button.set_valign(Gtk.Align.CENTER)
        button.set_size_request(ROW_ACTION_SIZE, ROW_ACTION_SIZE)
        button.set_tooltip_text(tooltip)
        button.connect("clicked", on_click)
        return button

    def _decorate_movable(self, row, deck):
        """Reorder mode: a drag handle, and the row itself moves as you drag."""
        handle = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic")
        handle.add_css_class("dim-label")
        handle.set_tooltip_text("Drag to move")
        row.add_prefix(handle)
        row.add_css_class("deck-row-movable")
        self._row_decks[row] = deck
        self._add_row_dnd(row)
        return row

    # ── Dragging ──
    #
    # The dragged row stays in the list and the rows it passes swap around it,
    # so the block rearranges under the pointer. The dragged row is never
    # unparented — that would cancel the drag mid-flight.

    def _add_row_dnd(self, row):
        source = Gtk.DragSource()
        source.set_actions(Gdk.DragAction.MOVE)
        source.connect(
            "prepare",
            lambda *_: Gdk.ContentProvider.new_for_value(GObject.Value(str, "deck")),
        )
        source.connect("drag-begin", lambda drag_source, _d:
                       self._drag_begin(drag_source, row))
        source.connect("drag-end", lambda *_: self._drag_end())
        source.connect("drag-cancel", lambda *_: (self._drag_end(), False)[1])
        row.add_controller(source)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("motion", lambda *_: self._drag_over(row))
        target.connect("drop", lambda *_: self._drag_end() or True)
        row.add_controller(target)

    def _drag_begin(self, source, row):
        # No floating copy of the row — the real row does the moving
        source.set_icon(_blank_icon(), 0, 0)
        self._drag_row = row
        row.add_css_class("deck-row-dragging")

    def _drag_over(self, row):
        """Defer the swap: reparenting rows inside a crossing handler makes
        GTK's drop target bookkeeping complain."""
        if (self._drag_row is None or row is self._drag_row
                or self._pending_row is row):
            return Gdk.DragAction.MOVE

        self._pending_row = row
        GLib.idle_add(self._apply_row_swap, row)
        return Gdk.DragAction.MOVE

    def _apply_row_swap(self, row):
        self._pending_row = None
        if self._drag_row is None or row is self._drag_row:
            return GLib.SOURCE_REMOVE
        if row.get_parent() is not self.listbox:
            return GLib.SOURCE_REMOVE

        position = self._row_position(self._drag_row)
        self.listbox.remove(row)
        self.listbox.insert(row, position)
        return GLib.SOURCE_REMOVE

    def _drag_end(self):
        self._pending_row = None
        if self._drag_row is not None:
            self._drag_row.remove_css_class("deck-row-dragging")
            self._drag_row = None
        self._save_widget_order()

    def _row_position(self, row):
        position = 0
        child = self.listbox.get_first_child()
        while child and child is not row:
            position += 1
            child = child.get_next_sibling()
        return position

    def _save_widget_order(self):
        """Read the order back off the rows and persist it."""
        decks = []
        child = self.listbox.get_first_child() if self.listbox else None
        while child:
            deck = self._row_decks.get(child)
            if deck is not None:
                decks.append(deck)
            child = child.get_next_sibling()

        if len(decks) != len(self._decks) or decks == self._decks:
            return
        self._decks = decks
        prefs.set_deck_order([prefs.deck_key(deck) for deck in decks])

    # ── Empty state ──

    def _build_empty_state(self):
        status = Adw.StatusPage()
        status.set_icon_name("view-grid-symbolic")
        status.set_title("No decks yet")
        status.set_description(
            "A deck is a grid of buttons that run shell commands."
        )
        status.set_vexpand(True)

        button = Gtk.Button(label="New Deck")
        button.add_css_class("suggested-action")
        button.add_css_class("pill")
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", lambda *_: self.on_primary())
        status.set_child(button)
        return status

    # ── Actions ──

    def on_primary(self):
        """Ctrl+N / the + button."""
        from deckapp.ui.deck_dialog import DeckCreateDialog
        DeckCreateDialog(self.window, on_created=self._on_created).present()

    def _on_created(self, deck):
        # A new deck is empty — go straight to the editor
        self.window.edit_deck(deck)

    def _confirm_delete(self, deck):
        confirm(
            self.window,
            f"Delete “{deck.name}”?",
            "The deck and its buttons will be permanently removed.",
            "Delete",
            lambda: self._delete(deck),
        )

    def _delete(self, deck):
        if self._app is not None:
            # Its window would otherwise keep running a deck that is gone
            self._app.close_pad(deck.deck_id)
        try:
            delete_deck(deck.path)
        except DeckError as e:
            show_error(self.window, "Could not delete deck", str(e))
            return
        get_state_manager().forget_deck(deck.deck_id)
        self.refresh()

    def on_back(self):
        """Escape leaves reorder mode; otherwise home has nowhere to go."""
        self._set_reorder_mode(False)


def _blank_icon():
    """A 1×1 transparent drag icon — the list itself shows what is happening."""
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 1, 1)
    pixbuf.fill(0x00000000)
    return Gdk.Texture.new_for_pixbuf(pixbuf)
