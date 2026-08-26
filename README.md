# DeckApp

DeckApp is a macro pad for Debian. You build a grid of buttons, each one runs a
shell command, and you open that grid as a small window on your desktop.

It is written in Python with GTK4 and libadwaita, so it follows your system
theme.

## Install

DeckApp needs GTK 4.8 and libadwaita 1.2 or newer.

### From the .deb

Download `deckapp_3.0.0_all.deb` from the releases page, then:

```bash
sudo apt install ./deckapp_3.0.0_all.deb
```

Use `apt`, not `dpkg -i`, so the dependencies come along. DeckApp then shows up
in your applications list like any other app, and `deckapp` works from a
terminal.

Your decks live in `~/.local/share/deckapp/`, so removing the package leaves
them alone:

```bash
sudo apt remove deckapp
```

To build the package yourself from a clone, run `./tools/build-deb.sh` and look
in `dist/`.

### From a clone

Install the dependencies:

```bash
sudo apt install python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

Then clone and run it:

```bash
git clone https://github.com/prabhatm021/deckapp.git
cd deckapp
python3 run.py
```

Started this way, DeckApp runs fine, but your desktop does not know it exists.
It will not be in your applications list, you cannot pin it, and GNOME will
throw away its notifications, so you never see the error when a command fails.

Two files fix that. One tells your desktop the app exists and how to start it,
the other is the icon:

```bash
install -Dm644 packaging/io.github.prabhatm021.deckapp.desktop ~/.local/share/applications/io.github.prabhatm021.deckapp.desktop
install -Dm644 assets/app/io.github.prabhatm021.deckapp.svg ~/.local/share/icons/hicolor/scalable/apps/io.github.prabhatm021.deckapp.svg
```

Open the first file and check the `Exec` line points at wherever you cloned
DeckApp. If you move the folder later, fix that line or the launcher stops
working.

## Making a deck

Click the plus button, give the deck a name, and pick how many rows and columns
you want. Anything up to 12 by 12 works.

Click the pencil next to a deck to edit it, then click an empty cell to add a
button. Give it a label and the command you would type in a terminal. The play
button next to the command field runs it right there, so you can check it before
saving. Drag a button to move it, or drop it on another button to swap the two.

A button is either single or toggle. A single button runs its command every time
you press it and stays lit while the command is running. A toggle has an ON
command and an OFF command, and it remembers which state it was in the next time
you open the deck. Toggles are green when on and red when off.

You can put a picture on a button. A PNG with a transparent background works
best. DeckApp warns you if the image you picked has no transparency, because it
will show up as a plain rectangle.

## Opening a deck

Click a deck in the list and it opens as its own window with no title bar, just
the keys. Press Escape to close it, or use the close button that appears when
you move your pointer over it. Drag any empty space to move the window around.

If a command fails, you get a normal desktop notification with the error the
shell printed.

## Running in the background

Open Preferences from the menu and turn on "Run in background". DeckApp then
keeps an icon in the top bar, and closing the window leaves it running. Click
that icon to see your decks and open any of them. "Start on login" does the same
thing from boot.

Quit from that icon when you want everything closed.

On GNOME the icon needs the AppIndicator extension. DeckApp tells you if it is
missing.

## Shortcuts

| Key | Action |
| --- | --- |
| Ctrl+N | New deck |
| Ctrl+S | Save |
| Ctrl+, | Preferences |
| Escape | Go back, or close a pad |
| Ctrl+Q | Quit |

## From a terminal

```bash
deckapp                 # the deck list
deckapp --deck media    # open one deck directly
deckapp --tray          # background, no window
deckapp --list          # print deck names
```

## Your files

Installed from the .deb, your decks and button icons live in
`~/.local/share/deckapp/`. Run from a git clone instead and they stay inside
that folder, so the clone is self contained. Settings and toggle states live in
`~/.config/deckapp/` either way.

If you used the clone first and then installed the package, copy your decks
over:

```bash
mkdir -p ~/.local/share/deckapp/decks
cp decks/*.json ~/.local/share/deckapp/decks/
cp -r assets/icons ~/.local/share/deckapp/assets/
```

Decks are JSON files you can edit by hand:

```json
{
  "deck_id": "media",
  "deck_name": "Media Controls",
  "grid": { "rows": 3, "cols": 4 },
  "buttons": {
    "0,0": {
      "label": "Screenshot",
      "behavior": "single",
      "command": "gnome-screenshot -i"
    },
    "1,0": {
      "label": "Mute",
      "behavior": "toggle",
      "state": "off",
      "on":  { "command": "pactl set-sink-mute @DEFAULT_SINK@ 1" },
      "off": { "command": "pactl set-sink-mute @DEFAULT_SINK@ 0" }
    }
  }
}
```

Keys are `"row,col"` counting from zero at the top left. If you break the JSON,
DeckApp skips the broken parts instead of refusing to start.

Buttons run with your shell and your environment, so a deck file someone sends
you can do anything a shell script can.

## Driving it from an assistant

There is a separate MCP server at
[deckapp-mcp](https://github.com/prabhatm021/deckapp-mcp). It lets an assistant
create decks, wire buttons to commands and press them, working on the same deck
files as the app.

## Tests

```bash
python3 -m pytest          # core tests, no display needed
python3 tools/smoke_ui.py  # opens every screen and checks it works
```

## License

[MIT](LICENSE)
