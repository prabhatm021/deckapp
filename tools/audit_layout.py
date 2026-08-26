#!/usr/bin/env python3
"""Look for text that does not fit, on every screen.

    python3 tools/audit_layout.py

The smoke test checks behaviour; this checks rendering. It walks each window's
widget tree and asks Pango which labels it had to ellipsize, which is how text
that does not fit gets caught. A behavioural test cannot see that.

Widget size is deliberately not compared against get_preferred_size(): GTK
measures height for width, so those numbers do not mean what they look like.
"""
import json
import os
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = tempfile.mkdtemp(prefix="deckapp-audit-")
os.environ["DECKAPP_DATA_DIR"] = DEMO
os.environ["XDG_CONFIG_HOME"] = os.path.join(DEMO, "config")
sys.path.insert(0, os.path.dirname(REPO))

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from deckapp.app import DeckApp  # noqa: E402
from deckapp.core import deck_store  # noqa: E402
from deckapp.core.models import Button  # noqa: E402

# Deck tiles ellipsize on purpose: a long label on a small key has to give.
INTENTIONAL = {"deck-btn"}

findings = []


def pump(seconds=0.4):
    context = GLib.MainContext.default()
    end = time.time() + seconds
    while time.time() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def _in_intentional(widget):
    node = widget
    while node is not None:
        if INTENTIONAL & set(node.get_css_classes()):
            return True
        node = node.get_parent()
    return False


def audit(window, screen):
    pump(0.5)

    def walk(widget):
        if isinstance(widget, Gtk.Label) and widget.get_mapped():
            layout = widget.get_layout()
            if layout is not None and layout.is_ellipsized():
                if not _in_intentional(widget):
                    findings.append(
                        (screen, "truncated", repr(widget.get_text()))
                    )
        child = widget.get_first_child()
        while child:
            walk(child)
            child = child.get_next_sibling()

    walk(window)


def seed():
    decks = os.path.join(DEMO, "decks")
    os.makedirs(decks, exist_ok=True)
    json.dump({"deck_id": "media", "deck_name": "Media Controls",
               "grid": {"rows": 2, "cols": 3},
               "buttons": {
                   "0,0": {"label": "Mute", "behavior": "toggle", "state": "on",
                           "on": {"command": "true"}, "off": {"command": "true"}},
                   "0,1": {"label": "Play", "behavior": "single", "command": "true"}}},
              open(os.path.join(decks, "media.json"), "w"))
    json.dump({"deck_id": "long", "deck_name": "A deck with a very long name here",
               "grid": {"rows": 1, "cols": 1}, "buttons": {}},
              open(os.path.join(decks, "long.json"), "w"))


class Audit(DeckApp):
    def do_activate(self):
        from deckapp.ui.button_editor import ButtonEditor
        from deckapp.ui.deck_dialog import DeckCreateDialog, DeckPropertiesDialog
        from deckapp.ui.main_window import MainWindow
        from deckapp.ui.pad_window import PadWindow
        from deckapp.ui.preferences import PreferencesWindow

        try:
            seed()
            window = MainWindow(self)
            window.present()
            audit(window, "deck list")

            page = window.current_page()
            page._set_reorder_mode(True)
            audit(window, "deck list, reordering")
            page._set_reorder_mode(False)

            deck = deck_store.load_deck(os.path.join(DEMO, "decks", "media.json"))
            pad = self.open_pad(deck)
            audit(pad, "pad")

            window.edit_deck(deck)
            audit(window, "editor")

            long_command = ("gsettings set org.gnome.settings-daemon.plugins."
                            "color night-light-enabled true")
            for label, behavior in (("Single", "single"), ("Toggle", "toggle")):
                dialog = ButtonEditor(
                    window, "Edit Button", subtitle="Row 2, column 1",
                    button=Button(1, 0, label="Night Light", behavior=behavior,
                                  command=long_command,
                                  on_command=long_command,
                                  off_command=long_command),
                    on_save=lambda d: None, on_delete=lambda: None)
                dialog.set_default_size(480, -1)
                dialog.present()
                audit(dialog, f"button editor, {label.lower()}")
                dialog.destroy()

            for name, dialog in (
                ("new deck", DeckCreateDialog(window)),
                ("deck properties", DeckPropertiesDialog(window, deck)),
                ("preferences", PreferencesWindow(self)),
            ):
                dialog.present()
                audit(dialog, name)
                dialog.destroy()

            self._on_shortcuts()
            pump(0.4)
            for extra in Gtk.Window.list_toplevels():
                if extra.get_visible() and extra.get_title() == "Keyboard Shortcuts":
                    audit(extra, "shortcuts")
                    extra.destroy()

            pad.destroy()
            window.destroy()
        finally:
            GLib.idle_add(self.quit)


if __name__ == "__main__":
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    app = Audit()
    app.set_application_id("io.github.prabhatm021.deckapp.audit")
    app.run([])

    if not findings:
        print("no truncated or clipped text on any screen")
    else:
        print(f"{len(findings)} problems:\n")
        for screen, kind, detail in findings:
            print(f"  {screen:26} {kind:11} {detail}")
        sys.exit(1)
