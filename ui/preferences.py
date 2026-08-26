"""Preferences — how DeckApp behaves when its window is closed."""
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from deckapp.core import autostart, prefs


class PreferencesWindow(Adw.PreferencesWindow):
    def __init__(self, app):
        super().__init__(transient_for=app.window, modal=True)
        self.app = app
        self._syncing = False

        self.set_title("Preferences")
        self.set_default_size(400, 330)
        self.set_search_enabled(False)

        page = Adw.PreferencesPage()
        page.set_title("General")

        group = Adw.PreferencesGroup()
        group.set_title("Background")

        self.background_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.background_row = self._switch_row(
            "Run in background", self.background_switch
        )
        group.add(self.background_row)

        self.login_switch = Gtk.Switch(valign=Gtk.Align.CENTER)
        self.login_row = self._switch_row(
            "Start on login", self.login_switch
        )
        group.add(self.login_row)

        page.add(group)
        self.add(page)

        self._load()
        self.background_switch.connect("notify::active", self._on_background)
        self.login_switch.connect("notify::active", self._on_login)

    def _switch_row(self, title, switch):
        row = Adw.ActionRow()
        row.set_title(title)
        row.add_suffix(switch)
        row.set_activatable_widget(switch)
        return row

    def _load(self):
        self._syncing = True
        self.background_switch.set_active(self.app.tray_running())
        self.login_switch.set_active(autostart.is_enabled())
        self.login_row.set_sensitive(self.app.tray_running())
        self._syncing = False

    # ── Switches ──

    def _on_background(self, switch, _param):
        if self._syncing:
            return

        prefs.set_run_in_background(switch.get_active())

        if switch.get_active():
            if not self.app.start_tray():
                self._syncing = True
                switch.set_active(False)
                self._syncing = False
                prefs.set_run_in_background(False)
                self._warn_no_tray()
                return
        else:
            self.app.stop_tray()
            if autostart.is_enabled():
                # Starting on login makes no sense without the background icon
                autostart.set_enabled(False)

        self._load()

    def _on_login(self, switch, _param):
        if self._syncing:
            return
        autostart.set_enabled(switch.get_active())
        self._load()

    def _warn_no_tray(self):
        from deckapp.ui import show_error
        show_error(
            self,
            "No place for the icon",
            "GNOME needs the AppIndicator extension:\n"
            "sudo apt install gnome-shell-extension-appindicator",
        )
