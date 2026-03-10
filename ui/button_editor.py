import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib
from pathlib import Path

from deckapp.ui import load_css


class ButtonEditor(Gtk.Dialog):
    DELETE_RESPONSE = 1001

    def __init__(self, parent, title="Button Editor", button_data=None):
        super().__init__(title=title, transient_for=parent, modal=True)

        load_css()
        self.set_default_size(440, -1)
        self.icon_path = None

        content = self.get_content_area()
        content.set_spacing(0)

        # Use a boxed-list for the form fields (Adwaita pattern)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_margin_top(12)
        box.set_margin_bottom(0)
        box.set_margin_start(16)
        box.set_margin_end(16)
        content.append(box)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        listbox.add_css_class("boxed-list")
        box.append(listbox)

        # ── Label ──
        self.label_row = Adw.EntryRow()
        self.label_row.set_title("Label")
        listbox.append(self.label_row)

        # ── Behavior ──
        self.behavior_row = Adw.ComboRow()
        self.behavior_row.set_title("Behavior")
        behavior_model = Gtk.StringList.new(["single", "toggle"])
        self.behavior_row.set_model(behavior_model)
        self.behavior_row.connect("notify::selected", self._on_behavior_changed)
        listbox.append(self.behavior_row)

        # ── Single command ──
        self.command_row = Adw.EntryRow()
        self.command_row.set_title("Command")
        listbox.append(self.command_row)

        # ── Toggle fields ──
        self.on_row = Adw.EntryRow()
        self.on_row.set_title("ON Command")
        listbox.append(self.on_row)

        self.off_row = Adw.EntryRow()
        self.off_row.set_title("OFF Command")
        listbox.append(self.off_row)

        self.state_row = Adw.ComboRow()
        self.state_row.set_title("Default State")
        self.state_row.set_model(Gtk.StringList.new(["off", "on"]))
        listbox.append(self.state_row)

        # ── Icon ──
        self.icon_row = Adw.ActionRow()
        self.icon_row.set_title("Icon")

        choose_btn = Gtk.Button(label="Choose…")
        choose_btn.add_css_class("flat")
        choose_btn.set_valign(Gtk.Align.CENTER)
        choose_btn.connect("clicked", self.on_choose_icon)
        self.icon_row.add_suffix(choose_btn)

        self.icon_preview = Gtk.Image()
        self.icon_preview.set_pixel_size(32)
        self.icon_preview.set_valign(Gtk.Align.CENTER)
        self.icon_row.add_suffix(self.icon_preview)

        listbox.append(self.icon_row)

        # ── Dialog action buttons ──
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)

        if button_data:
            del_btn = self.add_button("Delete", self.DELETE_RESPONSE)
            del_btn.add_css_class("destructive-action")

        ok_btn = self.add_button("Save", Gtk.ResponseType.OK)
        ok_btn.add_css_class("suggested-action")

        # ── Pre-fill ──
        if button_data:
            self.label_row.set_text(button_data.get("label", ""))

            behavior = button_data.get("behavior", "single")
            self.behavior_row.set_selected(1 if behavior == "toggle" else 0)

            if behavior == "single":
                self.command_row.set_text(button_data.get("command", ""))
            else:
                self.on_row.set_text(button_data.get("on_command", ""))
                self.off_row.set_text(button_data.get("off_command", ""))
                self.state_row.set_selected(1 if button_data.get("state", "off") == "on" else 0)

            icon = button_data.get("icon")
            if icon and Path(icon).exists():
                self.icon_path = icon
                self.icon_preview.set_from_file(icon)

        self._update_visibility()

    # ── Behavior visibility ──

    def _on_behavior_changed(self, combo, param):
        self._update_visibility()

    def _update_visibility(self):
        is_toggle = self.behavior_row.get_selected() == 1
        self.command_row.set_visible(not is_toggle)
        self.on_row.set_visible(is_toggle)
        self.off_row.set_visible(is_toggle)
        self.state_row.set_visible(is_toggle)

    # ── Icon picker ──

    def on_choose_icon(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Choose Icon",
            transient_for=self,
            modal=True,
            action=Gtk.FileChooserAction.OPEN,
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Open", Gtk.ResponseType.OK)
        dialog.connect("response", self._on_icon_chosen)
        dialog.present()

    def _on_icon_chosen(self, dialog, response):
        if response == Gtk.ResponseType.OK:
            f = dialog.get_file()
            if f:
                path = f.get_path()
                if path:
                    self.icon_path = path
                    self.icon_preview.set_from_file(path)
        dialog.close()

    # ── Export ──

    def get_data(self):
        is_toggle = self.behavior_row.get_selected() == 1
        behavior = "toggle" if is_toggle else "single"

        data = {
            "label": self.label_row.get_text(),
            "behavior": behavior,
            "icon": self.icon_path,
        }

        if behavior == "single":
            data["command"] = self.command_row.get_text()
        else:
            data["on_command"] = self.on_row.get_text()
            data["off_command"] = self.off_row.get_text()
            data["state"] = "on" if self.state_row.get_selected() == 1 else "off"

        return data
