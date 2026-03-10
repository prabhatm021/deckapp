import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gio, Adw, GLib

GLib.set_prgname("deckapp")
GLib.set_application_name("DeckApp")

from deckapp.core.command_runner import run_command
from deckapp.ui.deck_selector import DeckSelector


class DeckApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.prabhatm021.deckapp", flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = DeckSelector(self)
        win.present()

    def run_button(self, button):
        if button.behavior == "single":
            if button.command:
                run_command(button.command)

        elif button.behavior == "toggle":
            if button.state == "off":
                if button.on_command:
                    run_command(button.on_command)
                button.state = "on"
            else:
                if button.off_command:
                    run_command(button.off_command)
                button.state = "off"


def main():
    app = DeckApp()
    app.run(None)


if __name__ == "__main__":
    main()
