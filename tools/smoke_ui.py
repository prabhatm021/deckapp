#!/usr/bin/env python3
"""Build and drive every DeckApp screen, reporting anything that breaks.

    python3 tools/smoke_ui.py

Uses a throwaway data directory, so your real decks are untouched. Needs a
display; nothing is left on screen when it finishes.
"""
import json
import os
import sys
import tempfile
import traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = tempfile.mkdtemp(prefix="deckapp-smoke-")
os.environ["DECKAPP_DATA_DIR"] = DEMO
os.environ["XDG_CONFIG_HOME"] = os.path.join(DEMO, "config")
sys.path.insert(0, os.path.dirname(REPO))

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

from deckapp.app import DeckApp  # noqa: E402
from deckapp.core import deck_store, prefs  # noqa: E402
from deckapp.core.models import Button  # noqa: E402

failures = []
checked = 0


def check(name, fn):
    global checked
    checked += 1
    try:
        fn()
        print(f"  ok   {name}")
    except Exception:
        failures.append(name)
        print(f"  FAIL {name}")
        traceback.print_exc()


def pump(seconds=0.25):
    context = GLib.MainContext.default()
    import time
    end = time.time() + seconds
    while time.time() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def seed_decks():
    decks_dir = os.path.join(DEMO, "decks")
    os.makedirs(decks_dir, exist_ok=True)
    json.dump({
        "deck_id": "media", "deck_name": "Media", "grid": {"rows": 3, "cols": 4},
        "buttons": {
            "0,0": {"label": "Mute", "behavior": "toggle", "state": "on",
                    "on": {"command": "true"}, "off": {"command": "true"}},
            "0,1": {"label": "Play", "behavior": "single", "command": "true"},
            "2,3": {"label": "Broken", "behavior": "single",
                    "command": "definitely-not-a-command"},
        },
    }, open(os.path.join(decks_dir, "media.json"), "w"), indent=2)
    json.dump({"deck_id": "empty", "deck_name": "Empty",
               "grid": {"rows": 2, "cols": 2}, "buttons": {}},
              open(os.path.join(decks_dir, "empty.json"), "w"), indent=2)
    # a deliberately broken file: the list must survive it
    with open(os.path.join(decks_dir, "broken.json"), "w") as f:
        f.write("{ not json")


class Smoke(DeckApp):
    def do_activate(self):
        from deckapp.ui.button_editor import ButtonEditor
        from deckapp.ui.deck_dialog import DeckCreateDialog, DeckPropertiesDialog
        from deckapp.ui.main_window import MainWindow
        from deckapp.ui.pad_window import PadWindow
        from deckapp.ui.preferences import PreferencesWindow

        try:
            print("deck list:")
            seed_decks()
            window = MainWindow(self)
            window.present()
            pump(0.4)
            page = window.current_page()

            check("loads decks, skipping the broken file",
                  lambda: _assert(len(page._decks) == 2, page._decks))
            check("reorder mode on",
                  lambda: page._set_reorder_mode(True) or pump(0.2))
            check("reorder swaps and persists", lambda: _reorder(page))
            check("reorder mode off",
                  lambda: page._set_reorder_mode(False) or pump(0.2))

            print("pad:")
            deck = page._decks[0] if page._decks[0].buttons else page._decks[1]
            pad = self.open_pad(deck)
            pump(0.4)
            check("pad opens", lambda: _assert(self.is_pad_open(deck.deck_id)))
            check("row shows a close button while open",
                  lambda: _assert(any("deck-row-open" in _classes(r)
                                      for r in _rows(page))))
            check("press a toggle", lambda: _press(pad, deck, toggle=True))
            check("press a single", lambda: _press(pad, deck, toggle=False))
            check("pad closes and deregisters", lambda: _close_pad(self, deck))

            print("editor:")
            window.edit_deck(deck)
            pump(0.4)
            editor = window.current_page()
            check("editor builds a tile per cell",
                  lambda: _assert(len(editor._tiles) == deck.rows * deck.cols))
            check("add a button", lambda: editor._apply_new(1, 1, {
                "label": "New", "behavior": "single", "command": "true",
                "on_command": "", "off_command": "", "state": "off",
                "icon": None}))
            check("drag a tile", lambda: _drag(editor))
            check("edit a button", lambda: editor._apply_edit(1, 1, {
                "label": "Changed", "behavior": "toggle", "command": "true",
                "on_command": "a", "off_command": "b", "state": "on",
                "icon": None}))
            check("dirty marker in the title", lambda: _assert(
                editor.title_widget.get_title().endswith("•"),
                editor.title_widget.get_title()))
            check("properties resize", lambda: editor._apply_properties(
                deck.name, 2, 2))
            check("save", lambda: _assert(editor.on_save() is not False))
            check("clean after save", lambda: _assert(not editor.is_dirty()))
            check("delete a button", lambda: editor._delete_button(0, 0))
            check("clear deck", lambda: editor._clear_buttons())

            print("dialogs:")
            check("button editor (new)",
                  lambda: _cycle(ButtonEditor(window, "Add Button")))
            check("button editor (existing)", lambda: _cycle(ButtonEditor(
                window, "Edit Button",
                button=Button(0, 0, label="x", behavior="toggle"),
                on_save=lambda d: None, on_delete=lambda: None)))
            check("new deck dialog", lambda: _cycle(DeckCreateDialog(window)))
            check("deck properties dialog",
                  lambda: _cycle(DeckPropertiesDialog(window, deck)))
            check("preferences", lambda: _cycle(PreferencesWindow(self)))
            check("shortcuts window", lambda: self._on_shortcuts() or pump(0.3))
            check("about window", lambda: self._on_about() or pump(0.3))
            for extra in Gtk.Window.list_toplevels():
                if extra is not window and extra.get_visible():
                    extra.destroy()

            print("regressions:")
            seed_decks()
            window.show_deck_list()
            pump(0.3)
            page = window.current_page()
            live = next(d for d in page._decks if d.buttons)
            pad = self.open_pad(live)
            pump(0.3)
            check("edited deck refreshes an open pad",
                  lambda: _pad_refreshes(self, window, live, pad))
            check("deleting a deck closes its pad",
                  lambda: _delete_closes_pad(self, window))

            print("navigation:")
            check("back to the list", lambda: window.show_deck_list())
            check("empty state", lambda: _empty_state(window))
            check("window closes", lambda: window.destroy())
        finally:
            GLib.idle_add(self.quit)


