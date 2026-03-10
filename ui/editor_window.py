import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw

import shutil
import uuid
from pathlib import Path

from deckapp.core.deck_loader import Button
from deckapp.core.deck_saver import save_deck
from deckapp.core.paths import get_icons_dir
from deckapp.ui.button_editor import ButtonEditor
from deckapp.ui import load_css


class EditorWindow(Adw.ApplicationWindow):
    def __init__(self, app, deck):
        super().__init__(application=app)
        self.deck = deck
        self.app = app
        self._dirty = False

        load_css()
        self.set_title(f"Edit – {deck.deck_name}")
        self.set_default_size(
            max(500, deck.cols * 100 + 40),
            max(460, deck.rows * 100 + 80),
        )

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="Edit", subtitle=deck.deck_name))

        back_btn = Gtk.Button(label="Done")
        back_btn.set_icon_name("go-previous-symbolic")
        back_btn.connect("clicked", self.on_done_clicked)
        header.pack_start(back_btn)

        self.save_btn = Gtk.Button(label="Save")
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.connect("clicked", self.on_save_clicked)
        header.pack_end(self.save_btn)

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

        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_child(outer)
        self.set_content(self.toast_overlay)
        self.build_grid()

    # ── Dirty tracking ──

    def _mark_dirty(self):
        self._dirty = True

    # ── Grid ──

    def build_grid(self):
        for row in range(self.deck.rows):
            for col in range(self.deck.cols):
                pos = (row, col)

                if pos in self.deck.buttons:
                    btn = self.deck.buttons[pos]
                    widget = Gtk.Button()
                    widget.add_css_class("deck-btn")
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
                    widget.connect("clicked", lambda w, b=btn: self.on_edit_clicked(b))
                else:
                    widget = Gtk.Button(label="+")
                    widget.add_css_class("deck-btn")
                    widget.add_css_class("empty")
                    widget.connect("clicked", lambda w, r=row, c=col: self.on_add_clicked(r, c))

                self.grid.attach(widget, col, row, 1, 1)

    def refresh_grid(self):
        child = self.grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.grid.remove(child)
            child = nxt
        self.build_grid()

    # ── Icon storage ──

    def store_icon(self, source_path):
        icons_dir = get_icons_dir()
        ext = Path(source_path).suffix
        filename = f"{uuid.uuid4().hex}{ext}"
        shutil.copy(source_path, icons_dir / filename)
        return f"icons/{filename}"

    # ── Add button ──

    def on_add_clicked(self, row, col):
        dialog = ButtonEditor(self, title=f"Add Button ({row}, {col})")
        dialog.connect("response", self.on_add_response, row, col)
        dialog.present()

    def on_add_response(self, dialog, response, row, col):
        if response == Gtk.ResponseType.OK:
            data = dialog.get_data()
            button_data = {"label": data["label"], "behavior": data["behavior"]}

            if data.get("icon"):
                button_data["icon"] = self.store_icon(data["icon"])

            if data["behavior"] == "single":
                button_data["command"] = data["command"]
            else:
                button_data["state"] = data["state"]
                button_data["on"] = {"command": data["on_command"]}
                button_data["off"] = {"command": data["off_command"]}

            self.deck.buttons[(row, col)] = Button(row, col, button_data)
            self._mark_dirty()
            self.refresh_grid()

        dialog.close()

    # ── Edit button ──

    def on_edit_clicked(self, button):
        data = {"label": button.label, "behavior": button.behavior, "icon": getattr(button, "icon", None)}

        if button.behavior == "single":
            data["command"] = button.command
        else:
            data["on_command"] = button.on_command
            data["off_command"] = button.off_command
            data["state"] = button.state

        dialog = ButtonEditor(self, title="Edit Button", button_data=data)
        dialog.connect("response", self.on_edit_response, button)
        dialog.present()

    def on_edit_response(self, dialog, response, button):
        if response == Gtk.ResponseType.OK:
            data = dialog.get_data()
            button.label = data["label"]
            button.behavior = data["behavior"]

            if data.get("icon"):
                button.icon = self.store_icon(data["icon"])

            if data["behavior"] == "single":
                button.command = data["command"]
            else:
                button.on_command = data["on_command"]
                button.off_command = data["off_command"]
                button.state = data["state"]

            self._mark_dirty()
            self.refresh_grid()

        elif response == ButtonEditor.DELETE_RESPONSE:
            pos_to_delete = next((p for p, b in self.deck.buttons.items() if b is button), None)
            if pos_to_delete:
                del self.deck.buttons[pos_to_delete]
                self._mark_dirty()
                self.refresh_grid()

        dialog.close()

    # ── Save ──

    def on_save_clicked(self, widget):
        save_deck(self.deck, self.deck.path)
        self._dirty = False

        toast = Adw.Toast(title=f'"{self.deck.deck_name}" saved')
        toast.set_timeout(2)
        self.toast_overlay.add_toast(toast)

    # ── Done ──

    def on_done_clicked(self, widget):
        if self._dirty:
            self._confirm_discard()
        else:
            self._go_back()

    def _confirm_discard(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Unsaved changes",
            body="You have unsaved changes. Save before leaving?",
        )
        dialog.add_response("discard", "Discard")
        dialog.add_response("save", "Save & Done")
        dialog.set_response_appearance("discard", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_response_appearance("save", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("save")
        dialog.set_close_response("discard")
        dialog.connect("response", self._on_discard_response)
        dialog.present()

    def _on_discard_response(self, dialog, response):
        if response == "save":
            save_deck(self.deck, self.deck.path)
            self._dirty = False
        self._go_back()

    def _go_back(self):
        from deckapp.ui.layout_window import LayoutWindow
        LayoutWindow(self.app, self.deck).present()
        self.close()
