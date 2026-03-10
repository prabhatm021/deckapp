import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib

from deckapp.core.state_manager import StateManager
from deckapp.ui import load_css

_FLASH_MS = 200  # how long the single-click highlight stays on


class LayoutWindow(Adw.ApplicationWindow):
    def __init__(self, app, deck):
        super().__init__(application=app)
        self.app = app
        self.deck = deck

        self.state_manager = StateManager()
        load_css()
        self.set_title(deck.deck_name)
        self.set_default_size(
            max(400, deck.cols * 100 + 40),
            max(420, deck.rows * 100 + 80),
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=deck.deck_name))

        back_btn = Gtk.Button(label="Decks")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.connect("clicked", self.on_decks_clicked)
        header.pack_start(back_btn)

        edit_btn = Gtk.Button(label="Edit")
        edit_btn.connect("clicked", self.on_edit_clicked)
        header.pack_end(edit_btn)

        outer.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_hexpand(True)

        self.grid = Gtk.Grid(
            row_spacing=10,
            column_spacing=10,
            margin_top=16,
            margin_bottom=16,
            margin_start=16,
            margin_end=16,
        )
        self.grid.set_halign(Gtk.Align.CENTER)
        self.grid.set_valign(Gtk.Align.CENTER)

        scroll.set_child(self.grid)
        outer.append(scroll)

        self.set_content(outer)
        self.build_grid()

    # ── Grid ──

    def build_grid(self):
        for row in range(self.deck.rows):
            for col in range(self.deck.cols):
                pos = (row, col)

                if pos in self.deck.buttons:
                    btn = self.deck.buttons[pos]
                    widget = Gtk.Button()
                    widget.add_css_class("deck-btn")

                    # Restore persisted toggle state
                    if btn.behavior == "toggle":
                        btn.state = self.state_manager.get(self.deck.deck_id, pos, btn.state)

                    if btn.behavior == "toggle" and btn.state == "on":
                        widget.add_css_class("suggested-action")

                    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
                    box.set_halign(Gtk.Align.CENTER)
                    box.set_valign(Gtk.Align.CENTER)

                    if btn.icon:
                        image = Gtk.Image.new_from_file(btn.icon)
                        image.set_pixel_size(36)
                        box.append(image)

                    if btn.label:
                        lbl = Gtk.Label(label=btn.label)
                        lbl.set_justify(Gtk.Justification.CENTER)
                        lbl.set_wrap(True)
                        lbl.set_max_width_chars(10)
                        box.append(lbl)

                    widget.set_child(box)
                    widget.connect("clicked", lambda w, b=btn: self._on_btn_clicked(w, b))
                else:
                    widget = Gtk.Button()
                    widget.add_css_class("deck-btn")
                    widget.add_css_class("empty")
                    widget.set_child(Gtk.Label(label=""))

                self.grid.attach(widget, col, row, 1, 1)

    # ── Button click with visual feedback ──

    def _on_btn_clicked(self, widget, btn):
        self.app.run_button(btn)

        if btn.behavior == "toggle":
            self.state_manager.set(self.deck.deck_id, (btn.row, btn.col), btn.state)
            if btn.state == "on":
                widget.add_css_class("suggested-action")
            else:
                widget.remove_css_class("suggested-action")
        else:
            # Single: flash accent colour for _FLASH_MS then revert
            widget.add_css_class("suggested-action")
            GLib.timeout_add(_FLASH_MS, lambda: (
                widget.remove_css_class("suggested-action"), False
            )[1])

    # ── Navigation ──

    def on_edit_clicked(self, widget):
        from deckapp.ui.editor_window import EditorWindow
        self.close()
        EditorWindow(self.app, self.deck).present()

    def on_decks_clicked(self, widget):
        from deckapp.ui.deck_selector import DeckSelector
        DeckSelector(self.app).present()
        self.close()