def _assert(condition, detail=""):
    if not condition:
        raise AssertionError(str(detail) or "assertion failed")


def _rows(page):
    rows, child = [], page.listbox.get_first_child() if page.listbox else None
    while child:
        rows.append(child)
        child = child.get_next_sibling()
    return rows


def _classes(widget):
    return list(widget.get_css_classes())


def _reorder(page):
    before = [d.name for d in page._decks]
    rows = _rows(page)
    page._drag_row = rows[0]
    page._apply_row_swap(rows[1])
    page._drag_end()
    pump(0.2)
    _assert([d.name for d in page._decks] != before, "order did not change")
    _assert(prefs.get_deck_order(), "order was not saved")


def _press(pad, deck, toggle):
    target = next(b for b in deck.buttons.values() if b.is_toggle == toggle)
    tile = pad.grid.get_first_child()
    pad.grid._on_clicked(tile, target)
    pump(0.3)


def _close_pad(app, deck):
    app.close_pad(deck.deck_id)
    for _ in range(8):
        pump(0.2)
        if not app.is_pad_open(deck.deck_id):
            return
    raise AssertionError("pad stayed registered after closing")


def _drag(editor):
    filled = [pos for pos in editor.deck.positions()
              if editor.deck.get(*pos) is not None]
    _assert(filled, "no button to drag")
    source = filled[0]
    target = next(pos for pos in editor.deck.positions() if pos != source)
    editor._drag_pos = source
    editor._drag_origin = source
    editor._apply_swap(target)
    editor._finish_drag()
    pump(0.2)
    _assert(editor.deck.get(*target) is not None, "button did not land")


def _cycle(dialog):
    dialog.present()
    pump(0.3)
    dialog.destroy()


def _pad_refreshes(app, window, deck, pad):
    before = len(pad.grid.deck.buttons)
    window.edit_deck(deck)
    pump(0.3)
    editor = window.current_page()
    editor._apply_new(1, 2, {"label": "Fresh", "behavior": "single",
                             "command": "true", "on_command": "",
                             "off_command": "", "state": "off", "icon": None})
    editor.on_save()
    pump(0.3)
    after = len(app.pads[deck.deck_id].grid.deck.buttons)
    _assert(after == before + 1, f"pad still shows {after} buttons, not {before + 1}")
    window.show_deck_list()
    pump(0.3)


def _delete_closes_pad(app, window):
    page = window.current_page()
    deck = page._decks[0]
    app.open_pad(deck)
    pump(0.3)
    page._delete(deck)
    for _ in range(8):
        pump(0.2)
        if not app.is_pad_open(deck.deck_id):
            return
    raise AssertionError("pad stayed open after its deck was deleted")


def _empty_state(window):
    for path in deck_store.list_deck_paths():
        deck_store.delete_deck(path)
    window.show_deck_list()
    pump(0.3)


if __name__ == "__main__":
    Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)
    app = Smoke()
    app.set_application_id("io.github.prabhatm021.deckapp.smoke")
    app.run([])
    print()
    if failures:
        print(f"FAILED {len(failures)}/{checked}: {failures}")
        sys.exit(1)
    print(f"all {checked} UI checks passed")
