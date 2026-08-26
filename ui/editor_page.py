"""Edit mode — add, edit, move and delete buttons."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Adw, Gdk, GdkPixbuf, Gio, GLib, GObject, Gtk

from deckapp.core.deck_store import DeckError, save_deck
from deckapp.core.models import Button
from deckapp.core.state_manager import get_state_manager
from deckapp.ui import (DESTRUCTIVE, SUGGESTED, alert, confirm,
                        make_tile_content, show_error)


class EditorPage(Gtk.Box):
    def __init__(self, window, deck):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.window = window
        self.deck = deck
        self._dirty = False
        self._tiles = {}
        self._drag_pos = None
        self._drag_origin = None
        self._pending_swap = None

        header = Adw.HeaderBar()
        self.title_widget = Adw.WindowTitle(title=deck.name, subtitle="")
        header.set_title_widget(self.title_widget)

        done_btn = Gtk.Button(label="Done")
        done_btn.set_tooltip_text("Back to the deck list (Esc)")
        done_btn.connect("clicked", lambda *_: self.on_back())
        header.pack_start(done_btn)

        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.set_tooltip_text("Save changes (Ctrl+S)")
        self.save_btn.set_sensitive(False)
        self.save_btn.connect("clicked", lambda *_: self.on_save())
        header.pack_end(self.save_btn)

        menu_btn = Gtk.MenuButton()
        menu_btn.set_icon_name("view-more-symbolic")
        menu_btn.set_tooltip_text("Deck options")
        menu_btn.set_menu_model(self._build_menu())
        header.pack_end(menu_btn)

        self._install_actions()
        self.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        self.grid = Gtk.Grid(
            row_spacing=10, column_spacing=10,
            margin_top=16, margin_bottom=16, margin_start=16, margin_end=16,
        )
        self.grid.set_halign(Gtk.Align.CENTER)
        self.grid.set_valign(Gtk.Align.CENTER)
        scroll.set_child(self.grid)
        self.append(scroll)

        self._build_grid()

    def _build_menu(self):
        menu = Gio.Menu()
        menu.append("Deck Properties", "editor.properties")
        menu.append("Clear Deck", "editor.clear")
        return menu

    def _install_actions(self):
        group = Gio.SimpleActionGroup()
        for name, handler in (
            ("properties", self.on_properties),
            ("clear", self.on_clear),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, h=handler: h())
            group.add_action(action)
        self.insert_action_group("editor", group)

    # ── Dirty state ──

    def is_dirty(self):
        return self._dirty

    def _set_dirty(self, dirty=True):
        self._dirty = dirty
        self.save_btn.set_sensitive(dirty)
        self.title_widget.set_title(
            f"{self.deck.name} •" if dirty else self.deck.name
        )

    # ── Grid ──
    #
    # One widget per cell, created once and re-rendered from the deck. Dragging
    # swaps the deck data and re-renders the two cells, so tiles rearrange under
    # the pointer without any widget being unparented mid-drag (which would
    # cancel the drag).

    def _build_grid(self):
        self._tiles = {}
        for row, col in self.deck.positions():
            widget = Gtk.Button()
            widget.add_css_class("deck-btn")
            widget.connect("clicked", self._on_tile_clicked, (row, col))
            self._add_tile_dnd(widget, (row, col))
            self._tiles[(row, col)] = widget
            self.grid.attach(widget, col, row, 1, 1)
            self._render_tile((row, col))

    def _refresh_grid(self):
        """Rebuild after the grid size changed."""
        child = self.grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        self._build_grid()

    def _render_tile(self, pos):
        """Draw whatever the deck now holds at this position."""
        widget = self._tiles.get(pos)
        if widget is None:
            return
        row, col = pos
        button = self.deck.get(row, col)

        for css in ("deck-empty", "deck-unset", "deck-dragging",
                    "deck-toggle-on", "deck-toggle-off"):
            widget.remove_css_class(css)

        if button is None:
            widget.add_css_class("deck-empty")
            icon = Gtk.Image.new_from_icon_name("list-add-symbolic")
            icon.set_pixel_size(24)
            widget.set_child(icon)
            return

        widget.set_child(make_tile_content(button))
        if button.is_toggle:
            # Its default state, the same colours the pad uses
            widget.add_css_class("deck-toggle-on" if button.state == "on"
                                 else "deck-toggle-off")
        if not button.is_configured():
            widget.add_css_class("deck-unset")

    def _on_tile_clicked(self, _widget, pos):
        row, col = pos
        if self.deck.get(row, col) is None:
            self.on_add_button(row, col)
        else:
            self.on_edit_button(row, col)

    # ── Dragging ──

    def _add_tile_dnd(self, widget, pos):
        source = Gtk.DragSource()
        source.set_actions(Gdk.DragAction.MOVE)

        def _prepare(_source, _x, _y):
            row, col = pos
            if self.deck.get(row, col) is None:
                return None          # nothing to drag out of an empty cell
            return Gdk.ContentProvider.new_for_value(
                GObject.Value(str, f"{row},{col}")
            )

        def _begin(drag_source, _drag):
            drag_source.set_icon(_blank_icon(), 0, 0)
            self._drag_pos = pos
            self._drag_origin = pos
            self._tiles[pos].add_css_class("deck-dragging")

        source.connect("prepare", _prepare)
        source.connect("drag-begin", _begin)
        source.connect("drag-end", lambda *_: self._end_drag())
        source.connect("drag-cancel", lambda *_: (self._end_drag(), False)[1])
        widget.add_controller(source)

        target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        target.connect("motion", lambda *_: self._drag_over(pos))
        target.connect("drop", lambda *_: self._drop_on(pos))
        widget.add_controller(target)

    def _drag_over(self, pos):
        """Schedule the swap; do not touch widgets while GTK is delivering a
        crossing event, or its drop target bookkeeping trips its own asserts."""
        if (self._drag_pos is None or pos == self._drag_pos
                or self._pending_swap == pos):
            return Gdk.DragAction.MOVE

        self._pending_swap = pos
        GLib.idle_add(self._apply_swap, pos)
        return Gdk.DragAction.MOVE

    def _apply_swap(self, pos):
        self._pending_swap = None
        if self._drag_pos is None or pos == self._drag_pos:
            return GLib.SOURCE_REMOVE

        moved_from = self._drag_pos
        self.deck.move(moved_from, pos)      # swaps if the cell is taken
        self._drag_pos = pos

        self._render_tile(moved_from)
        self._render_tile(pos)
        self._tiles[pos].add_css_class("deck-dragging")
        return GLib.SOURCE_REMOVE

    def _drop_on(self, pos):
        self._apply_swap(pos)
        self._finish_drag()
        return True

    def _end_drag(self):
        self._finish_drag()

    def _finish_drag(self):
        self._pending_swap = None
        if self._drag_pos is None:
            return
        landed, origin = self._drag_pos, self._drag_origin
        self._drag_pos = self._drag_origin = None

        for pos in (landed, origin):
            if pos is not None:
                self._tiles[pos].remove_css_class("deck-dragging")
                self._render_tile(pos)

        if landed != origin:
            self._sync_toggle_state(origin, landed)
            self._set_dirty()

    def _sync_toggle_state(self, origin, landed):
        """Saved toggle states follow their buttons across the grid."""
        state_manager = get_state_manager()
        moved = self.deck.get(*landed)
        displaced = self.deck.get(*origin)

        if moved is not None and moved.is_toggle:
            state_manager.set(self.deck.deck_id, landed, moved.state)
        if displaced is not None and displaced.is_toggle:
            state_manager.set(self.deck.deck_id, origin, displaced.state)
        elif displaced is None:
            state_manager.forget_position(self.deck.deck_id, origin)

    # ── Add / edit buttons ──

    def on_add_button(self, row, col):
        from deckapp.ui.button_editor import ButtonEditor
        ButtonEditor(
            self.window,
            title="Add Button",
            subtitle=f"Row {row + 1}, column {col + 1}",
            on_save=lambda data: self._apply_new(row, col, data),
        ).present()

    def _apply_new(self, row, col, data):
        self.deck.place(row, col, Button(row=row, col=col, **data))
        self._set_dirty()
        self._refresh_grid()

    def on_edit_button(self, row, col):
        from deckapp.ui.button_editor import ButtonEditor
        button = self.deck.get(row, col)
        if button is None:
            return
        ButtonEditor(
            self.window,
            title="Edit Button",
            subtitle=f"Row {row + 1}, column {col + 1}",
            button=button,
            on_save=lambda data: self._apply_edit(row, col, data),
            on_delete=lambda: self._delete_button(row, col),
        ).present()

    def _apply_edit(self, row, col, data):
        button = self.deck.get(row, col)
        if button is None:
            return
        for key, value in data.items():
            setattr(button, key, value)
        self._set_dirty()
        self._refresh_grid()

    def _delete_button(self, row, col):
        button = self.deck.remove(row, col)
        if button is None:
            return
        get_state_manager().forget_position(self.deck.deck_id, (row, col))
        self._set_dirty()
        self._refresh_grid()

    # ── Deck-level actions ──

    def on_properties(self):
        from deckapp.ui.deck_dialog import DeckPropertiesDialog
        DeckPropertiesDialog(
            self.window, self.deck, on_apply=self._apply_properties
        ).present()

    def _apply_properties(self, name, rows, cols):
        changed = False
        if name != self.deck.name:
            self.deck.name = name
            changed = True
        if (rows, cols) != (self.deck.rows, self.deck.cols):
            self.deck.resize(rows, cols)
            changed = True
        if changed:
            self._set_dirty()
            self._refresh_grid()

    def on_clear(self):
        if not self.deck.buttons:
            return
        confirm(
            self.window,
            "Remove all buttons?",
            f"All {len(self.deck.buttons)} buttons will be removed. "
            "Nothing is written to disk until you save.",
            "Clear Deck",
            self._clear_buttons,
        )

    def _clear_buttons(self):
        self.deck.buttons.clear()
        get_state_manager().forget_deck(self.deck.deck_id)
        self._set_dirty()
        self._refresh_grid()

    # ── Save / leave ──

    def on_save(self):
        return self._save()

    def _save(self):
        try:
            save_deck(self.deck, self.deck.path)
        except DeckError as e:
            show_error(self.window, "Could not save deck", str(e))
            return False
        self._set_dirty(False)
        # An open pad for this deck is now out of date
        app = self.window.get_application()
        if hasattr(app, "reload_pad"):
            app.reload_pad(self.deck)
        return True

    def on_back(self):
        if not self._dirty:
            self._leave()
            return

        def _chosen(response):
            if response == "save":
                self._save_and_leave()
            elif response == "discard":
                self._leave()

        alert(
            self.window,
            "Save changes?",
            f"“{self.deck.name}” has unsaved changes.",
            [
                ("cancel", "Cancel", None),
                ("discard", "Discard", DESTRUCTIVE),
                ("save", "Save", SUGGESTED),
            ],
            on_response=_chosen,
            default="save",
            close="cancel",
        )

    def _save_and_leave(self):
        if self._save():
            self._leave()

    def _leave(self):
        self.window.show_deck_list()



def _blank_icon():
    """A 1×1 transparent drag icon: the grid itself shows the movement."""
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 1, 1)
    pixbuf.fill(0x00000000)
    return Gdk.Texture.new_for_pixbuf(pixbuf)
