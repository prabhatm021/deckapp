"""The pressable button grid, shared by the deck page and the pad window."""
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import GLib, Gtk

from deckapp.core.command_runner import run_command
from deckapp.core.state_manager import get_state_manager
from deckapp.ui import make_tile_content

MIN_LIT_MS = 260   # a fast command should still be visible
SPACING = 8
MARGIN = 8


class DeckGrid(Gtk.Grid):
    """The deck's buttons.

    `crop` trims the grid to the area that actually holds buttons, so a pad
    for a 4 × 4 deck with five buttons in one corner is not mostly empty
    window. The editor always shows the full grid.
    """

    def __init__(self, deck, crop=False, on_failure=None):
        super().__init__(
            row_spacing=SPACING, column_spacing=SPACING,
            margin_top=MARGIN, margin_bottom=MARGIN,
            margin_start=MARGIN, margin_end=MARGIN,
        )
        self.deck = deck
        self.crop = crop
        # on_failure(title, body): a command that failed, worth a notification
        self.on_failure = on_failure
        self.state_manager = get_state_manager()
        self._timers = {}
        self._started_at = {}

        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        self._restore_toggle_states()
        self._build()

    # ── Building ──

    def _restore_toggle_states(self):
        for pos, button in self.deck.buttons.items():
            if button.is_toggle:
                button.state = self.state_manager.get(
                    self.deck.deck_id, pos, button.state
                )

    def bounds(self):
        """(top, left, bottom, right) of the area to draw, inclusive."""
        if not self.crop or not self.deck.buttons:
            return 0, 0, self.deck.rows - 1, self.deck.cols - 1
        rows = [row for row, _ in self.deck.buttons]
        cols = [col for _, col in self.deck.buttons]
        return min(rows), min(cols), max(rows), max(cols)

    def _build(self):
        if self.crop and not self.deck.buttons:
            self.attach(self._make_empty_notice(), 0, 0, 1, 1)
            return

        top, left, bottom, right = self.bounds()
        for row in range(top, bottom + 1):
            for col in range(left, right + 1):
                button = self.deck.get(row, col)
                widget = (self._make_tile(button) if button
                          else self._make_placeholder())
                self.attach(widget, col - left, row - top, 1, 1)

    def _make_empty_notice(self):
        label = Gtk.Label(label="No buttons yet.\nAdd some in DeckApp.")
        label.set_justify(Gtk.Justification.CENTER)
        label.add_css_class("dim-label")
        for margin in ("top", "bottom", "start", "end"):
            getattr(label, f"set_margin_{margin}")(24)
        return label

    def _make_placeholder(self):
        widget = Gtk.Button()
        widget.add_css_class("deck-btn")
        widget.add_css_class("deck-slot")
        widget.set_sensitive(False)
        widget.set_can_focus(False)
        widget.set_child(Gtk.Label(label=""))
        return widget

    def _make_tile(self, button):
        widget = Gtk.Button()
        widget.add_css_class("deck-btn")
        widget.set_child(make_tile_content(button))

        if button.is_toggle:
            widget.add_css_class("deck-toggle-on" if button.state == "on"
                                 else "deck-toggle-off")
        if not button.is_configured():
            widget.add_css_class("deck-unset")

        widget.connect("clicked", self._on_clicked, button)
        return widget

    # ── Pressing ──

    def _on_clicked(self, widget, button):
        command = button.command_for_next_press()

        if not command.strip() and not button.is_toggle:
            return          # an unconfigured key is dimmed; pressing it is a no-op

        if button.is_toggle:
            self._flip_toggle(widget, button)
        else:
            self._light_while_running(widget)

        if command.strip():
            run_command(
                command,
                on_error=lambda message, b=button: self._report_failure(b, message),
                on_finished=lambda ok, w=widget: self._command_finished(w, ok),
            )
        else:
            self._command_finished(widget, False)

    def _flip_toggle(self, widget, button):
        button.state = "off" if button.state == "on" else "on"
        self.state_manager.set(
            self.deck.deck_id, (button.row, button.col), button.state
        )
        on = button.state == "on"
        widget.add_css_class("deck-toggle-on" if on else "deck-toggle-off")
        widget.remove_css_class("deck-toggle-off" if on else "deck-toggle-on")

    def _light_while_running(self, widget):
        """A single button stays lit for as long as its command runs."""
        self._cancel_timer(widget)
        widget.add_css_class("deck-running")
        self._started_at[widget] = GLib.get_monotonic_time()

    def _command_finished(self, widget, _succeeded):
        started = self._started_at.pop(widget, None)
        if started is None:
            widget.remove_css_class("deck-running")
            return GLib.SOURCE_REMOVE

        elapsed_ms = (GLib.get_monotonic_time() - started) // 1000
        remaining = max(0, MIN_LIT_MS - elapsed_ms)
        if remaining == 0:
            self._unlight(widget)
        else:
            self._timers[widget] = GLib.timeout_add(remaining,
                                                    self._unlight, widget)
        return GLib.SOURCE_REMOVE

    def _unlight(self, widget):
        self._timers.pop(widget, None)
        if widget.get_root() is not None:
            widget.remove_css_class("deck-running")
        return GLib.SOURCE_REMOVE

    def _cancel_timer(self, widget):
        timer = self._timers.pop(widget, None)
        if timer:
            GLib.source_remove(timer)

    def cancel_flashes(self):
        for timer in self._timers.values():
            GLib.source_remove(timer)
        self._timers.clear()
        self._started_at.clear()

    def _report_failure(self, button, message):
        if self.on_failure is not None:
            # The reason is already the body, so the title just says which
            # button, on which deck, went wrong.
            self.on_failure(
                f"“{button.display_label()}” from “{self.deck.name}” failed",
                message,
            )
        else:
            self.on_message(message)
        return GLib.SOURCE_REMOVE
