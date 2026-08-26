#!/usr/bin/env python3
"""Render DeckApp's screens to screenshots/{light,dark}/ plus an index.html.

    python3 tools/screenshots.py            # every screen, both themes
    python3 tools/screenshots.py 02 05      # only screens whose name contains these

Needs a running X11 display; captures the real window pixels with xwininfo,
xprop (_GTK_FRAME_EXTENTS, so window shadows are cropped off) and Pillow.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "screenshots")
DEMO = os.path.join(tempfile.gettempdir(), "deckapp-shots-data")

os.environ["DECKAPP_DATA_DIR"] = DEMO
os.environ["XDG_CONFIG_HOME"] = os.path.join(DEMO, "config")
sys.path.insert(0, os.path.dirname(REPO))

import gi  # noqa: E402
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkX11", "4.0")
from gi.repository import Adw, GdkX11, GLib, Gtk  # noqa: E402,F401
from PIL import Image  # noqa: E402

from deckapp.core import deck_store  # noqa: E402
from deckapp.core.models import Button  # noqa: E402

DISPLAY = os.environ.get("DISPLAY", ":0")
ONLY = [a for a in sys.argv[1:] if not a.startswith("-")]
THEMES = ["light", "dark"]
if "--light" in sys.argv:
    THEMES = ["light"]
elif "--dark" in sys.argv:
    THEMES = ["dark"]

TITLES = {
    "01-deck-list-empty": "Deck list — empty state (first launch)",
    "02-deck-list": "Deck list — with decks",
    "03-deck-run": "Run mode — press buttons (Mute toggle is ON)",
    "05-editor": "Edit mode",
    "06-editor-unsaved": "Edit mode — unsaved changes",
    "07-button-editor-single": "Button editor — single behaviour",
    "08-button-editor-toggle": "Button editor — toggle behaviour",
    "09-new-deck": "New deck dialog",
    "10-deck-properties": "Deck properties (rename + resize grid)",
    "11-confirm-delete": "Confirm deck deletion",
    "12-unsaved-changes": "Unsaved changes prompt",
    "13-shortcuts": "Keyboard shortcuts window",
    "14-about": "About window",
    "15-large-grid": "Run mode — 6 × 8 grid",
    "16-editor-empty-deck": "Edit mode — brand new empty deck",
}

DECKS = {
    "media.json": {
        "deck_id": "media", "deck_name": "Media Controls",
        "grid": {"rows": 3, "cols": 4},
        "buttons": {
            "0,0": {"label": "Mute", "behavior": "toggle", "state": "on",
                    "on": {"command": "pactl set-sink-mute @DEFAULT_SINK@ 1"},
                    "off": {"command": "pactl set-sink-mute @DEFAULT_SINK@ 0"}},
            "0,1": {"label": "Volume −", "behavior": "single",
                    "command": "pactl set-sink-volume @DEFAULT_SINK@ -5%"},
            "0,2": {"label": "Volume +", "behavior": "single",
                    "command": "pactl set-sink-volume @DEFAULT_SINK@ +5%"},
            "0,3": {"label": "Play / Pause", "behavior": "single",
                    "command": "playerctl play-pause"},
            "1,0": {"label": "Previous", "behavior": "single",
                    "command": "playerctl previous"},
            "1,1": {"label": "Next", "behavior": "single",
                    "command": "playerctl next"},
            "1,3": {"label": "Night Light", "behavior": "toggle", "state": "off",
                    "on": {"command": "gsettings set org.gnome.settings-daemon."
                                      "plugins.color night-light-enabled true"},
                    "off": {"command": "gsettings set org.gnome.settings-daemon."
                                       "plugins.color night-light-enabled false"}},
            "2,0": {"label": "Screenshot", "behavior": "single",
                    "command": "gnome-screenshot -i"},
            "2,2": {"label": "No command yet", "behavior": "single", "command": ""},
        },
    },
    "dev-tools.json": {
        "deck_id": "dev-tools", "deck_name": "Dev Tools",
        "grid": {"rows": 2, "cols": 3},
        "buttons": {
            "0,0": {"label": "Build", "behavior": "single", "command": "make -C ~/proj"},
            "0,1": {"label": "Tests", "behavior": "single", "command": "pytest -q"},
            "1,0": {"label": "Docker", "behavior": "toggle", "state": "off",
                    "on": {"command": "systemctl --user start docker"},
                    "off": {"command": "systemctl --user stop docker"}},
        },
    },
    "scratch.json": {
        "deck_id": "scratch", "deck_name": "Scratch",
        "grid": {"rows": 4, "cols": 4}, "buttons": {},
    },
}


def reset_decks(with_decks=True):
    shutil.rmtree(os.path.join(DEMO, "decks"), ignore_errors=True)
    os.makedirs(os.path.join(DEMO, "decks"), exist_ok=True)
    if with_decks:
        for name, data in DECKS.items():
            with open(os.path.join(DEMO, "decks", name), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)


def demo_deck(name):
    return deck_store.load_deck(os.path.join(DEMO, "decks", name))


# ── Capture ──

def pump(seconds=0.4):
    context = GLib.MainContext.default()
    end = time.time() + seconds
    while time.time() < end:
        while context.pending():
            context.iteration(False)
        time.sleep(0.01)


def _int(pattern, text):
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


def capture(window, path, settle=0.7):
    """Grab the window's own pixels via xwd, so an overlapping window or a
    lost focus can never end up in the shot."""
    window.present()
    pump(settle)
    xid = window.get_surface().get_xid()

    raw = os.path.join(tempfile.gettempdir(), "deckapp-shot.xwd")
    with open(raw, "wb") as f:
        subprocess.run(["xwd", "-id", str(xid), "-silent"], stdout=f, check=True)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, path],
                   check=True)

    # Crop the client-side shadow that GTK draws around the window
    extents = subprocess.run(["xprop", "-id", str(xid), "_GTK_FRAME_EXTENTS"],
                             capture_output=True, text=True).stdout
    nums = re.findall(r"\d+", extents.split("=")[-1]) if "=" in extents else []
    image = Image.open(path)
    if len(nums) == 4:
        left, right, top, bottom = (int(n) for n in nums)
        image = image.crop((left, top, image.width - right, image.height - bottom))
        image.save(path)
    return image.size


# ── The screens ──

class Shooter(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.prabhatm021.deckapp.shots")
        self.taken = []

    def do_activate(self):
        try:
            schemes = {"light": Adw.ColorScheme.FORCE_LIGHT,
                       "dark": Adw.ColorScheme.FORCE_DARK}
            for theme, scheme in ((t, schemes[t]) for t in THEMES):
                Adw.StyleManager.get_default().set_color_scheme(scheme)
                self.theme = theme
                print(f"{theme}:")
                self.run_pass()
        finally:
            GLib.idle_add(self.quit)

    def shoot(self, window, name):
        if ONLY and not any(token in name for token in ONLY):
            return
        path = os.path.join(OUT, self.theme, name + ".png")
        size = capture(window, path)
        self.taken.append(name)
        print(f"  {self.theme}/{name}.png  {size[0]}×{size[1]}")

    def run_pass(self):
        from deckapp.app import DeckApp
        from deckapp.ui import DESTRUCTIVE, SUGGESTED, alert, confirm
        from deckapp.ui.button_editor import ButtonEditor
        from deckapp.ui.deck_dialog import DeckCreateDialog, DeckPropertiesDialog
        from deckapp.ui.main_window import MainWindow

        reset_decks(with_decks=False)
        window = MainWindow(self)
        window.set_default_size(560, 640)
        self.window = window
        self.shoot(window, "01-deck-list-empty")

        reset_decks()
        window.show_deck_list()
        self.shoot(window, "02-deck-list")

        media = demo_deck("media.json")
        window.open_deck(media)
        self.shoot(window, "03-deck-run")

        window.edit_deck(media)
        editor = window.current_page()
        self.shoot(window, "05-editor")

        editor._apply_new(1, 2, {"label": "Lock Screen", "behavior": "single",
                                 "command": "loginctl lock-session",
                                 "on_command": "", "off_command": "",
                                 "state": "off", "icon": None})
        self.shoot(window, "06-editor-unsaved")

        dialog = ButtonEditor(window, title="Edit Button", subtitle="Row 1, column 2",
                              button=Button(0, 1, label="Volume +",
                                            command="pactl set-sink-volume "
                                                    "@DEFAULT_SINK@ +5%"),
                              on_save=lambda d: None, on_delete=lambda: None)
        dialog.set_default_size(480, 560)
        self.shoot(dialog, "07-button-editor-single")
        dialog.destroy()

        dialog = ButtonEditor(window, title="Edit Button", subtitle="Row 1, column 1",
                              button=Button(0, 0, label="Mute", behavior="toggle",
                                            on_command="pactl set-sink-mute "
                                                       "@DEFAULT_SINK@ 1",
                                            off_command="pactl set-sink-mute "
                                                        "@DEFAULT_SINK@ 0"),
                              on_save=lambda d: None, on_delete=lambda: None)
        dialog.set_default_size(480, 620)
        self.shoot(dialog, "08-button-editor-toggle")
        dialog.destroy()

        dialog = DeckCreateDialog(window)
        dialog.name_row.set_text("Streaming")
        dialog.set_default_size(440, 300)
        self.shoot(dialog, "09-new-deck")
        dialog.destroy()

        dialog = DeckPropertiesDialog(window, media)
        dialog.set_default_size(440, 300)
        self.shoot(dialog, "10-deck-properties")
        dialog.destroy()

        dialog = confirm(window, "Delete “Media Controls”?",
                         "The deck and its buttons will be permanently removed.",
                         "Delete", lambda: None)
        self.shoot(dialog, "11-confirm-delete")
        dialog.destroy()

        dialog = alert(window, "Save changes?",
                       "“Media Controls” has unsaved changes.",
                       [("cancel", "Cancel", None),
                        ("discard", "Discard", DESTRUCTIVE),
                        ("save", "Save", SUGGESTED)],
                       default="save", close="cancel")
        self.shoot(dialog, "12-unsaved-changes")
        dialog.destroy()

        for name, builder, size in (
            ("13-shortcuts", DeckApp._on_shortcuts, (380, 330)),
            ("14-about", DeckApp._on_about, (420, 540)),
        ):
            before = set(Gtk.Window.list_toplevels())
            builder(self)
            pump(0.5)
            new = [w for w in Gtk.Window.list_toplevels() if w not in before]
            if new:
                new[0].set_default_size(*size)
                self.shoot(new[0], name)
                new[0].destroy()

        big = demo_deck("media.json")
        big.resize(6, 8)
        big.name = "Big Grid (6 × 8)"
        window.open_deck(big)
        window.set_default_size(900, 700)
        self.shoot(window, "15-large-grid")

        window.set_default_size(560, 640)
        window.edit_deck(demo_deck("scratch.json"))
        self.shoot(window, "16-editor-empty-deck")

        window.destroy()
        pump(0.2)


def write_index():
    import html
    import pathlib
    root = pathlib.Path(OUT)
    names = sorted({p.stem for p in (root / "light").glob("*.png")})
    sections, toc = [], []
    for i, name in enumerate(names, 1):
        title = html.escape(TITLES.get(name, name))
        cells = ""
        for theme in ("light", "dark"):
            if (root / theme / f"{name}.png").exists():
                cells += (f'<figure><figcaption>{theme}</figcaption>'
                          f'<img src="{theme}/{name}.png" alt="{title} ({theme})">'
                          f'</figure>')
        sections.append(f'<section id="s{i}"><h2><span class="n">{i}</span>{title}'
                        f'<code>{html.escape(name)}</code></h2>'
                        f'<div class="pair">{cells}</div></section>')
        toc.append(f'<li><a href="#s{i}">{i}. {title}</a></li>')

    (root / "index.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>DeckApp — screen review</title>
<style>
:root{{color-scheme:light dark;--fg:#1b1b1b;--bg:#fafafa;--card:#fff;--line:#dcdcdc;--dim:#666}}
@media (prefers-color-scheme:dark){{:root{{--fg:#eee;--bg:#1a1a1a;--card:#242424;--line:#3a3a3a;--dim:#aaa}}}}
body{{font:15px/1.5 system-ui,Cantarell,sans-serif;margin:0;padding:32px;background:var(--bg);color:var(--fg)}}
h1{{margin:0 0 4px}} p.sub{{color:var(--dim);margin:0 0 24px}}
ol.toc{{columns:2;max-width:900px;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 16px 16px 40px;margin:0 0 32px}}
ol.toc a{{color:inherit;text-decoration:none}} ol.toc a:hover{{text-decoration:underline}}
section{{margin:0 0 34px;max-width:1200px}}
h2{{font-size:16px;display:flex;align-items:center;gap:10px;margin:0 0 10px;font-weight:600}}
.n{{background:var(--fg);color:var(--bg);border-radius:999px;width:24px;height:24px;display:grid;place-items:center;font-size:12px}}
code{{color:var(--dim);font-size:12px;font-weight:400}}
.pair{{display:flex;gap:18px;flex-wrap:wrap}}
figure{{margin:0}} figcaption{{color:var(--dim);font-size:12px;margin-bottom:6px}}
img{{border:1px solid var(--line);border-radius:10px;max-width:100%;background:var(--card)}}
</style>
<h1>DeckApp — every screen</h1>
<p class="sub">{len(names)} screens × light and dark. Reference a screen by its number.</p>
<ol class="toc">{''.join(toc)}</ol>
{''.join(sections)}
""", encoding="utf-8")
    print(f"\nindex.html · {len(names)} screens in {OUT}")


if __name__ == "__main__":
    app = Shooter()
    app.run([])
    write_index()
