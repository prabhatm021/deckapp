"""Dialog for creating and editing a single deck button."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from deckapp.core.command_runner import run_command
from deckapp.core.icons import IconError, import_icon, looks_opaque
from deckapp.core.models import MAX_LABEL_LEN, SINGLE, TOGGLE
from deckapp.core.paths import resolve_asset
from deckapp.ui import choose_image, confirm, show_error

BEHAVIOR_LABELS = ["Single", "Toggle"]
BEHAVIOR_HINTS = [
    "Runs one command each time it is pressed.",
    "Alternates between an ON and an OFF command.",
]


class ButtonEditor(Adw.Window):
    def __init__(self, window, title="Button", subtitle="", button=None,
                 on_save=None, on_delete=None):
        super().__init__(transient_for=window, modal=True)
        self.window = window
        self.on_save = on_save
        self.on_delete = on_delete
        self.icon = button.icon if button else None

        self.set_title(title)
        self.set_default_size(460, -1)
        self.set_hide_on_close(False)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        header.set_title_widget(Adw.WindowTitle(title=title, subtitle=subtitle))

        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", lambda *_: self.close())
        header.pack_start(cancel_btn)

        save_btn = Gtk.Button(label="Save")
        save_btn.add_css_class("suggested-action")
        save_btn.connect("clicked", lambda *_: self._save())
        header.pack_end(save_btn)
        outer.append(header)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_propagate_natural_height(True)
        scroll.set_vexpand(True)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        body.set_margin_top(18)
        body.set_margin_bottom(18)
        body.set_margin_start(18)
        body.set_margin_end(18)

        body.append(self._build_basics_group())
        body.append(self._build_command_group())
        body.append(self._build_icon_group())

        if button is not None and on_delete is not None:
            delete_btn = Gtk.Button(label="Remove Button")
            delete_btn.add_css_class("destructive-action")
            delete_btn.set_halign(Gtk.Align.CENTER)
            delete_btn.connect("clicked", lambda *_: self._confirm_delete())
            body.append(delete_btn)

        scroll.set_child(body)
        outer.append(scroll)
        self.set_content(outer)

        if button is not None:
            self._load(button)
        self._update_visibility()
        self._install_keys()

    # ── Form ──

    def _build_basics_group(self):
        group = Adw.PreferencesGroup()

        self.label_row = Adw.EntryRow()
        self.label_row.set_title("Label")
        group.add(self.label_row)

        self.behavior_row = Adw.ComboRow()
        self.behavior_row.set_title("Behaviour")
        self.behavior_row.set_model(Gtk.StringList.new(BEHAVIOR_LABELS))
        self.behavior_row.set_subtitle(BEHAVIOR_HINTS[0])
        self.behavior_row.connect(
            "notify::selected", lambda *_: self._update_visibility()
        )
        group.add(self.behavior_row)
        return group

    def _build_command_group(self):
        group = Adw.PreferencesGroup()
        group.set_title("Command")
        group.set_description("Exactly as you would type it in a terminal.")

        self.command_row = Adw.EntryRow()
        self.command_row.set_title("Command")
        self.command_row.add_suffix(self._test_button(lambda: self.command_row))
        group.add(self.command_row)

        self.on_row = Adw.EntryRow()
        self.on_row.set_title("Turn ON command")
        self.on_row.add_suffix(self._test_button(lambda: self.on_row))
        group.add(self.on_row)

        self.off_row = Adw.EntryRow()
        self.off_row.set_title("Turn OFF command")
        self.off_row.add_suffix(self._test_button(lambda: self.off_row))
        group.add(self.off_row)

        self.state_row = Adw.ComboRow()
        self.state_row.set_title("Starts as")
        self.state_row.set_model(Gtk.StringList.new(["OFF", "ON"]))
        group.add(self.state_row)
        return group

    def _test_button(self, get_row):
        button = Gtk.Button()
        button.set_icon_name("media-playback-start-symbolic")
        button.add_css_class("flat")
        button.set_valign(Gtk.Align.CENTER)
        button.set_tooltip_text("Test this command now")
        # Never take the keyboard focus: it sits right where the caret ends up
        # in a long command, and Tab used to land here instead of the next
        # field — both kicked you out of the entry mid-edit.
        button.set_can_focus(False)
        button.set_focus_on_click(False)
        button.connect("clicked", lambda *_: self._test(get_row().get_text()))
        return button

    def _build_icon_group(self):
        group = Adw.PreferencesGroup()
        group.set_title("Icon")
        group.set_description(
            "Optional. Use a PNG with a transparent background."
        )

        self.icon_row = Adw.ActionRow()
        self.icon_row.set_title("Image")
        self.icon_row.set_subtitle("None")

        self.icon_preview = Gtk.Image()
        self.icon_preview.set_pixel_size(32)
        self.icon_preview.set_valign(Gtk.Align.CENTER)
        self.icon_row.add_prefix(self.icon_preview)

        self.remove_icon_btn = Gtk.Button()
        self.remove_icon_btn.set_icon_name("edit-clear-symbolic")
        self.remove_icon_btn.add_css_class("flat")
        self.remove_icon_btn.set_valign(Gtk.Align.CENTER)
        self.remove_icon_btn.set_tooltip_text("Remove icon")
        self.remove_icon_btn.connect("clicked", lambda *_: self._set_icon(None))
        self.icon_row.add_suffix(self.remove_icon_btn)

        choose_btn = Gtk.Button(label="Choose…")
        choose_btn.set_valign(Gtk.Align.CENTER)
        choose_btn.connect("clicked", lambda *_: self._choose_icon())
        self.icon_row.add_suffix(choose_btn)

        group.add(self.icon_row)

        # Stays on screen while an opaque image is selected, unlike a toast
        self.icon_warning = Gtk.Label()
        self.icon_warning.set_wrap(True)
        self.icon_warning.set_xalign(0)
        self.icon_warning.set_margin_top(6)
        self.icon_warning.set_margin_start(4)
        self.icon_warning.add_css_class("warning")
        self.icon_warning.add_css_class("caption")
        self.icon_warning.set_visible(False)
        group.add(self.icon_warning)
        return group

    def _install_keys(self):
        keys = Gtk.EventControllerKey()

        def _pressed(_controller, keyval, _keycode, state):
            if keyval == Gdk.KEY_Escape:
                self.close()
                return True
            if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and (
                state & Gdk.ModifierType.CONTROL_MASK
            ):
                self._save()
                return True
            return False

        keys.connect("key-pressed", _pressed)
        self.add_controller(keys)

    # ── State ──

    def _is_toggle(self):
        return self.behavior_row.get_selected() == 1

    def _update_visibility(self):
        toggle = self._is_toggle()
        self.behavior_row.set_subtitle(BEHAVIOR_HINTS[1 if toggle else 0])
        self.command_row.set_visible(not toggle)
        self.on_row.set_visible(toggle)
        self.off_row.set_visible(toggle)
        self.state_row.set_visible(toggle)

    def _load(self, button):
        self.label_row.set_text(button.label)
        self.behavior_row.set_selected(1 if button.is_toggle else 0)
        self.command_row.set_text(button.command)
        self.on_row.set_text(button.on_command)
        self.off_row.set_text(button.off_command)
        self.state_row.set_selected(1 if button.state == "on" else 0)
        self._set_icon(button.icon)

    def _set_icon(self, relative):
        self.icon = relative
        if relative:
            self.icon_preview.set_from_file(resolve_asset(relative))
            self.icon_row.set_subtitle(relative.split("/")[-1])
            self.remove_icon_btn.set_visible(True)
            opaque = looks_opaque(relative)
            self.icon_warning.set_label(
                "This image has no transparent areas, so it shows as a "
                "rectangle on the button. Export a cut-out PNG rather than a "
                "screenshot of one."
            )
            self.icon_warning.set_visible(opaque)
        else:
            self.icon_preview.set_from_icon_name("image-x-generic-symbolic")
            self.icon_row.set_subtitle("None")
            self.remove_icon_btn.set_visible(False)
            self.icon_warning.set_visible(False)

    # ── Actions ──

    def _choose_icon(self):
        def _chosen(path):
            try:
                relative = import_icon(path)
            except IconError as e:
                show_error(self, "Could not use that image", str(e))
                return

            self._set_icon(relative)

        choose_image(self, _chosen)

    def _test(self, command):
        if not (command or "").strip():
            return
        app = self.window.get_application()
        run_command(
            command,
            on_error=lambda message: app.notify(
                "Test command failed", message, ident="deckapp-test"
            ) if hasattr(app, "notify") else None,
        )

    def _confirm_delete(self):
        def _delete():
            if self.on_delete:
                self.on_delete()
            self.close()

        confirm(
            self,
            "Remove this button?",
            "The button will be removed from the grid.",
            "Remove",
            _delete,
        )

    def _save(self):
        toggle = self._is_toggle()
        data = {
            "label": self.label_row.get_text().strip()[:MAX_LABEL_LEN],
            "behavior": TOGGLE if toggle else SINGLE,
            # Keep every field: switching behaviour back and forth in one
            # session should not throw away what was already typed.
            "command": self.command_row.get_text().strip(),
            "on_command": self.on_row.get_text().strip(),
            "off_command": self.off_row.get_text().strip(),
            "state": "on" if self.state_row.get_selected() == 1 else "off",
            "icon": self.icon,
        }
        if self.on_save:
            self.on_save(data)
        self.close()
