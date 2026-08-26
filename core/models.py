"""Data model for decks and buttons.

Invariants worth knowing:

* A Button always has every attribute (command, on_command, off_command,
  state, icon) regardless of its behaviour. Missing-attribute crashes were
  a real problem in 2.x.
* `Button.icon` is ALWAYS stored relative to the assets dir ("icons/x.png")
  or None. Use `Button.icon_path` when you need an absolute path to load.
"""
from pathlib import Path

from deckapp.core.paths import resolve_asset, to_relative_asset

SINGLE = "single"
TOGGLE = "toggle"
BEHAVIORS = (SINGLE, TOGGLE)

MIN_GRID = 1
MAX_GRID = 12
DEFAULT_ROWS = 4
DEFAULT_COLS = 4

MAX_LABEL_LEN = 64


def clamp_grid(value, default) -> int:
    """Coerce anything to a sane grid dimension."""
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(MIN_GRID, min(MAX_GRID, value))


class Button:
    def __init__(self, row, col, label="", behavior=SINGLE, command="",
                 on_command="", off_command="", state="off", icon=None):
        self.row = int(row)
        self.col = int(col)
        self.label = (label or "")[:MAX_LABEL_LEN]
        self.behavior = behavior if behavior in BEHAVIORS else SINGLE
        self.command = command or ""
        self.on_command = on_command or ""
        self.off_command = off_command or ""
        self.state = "on" if state == "on" else "off"
        self.icon = icon or None

    # ── Serialisation ──

    @classmethod
    def from_dict(cls, row, col, data):
        if not isinstance(data, dict):
            data = {}

        behavior = data.get("behavior", SINGLE)
        if behavior not in BEHAVIORS:
            behavior = SINGLE

        # Tolerate both {"on": {"command": "…"}} and {"on": "…"}
        def _cmd(key):
            value = data.get(key)
            if isinstance(value, dict):
                return str(value.get("command", "") or "")
            return str(value or "")

        icon = data.get("icon") or None
        if icon:
            # 2.x sometimes wrote absolute paths — normalise them back.
            icon = to_relative_asset(str(icon))

        return cls(
            row=row,
            col=col,
            label=str(data.get("label", "") or ""),
            behavior=behavior,
            command=str(data.get("command", "") or ""),
            on_command=_cmd("on"),
            off_command=_cmd("off"),
            state=data.get("state", "off"),
            icon=icon,
        )

    def to_dict(self):
        data = {"label": self.label, "behavior": self.behavior}
        if self.icon:
            data["icon"] = self.icon
        if self.behavior == SINGLE:
            data["command"] = self.command
        else:
            data["state"] = self.state
            data["on"] = {"command": self.on_command}
            data["off"] = {"command": self.off_command}
        return data

    # ── Helpers ──

    @property
    def icon_path(self):
        """Absolute path to the icon file, or None if unset/missing."""
        if not self.icon:
            return None
        path = resolve_asset(self.icon)
        return path if Path(path).is_file() else None

    @property
    def is_toggle(self):
        return self.behavior == TOGGLE

    def command_for_next_press(self):
        """The command a press would run right now ('' if nothing is configured)."""
        if self.behavior == SINGLE:
            return self.command
        return self.off_command if self.state == "on" else self.on_command

    def is_configured(self):
        if self.behavior == SINGLE:
            return bool(self.command.strip())
        return bool(self.on_command.strip() or self.off_command.strip())

    def display_label(self):
        return self.label or "Untitled"


class Deck:
    def __init__(self, deck_id, name, rows=DEFAULT_ROWS, cols=DEFAULT_COLS,
                 buttons=None, path=None):
        self.deck_id = deck_id
        self.name = name
        self.rows = clamp_grid(rows, DEFAULT_ROWS)
        self.cols = clamp_grid(cols, DEFAULT_COLS)
        self.buttons = buttons or {}
        self.path = Path(path) if path else None

    # ── Serialisation ──

    @classmethod
    def from_dict(cls, data, path=None, fallback_id="deck"):
        if not isinstance(data, dict):
            data = {}

        grid = data.get("grid")
        if not isinstance(grid, dict):
            grid = {}

        deck = cls(
            deck_id=str(data.get("deck_id") or fallback_id),
            name=str(data.get("deck_name") or fallback_id),
            rows=grid.get("rows", DEFAULT_ROWS),
            cols=grid.get("cols", DEFAULT_COLS),
            path=path,
        )

        raw_buttons = data.get("buttons")
        if not isinstance(raw_buttons, dict):
            raw_buttons = {}

        for key, btn_data in raw_buttons.items():
            try:
                row_s, col_s = str(key).split(",")
                row, col = int(row_s), int(col_s)
            except (ValueError, TypeError):
                continue  # skip malformed keys instead of dying
            if not (0 <= row < deck.rows and 0 <= col < deck.cols):
                continue  # skip buttons outside the grid
            deck.buttons[(row, col)] = Button.from_dict(row, col, btn_data)

        return deck

    def to_dict(self):
        return {
            "deck_id": self.deck_id,
            "deck_name": self.name,
            "grid": {"rows": self.rows, "cols": self.cols},
            "buttons": {
                f"{row},{col}": btn.to_dict()
                for (row, col), btn in sorted(self.buttons.items())
            },
        }

    # ── Grid operations ──

    def positions(self):
        for row in range(self.rows):
            for col in range(self.cols):
                yield row, col

    def get(self, row, col):
        return self.buttons.get((row, col))

    def place(self, row, col, button):
        button.row, button.col = row, col
        self.buttons[(row, col)] = button

    def remove(self, row, col):
        return self.buttons.pop((row, col), None)

    def move(self, src, dst):
        """Move a button, swapping with the destination if it is occupied."""
        if src == dst:
            return
        moving = self.buttons.pop(src, None)
        if moving is None:
            return
        displaced = self.buttons.pop(dst, None)
        self.place(dst[0], dst[1], moving)
        if displaced is not None:
            self.place(src[0], src[1], displaced)

    def buttons_lost_by_resize(self, rows, cols):
        """Buttons that would fall outside a resized grid."""
        return [b for (r, c), b in self.buttons.items() if r >= rows or c >= cols]

    def resize(self, rows, cols):
        """Resize the grid, dropping any button that no longer fits."""
        self.rows = clamp_grid(rows, self.rows)
        self.cols = clamp_grid(cols, self.cols)
        for pos in [p for p in self.buttons if p[0] >= self.rows or p[1] >= self.cols]:
            del self.buttons[pos]

    def used_icons(self):
        return {b.icon for b in self.buttons.values() if b.icon}
