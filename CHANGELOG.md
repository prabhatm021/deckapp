# Changelog

## 3.0.0

Rewrite of the internals plus a pass over the interface.

### Fixed

- GTK4 has no `destroy` signal, so windows closed with `close()` were never
  deregistered: closed pads stayed "open" forever and the main window's
  reference was never released.
- Re-rendering tiles inside a drag crossing handler tripped GTK's own drop
  target asserts, flooding the terminal with `Gtk-CRITICAL` during every drag.
- A pad kept showing stale buttons after its deck was edited and saved.
- Deleting a deck left its pad window open, running a deck that no longer existed.
- Quitting from the tray discarded unsaved edits without asking.
- The ▶ test button in the button editor took keyboard focus, so a Right arrow
  at the end of a long command jumped the caret out of the field.
- Icons picked in the editor showed up as broken until the app was restarted:
  icon paths were absolute when loaded from disk but relative when just set.
  Paths are now stored relative everywhere and resolved only for display.
- Editing a button re-copied its icon every time, leaving orphaned files in
  `assets/icons/`. Icons are content-addressed now, so the same image is stored
  once, and unused files can be pruned (`remove_unused_icons` over MCP).
- A malformed deck file crashed the app with a traceback. Bad files are now
  reported and skipped, and the remaining decks still load.
- Closing the window with the title-bar button skipped the unsaved-changes
  prompt and silently discarded edits.
- Buttons whose `behavior` was neither `single` nor `toggle` produced
  `AttributeError` crashes when saved. Every button now carries every field.
- Deck writes were not atomic — an interrupted save could truncate a deck file.
- Two decks with the same name shared saved toggle state.
- Deck names containing `&` or `<` broke the deck list rendering.
- Packaging was broken: an invalid build backend and a package layout that
  produced an empty wheel.

### Added

- **Pad windows** — open a deck as a bare window with no title bar, from the
  deck list, the tray menu, or `deckapp --deck <name>`.
- **Top-bar icon** — `Run in background` in Preferences keeps DeckApp in the
  shell's status area with every deck one click away; `Start on login` brings it
  back at boot. Implemented as StatusNotifierItem + DBusMenu over D-Bus, since
  the usual tray libraries are GTK3-only.
- **Desktop notifications** for failed commands, naming the button and its deck
  and carrying the shell's own error, replacing in-app toasts.
- Drag decks into any order in the list, saved between sessions.
- A DeckApp icon, used by the window, the dock, the tray and notifications.
- Grid size is editable after creation (**Deck options → Deck Properties**),
  from 1 × 1 up to 12 × 12, with a warning before buttons are dropped.
- Drag a button onto another cell to move it, or onto an occupied cell to swap.
- A ▶ test button next to each command field in the button editor.
- Icons can be removed again, and are validated (type, size) on import.
- Keyboard shortcuts: `Ctrl+N`, `Ctrl+S`, `Ctrl+,`, `Esc`, `Ctrl+Q`.
- Main menu with Preferences, Keyboard Shortcuts, About and Open Decks Folder.
- Empty state on the deck list instead of a bare window.
- A desktop entry in `packaging/`.
- `DECKAPP_DATA_DIR` and `DECKAPP_DEBUG` environment variables.
- Core test suite: `python3 -m pytest`.

### Changed

- A single button stays lit for as long as its command runs, instead of a fixed
  220 ms flash.
- Toggle keys are green when ON and red when OFF; single keys use the accent
  colour while running.
- No in-app toasts anywhere: failures become notifications, successes are silent.
- Navigation happens inside one window instead of opening and closing a new
  window per screen, so the window no longer jumps around the desktop.
- The deck list shows each deck's real name and grid size.
- Commands run in their own session, so a child process can no longer take
  down the app, and long-running commands are no longer reported as failures.
- Deck files are read defensively: out-of-range buttons, unparseable grid sizes
  and unknown behaviours are normalised instead of trusted.
- `core/` no longer depends on GTK, only on `GLib`, so the model, the tests and
  the MCP server all run without a display.
- The deck list opens a deck; editing moved behind a pencil button.

## 2.0.0

Initial public release.
