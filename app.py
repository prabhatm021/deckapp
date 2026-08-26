"""DeckApp — a virtual macro pad for Linux desktops."""
import logging
import os
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from deckapp import __version__  # noqa: E402
from deckapp.core import autostart  # noqa: E402
from deckapp.core.tray import MenuItem, TrayIcon  # noqa: E402
from deckapp.core import prefs  # noqa: E402
from deckapp.core.deck_store import load_all_decks  # noqa: E402
from deckapp.core.paths import (get_app_icon_dir, get_app_icon_file,  # noqa: E402
                                get_decks_dir, get_menu_play_icon)
from deckapp.ui import confirm  # noqa: E402

APP_ID = "io.github.prabhatm021.deckapp"
APP_ICON = APP_ID
# A deck row in the tray menu: play, in the menu's own icon slot. Sent as raw
# PNG so the shell cannot recolour it the way it recolours *-symbolic names.
DECK_MENU_ICON = "media-playback-start-symbolic"

GLib.set_prgname("deckapp")
GLib.set_application_name("DeckApp")

logger = logging.getLogger("deckapp")

SHORTCUTS = [
    ("Ctrl+N", "New deck"),
    ("Ctrl+S", "Save changes"),
    ("Esc", "Go back"),
    ("Ctrl+Q", "Quit"),
]


class DeckApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE,
        )
        self.window = None
        self.add_main_option(
            "deck", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.STRING,
            "Open this deck as a pad window", "NAME",
        )
        self.add_main_option(
            "list", ord("l"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            "List deck names and exit", None,
        )
        self.add_main_option(
            "tray", ord("t"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE,
            "Run in the background with a tray icon", None,
        )
        self.tray = None
        self._held = False
        self.pads = {}            # deck_id -> PadWindow
        self._pad_listeners = []

    # ── Lifecycle ──

    def do_startup(self):
        Adw.Application.do_startup(self)
        self._install_icon()
        self._install_actions()

    @staticmethod
    def _install_icon():
        """Make DeckApp's own icon findable by name, without installing it."""
        display = Gdk.Display.get_default()
        if display is not None:
            theme = Gtk.IconTheme.get_for_display(display)
            theme.add_search_path(str(get_app_icon_dir()))
        Gtk.Window.set_default_icon_name(APP_ICON)

    def do_activate(self):
        # The tray is a saved preference, not something only --tray turns on
        if prefs.get_run_in_background() and self.tray is None:
            self.start_tray()

        if self.window is None:
            from deckapp.ui.main_window import MainWindow
            self.window = MainWindow(self)
            # GTK4 has no ::destroy signal — watch the close request instead,
            # and only drop the reference if the close actually went through
            # (MainWindow vetoes it while there are unsaved edits).
            self.window.connect("close-request", self._on_window_close_request)
        self.window.present()

    def _on_window_close_request(self, *_args):
        GLib.idle_add(self._forget_closed_window)
        return False

    def _forget_closed_window(self):
        if self.window is not None and not self.window.get_visible():
            self.window = None
        return GLib.SOURCE_REMOVE

    # ── Command line ──

    @staticmethod
    def _emit(command_line, text, error=False):
        """Write to the invoking terminal (GLib < 2.80 has no *_literal)."""
        method = "printerr_literal" if error else "print_literal"
        printer = getattr(command_line, method, None)
        if printer is not None:
            printer(text)
        else:
            (sys.stderr if error else sys.stdout).write(text)

    def do_command_line(self, command_line):
        options = command_line.get_options_dict().end().unpack()

        if options.get("list"):
            decks, _errors = load_all_decks()
            for deck in decks:
                self._emit(command_line, f"{deck.deck_id}\t{deck.name}\n")
            return 0

        if options.get("tray"):
            if not self.start_tray():
                self._emit(command_line,
                           "deckapp: no tray host available\n", error=True)
                return 1
            prefs.set_run_in_background(True)
            return 0

        wanted = options.get("deck")
        if wanted:
            if not self.open_pad_by_name(wanted):
                self._emit(command_line,
                           f"deckapp: no deck matching “{wanted}”\n", error=True)
                return 1
            return 0

        self.activate()
        return 0

    def open_pad_by_name(self, wanted) -> bool:
        """Open a deck as a pad, matched on id, file name or display name."""
        decks, _errors = load_all_decks()
        wanted_key = wanted.strip().lower()
        match = next(
            (d for d in decks
             if wanted_key in (d.deck_id.lower(), d.name.lower(),
                               d.path.stem.lower() if d.path else "")),
            None,
        )
        if match is None:
            return False
        self.open_pad(match)
        return True

    # ── Notifications ──

    def notify(self, title, body, ident=None):
        """A real desktop notification, so failures land in the shell's
        notification centre instead of a toast that disappears.

        Always DeckApp's own icon: a notification identifies the application
        that sent it, not the individual button.
        """
        notification = Gio.Notification.new(title)
        if body:
            notification.set_body(body)
        notification.set_priority(Gio.NotificationPriority.NORMAL)
        # A FileIcon, not a ThemedIcon: the shell resolves themed names against
        # its own icon theme, which knows nothing about a source checkout.
        icon_file = get_app_icon_file()
        try:
            if icon_file.is_file():
                notification.set_icon(
                    Gio.FileIcon.new(Gio.File.new_for_path(str(icon_file)))
                )
            else:
                notification.set_icon(Gio.ThemedIcon.new(APP_ICON))
        except Exception:      # pragma: no cover - icon lookup is best effort
            pass
        self.send_notification(ident or "deckapp-command", notification)

    # ── Tray ──

    def start_tray(self) -> bool:
        """Run in the background: an icon in the top bar, no window."""
        if self.tray is not None:
            return True

        self.tray = TrayIcon(
            app_id="deckapp",
            title="DeckApp",
            icon_name=APP_ICON,
            icon_theme_path=str(get_app_icon_dir()),
            build_menu=self._build_tray_menu,
            on_activate=self._on_tray_clicked,
        )
        if not self.tray.start():
            self.tray = None
            return False

        if not self._held:
            # Keep running with every window closed — only Quit ends it
            self.hold()
            self._held = True
        self._sync_background_action()
        return True

    def stop_tray(self):
        if self.tray is not None:
            self.tray.stop()
            self.tray = None
        if self._held:
            self.release()
            self._held = False
        self._sync_background_action()

    def tray_running(self) -> bool:
        return self.tray is not None

    def _sync_background_action(self):
        """Keep an open Preferences window in step with the tray state."""
        for window in self.get_windows():
            loader = getattr(window, "_load", None)
            if callable(loader) and hasattr(window, "background_switch"):
                loader()

    def _build_tray_menu(self):
        decks, _errors = load_all_decks()
        decks = prefs.apply_deck_order(decks)
        play_png = get_menu_play_icon()

        items = []
        for index, deck in enumerate(decks, start=1):
            items.append(MenuItem(
                index, deck.name,
                on_click=lambda d=deck: self._open_pad(d),
                icon_name=None if play_png else DECK_MENU_ICON,
                icon_data=play_png,
            ))

        if not decks:
            items.append(MenuItem(1, "No decks yet", enabled=False))

        next_id = len(items) + 1
        items.append(MenuItem(next_id, "", separator=True))
        items.append(MenuItem(next_id + 1, "Open DeckApp",
                              on_click=self._on_tray_clicked))
        items.append(MenuItem(next_id + 2, "Quit DeckApp",
                              on_click=self.quit_everything))
        return items

    def _open_pad(self, deck):
        self.open_pad(deck)
        return GLib.SOURCE_REMOVE

    # ── Open pads ──

    def open_pad(self, deck):
        """Open a deck as a pad, or raise the one already open for it."""
        from deckapp.ui.pad_window import PadWindow

        existing = self.pads.get(deck.deck_id)
        if existing is not None:
            existing.present()
            return existing

        pad = PadWindow(self, deck)
        self.pads[deck.deck_id] = pad
        # A pad never vetoes its close, so close-request means it is going
        pad.connect("close-request",
                    lambda *_, d=deck.deck_id: self._forget_pad(d) or False)
        pad.present()
        self._notify_pads()
        return pad

    def reload_pad(self, deck):
        """Push edited deck contents into an open pad, if there is one."""
        pad = self.pads.get(deck.deck_id)
        if pad is not None:
            pad.reload(deck)

    def close_pad(self, deck_id):
        pad = self.pads.get(deck_id)
        if pad is not None:
            pad.close()

    def is_pad_open(self, deck_id) -> bool:
        return deck_id in self.pads

    def add_pad_listener(self, callback):
        self._pad_listeners.append(callback)

    def remove_pad_listener(self, callback):
        if callback in self._pad_listeners:
            self._pad_listeners.remove(callback)

    def _forget_pad(self, deck_id):
        self.pads.pop(deck_id, None)
        self._notify_pads()
        return False

    def _notify_pads(self):
        for callback in list(self._pad_listeners):
            callback()

    def _on_tray_clicked(self):
        self.activate()
        return GLib.SOURCE_REMOVE

    def quit_everything(self):
        """Close every pad, the manager, and the tray icon itself."""
        page = getattr(self.window, "current_page", lambda: None)()
        if getattr(page, "is_dirty", lambda: False)():
            self.window.present()
            confirm(
                self.window,
                "Unsaved changes",
                f"“{page.deck.name}” has unsaved changes.",
                "Discard & Quit",
                self._quit_now,
                destructive=True,
                cancel_label="Keep Editing",
            )
            return GLib.SOURCE_REMOVE
        return self._quit_now()

    def _quit_now(self):
        for window in list(self.get_windows()):
            window.destroy()
        self.stop_tray()
        self.quit()
        return GLib.SOURCE_REMOVE

    # ── Actions ──

    def _install_actions(self):
        entries = {
            "quit": self._on_quit,
            "about": self._on_about,
            "shortcuts": self._on_shortcuts,
            "open-folder": self._on_open_folder,
            "preferences": self._on_preferences,
        }
        for name, handler in entries.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda *_a, h=handler: h())
            self.add_action(action)

        for action, accels in (
            ("app.quit", ["<Control>q"]),
            ("app.preferences", ["<Control>comma"]),
            ("win.back", ["Escape"]),
            ("win.save", ["<Control>s"]),
            ("win.primary", ["<Control>n"]),
        ):
            self.set_accels_for_action(action, accels)

    def _on_quit(self):
        if self.window is not None:
            # Route through the window so unsaved edits are not lost silently
            self.window.close()
        if self.tray is None:
            self.quit()

    def _on_preferences(self):
        from deckapp.ui.preferences import PreferencesWindow
        if self.window is None:
            self.activate()
        PreferencesWindow(self).present()

    def _on_about(self):
        about_cls = getattr(Adw, "AboutWindow", None)
        if about_cls is not None:
            about = about_cls(
                transient_for=self.window,
                application_name="DeckApp",
                application_icon=APP_ICON,
                version=__version__,
                developer_name="prabhatm021",
                license_type=Gtk.License.MIT_X11,
                comments="A virtual macro pad: grids of buttons that run shell commands.",
                website="https://github.com/prabhatm021/deckapp",
                issue_url="https://github.com/prabhatm021/deckapp/issues",
            )
            about.present()
            return

        about = Gtk.AboutDialog(transient_for=self.window, modal=True)
        about.set_program_name("DeckApp")
        about.set_version(__version__)
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_comments("A virtual macro pad for Linux.")
        about.present()

    def _on_shortcuts(self):
        window = Gtk.Window(transient_for=self.window, modal=True)
        window.set_title("Keyboard Shortcuts")
        window.set_default_size(340, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_margin_top(18)
        box.set_margin_bottom(18)
        box.set_margin_start(18)
        box.set_margin_end(18)

        group = Adw.PreferencesGroup()
        for keys, description in SHORTCUTS:
            row = Adw.ActionRow()
            row.set_title(description)
            shortcut = Gtk.Label(label=keys)
            shortcut.add_css_class("dim-label")
            shortcut.add_css_class("monospace")
            shortcut.set_valign(Gtk.Align.CENTER)
            row.add_suffix(shortcut)
            group.add(row)
        box.append(group)
        window.set_child(box)
        window.present()

    def _on_open_folder(self):
        uri = get_decks_dir().as_uri()
        try:
            Gtk.show_uri(self.window, uri, 0)
        except Exception as e:  # pragma: no cover - depends on the desktop
            logger.warning("Could not open %s: %s — decks are in %s",
                           uri, e, get_decks_dir())


def main():
    logging.basicConfig(
        level=logging.DEBUG if os.environ.get("DECKAPP_DEBUG") else logging.INFO,
        format="[deckapp] %(levelname)s %(name)s: %(message)s",
    )
    app = DeckApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
