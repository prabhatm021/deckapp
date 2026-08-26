"""Core logic tests — no GTK widgets, safe to run headless.

    python3 -m pytest
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    """Point every path helper at a throwaway directory."""
    monkeypatch.setenv("DECKAPP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path


# ── Deck creation & naming ──

def test_create_deck_slugifies_and_deduplicates():
    from deckapp.core import deck_store

    first = deck_store.create_deck("My Deck!", 3, 5)
    assert (first.rows, first.cols) == (3, 5)
    assert first.path.name == "my-deck.json"

    second = deck_store.create_deck("My Deck!")
    assert second.path.name == "my-deck-2.json"
    assert second.deck_id != first.deck_id  # separate toggle state


@pytest.mark.parametrize("name", ["", "   ", "!!!", "***", "x" * 100])
def test_invalid_names_are_rejected(name):
    from deckapp.core import deck_store

    with pytest.raises(deck_store.DeckError):
        deck_store.create_deck(name)


def test_grid_size_is_clamped():
    from deckapp.core import deck_store
    from deckapp.core.models import MAX_GRID, MIN_GRID

    assert deck_store.create_deck("big", 500, 500).rows == MAX_GRID
    assert deck_store.create_deck("small", 0, -4).cols == MIN_GRID


# ── Loading hostile / broken files ──

def test_corrupt_deck_raises_deck_error():
    from deckapp.core import deck_store

    path = deck_store.get_decks_dir() / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(deck_store.DeckError):
        deck_store.load_deck(path)


def test_one_broken_deck_does_not_hide_the_others():
    from deckapp.core import deck_store

    deck_store.create_deck("good")
    (deck_store.get_decks_dir() / "broken.json").write_text("nope", encoding="utf-8")

    decks, errors = deck_store.load_all_decks()
    assert [d.name for d in decks] == ["good"]
    assert len(errors) == 1


def test_hostile_json_is_normalised():
    from deckapp.core import deck_store
    from deckapp.core.models import MAX_GRID

    path = deck_store.get_decks_dir() / "hostile.json"
    path.write_text(json.dumps({
        "deck_name": "R&D",
        "grid": {"rows": "banana", "cols": 999},
        "buttons": {
            "not-a-key": {"label": "skipped"},
            "9,9": {"label": "outside the grid"},
            "0,0": {"label": "ok", "behavior": "nonsense"},
            "0,1": {"behavior": "toggle", "on": "shorthand-on"},
            "0,2": None,
        },
    }), encoding="utf-8")

    deck = deck_store.load_deck(path)
    assert deck.rows == 4                      # unparseable -> default
    assert deck.cols == MAX_GRID               # oversized -> clamped
    assert (9, 9) not in deck.buttons          # out-of-grid dropped
    assert len(deck.buttons) == 3              # malformed key dropped
    assert deck.get(0, 0).behavior == "single"  # unknown behaviour -> single
    assert deck.get(0, 1).on_command == "shorthand-on"
    assert deck.get(0, 2).label == ""          # null button survives


def test_save_load_round_trip():
    from deckapp.core import deck_store
    from deckapp.core.models import Button, Deck

    deck = Deck("rt", "Round Trip", 2, 2)
    deck.place(0, 0, Button(0, 0, label="A", command="echo a"))
    deck.place(1, 1, Button(1, 1, label="B", behavior="toggle",
                            on_command="on", off_command="off", state="on"))

    path = deck_store.get_decks_dir() / "rt.json"
    deck_store.save_deck(deck, path)
    assert deck_store.load_deck(path).to_dict() == deck.to_dict()


def test_save_is_atomic(monkeypatch):
    from deckapp.core import deck_store

    deck = deck_store.create_deck("keepme")
    original = deck.path.read_text(encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("deckapp.core.paths.os.fsync", boom)
    with pytest.raises(deck_store.DeckError):
        deck_store.save_deck(deck, deck.path)

    assert deck.path.read_text(encoding="utf-8") == original


# ── Buttons ──

def test_button_always_has_every_attribute():
    from deckapp.core.models import Button

    button = Button.from_dict(0, 0, {"behavior": "toggle"})
    for attr in ("command", "on_command", "off_command", "state", "icon"):
        assert hasattr(button, attr)


def test_toggle_runs_the_opposite_command():
    from deckapp.core.models import Button

    button = Button(0, 0, behavior="toggle", on_command="up", off_command="down")
    assert button.command_for_next_press() == "up"
    button.state = "on"
    assert button.command_for_next_press() == "down"


def test_move_swaps_and_updates_coordinates():
    from deckapp.core.models import Button, Deck

    deck = Deck("m", "Move", 2, 2)
    a, b = Button(0, 0, label="A"), Button(1, 1, label="B")
    deck.place(0, 0, a)
    deck.place(1, 1, b)

    deck.move((0, 0), (1, 1))
    assert deck.get(1, 1) is a and (a.row, a.col) == (1, 1)
    assert deck.get(0, 0) is b and (b.row, b.col) == (0, 0)


def test_resize_drops_out_of_range_buttons():
    from deckapp.core.models import Button, Deck

    deck = Deck("r", "Resize", 3, 3)
    deck.place(0, 0, Button(0, 0, label="keep"))
    deck.place(2, 2, Button(2, 2, label="lose"))

    assert [b.label for b in deck.buttons_lost_by_resize(2, 2)] == ["lose"]
    deck.resize(2, 2)
    assert list(deck.buttons) == [(0, 0)]


# ── Icons ──

@pytest.fixture
def png(tmp_path):
    path = tmp_path / "icon.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return path


def test_importing_the_same_icon_twice_does_not_duplicate(png):
    from deckapp.core import icons

    first = icons.import_icon(str(png))
    assert icons.import_icon(str(png)) == first
    assert len(list(icons.get_icons_dir().iterdir())) == 1

    # Re-importing an already-managed icon must not copy it again either
    stored = icons.get_icons_dir() / os.path.basename(first)
    assert icons.import_icon(str(stored)) == first
    assert len(list(icons.get_icons_dir().iterdir())) == 1


def test_legacy_absolute_icon_paths_are_normalised(png):
    from deckapp.core import icons
    from deckapp.core.models import Button
    from deckapp.core.paths import resolve_asset

    relative = icons.import_icon(str(png))
    absolute = resolve_asset(relative)

    button = Button.from_dict(0, 0, {"icon": absolute})
    assert button.icon == relative
    assert button.icon_path == absolute


def test_missing_icon_file_does_not_break_a_button():
    from deckapp.core.models import Button

    assert Button(0, 0, icon="icons/gone.png").icon_path is None


@pytest.mark.parametrize("factory", [
    lambda p: str(p / "does-not-exist.png"),
    lambda p: str(_write(p / "script.exe", b"MZ")),
    lambda p: str(_write(p / "empty.png", b"")),
])
def test_bad_icons_are_rejected(tmp_path, factory):
    from deckapp.core import icons

    with pytest.raises(icons.IconError):
        icons.import_icon(factory(tmp_path))


def _write(path, data):
    path.write_bytes(data)
    return path


def test_prune_only_removes_unused_icons(png):
    from deckapp.core import icons

    relative = icons.import_icon(str(png))
    assert icons.prune_unused_icons({relative}) == 0
    assert icons.prune_unused_icons(set()) == 1


# ── State ──

def test_toggle_state_survives_a_restart(tmp_path):
    from deckapp.core.state_manager import StateManager

    path = tmp_path / "state.json"
    StateManager(state_file=path).set("deck", (0, 1), "on")
    assert StateManager(state_file=path).get("deck", (0, 1)) == "on"


def test_corrupt_state_file_is_ignored(tmp_path):
    from deckapp.core.state_manager import StateManager

    path = tmp_path / "state.json"
    path.write_text("{{{", encoding="utf-8")
    assert StateManager(state_file=path).get("deck", (0, 1)) == "off"


def test_forget_deck_clears_its_positions(tmp_path):
    from deckapp.core.state_manager import StateManager

    manager = StateManager(state_file=tmp_path / "state.json")
    manager.set("deck", (0, 0), "on")
    manager.forget_deck("deck")
    assert manager.get("deck", (0, 0)) == "off"


# ── Commands ──

def test_empty_command_is_not_run():
    from deckapp.core.command_runner import run_command

    assert run_command("   ") is False
    assert run_command(None) is False


def test_failing_command_reports_an_error():
    import threading
    from deckapp.core.command_runner import run_command

    seen, done = [], threading.Event()

    def capture(message):
        seen.append(message)
        done.set()

    # on_error is normally marshalled to the GTK main loop; call it directly here
    import deckapp.core.command_runner as runner
    original = runner.GLib.idle_add
    runner.GLib.idle_add = lambda fn, *a, **kw: fn(*a)
    try:
        assert run_command("exit 42", on_error=capture) is True
        assert done.wait(timeout=15)
    finally:
        runner.GLib.idle_add = original

    assert "42" in seen[0]


# ── Deck order ──

def test_deck_order_is_applied_and_persisted():
    from deckapp.core import deck_store, prefs

    a = deck_store.create_deck("Alpha")
    b = deck_store.create_deck("Beta")
    c = deck_store.create_deck("Gamma")

    decks, _ = deck_store.load_all_decks()
    assert [d.name for d in prefs.apply_deck_order(decks)] == ["Alpha", "Beta", "Gamma"]

    prefs.set_deck_order([prefs.deck_key(c), prefs.deck_key(a), prefs.deck_key(b)])
    decks, _ = deck_store.load_all_decks()
    assert [d.name for d in prefs.apply_deck_order(decks)] == ["Gamma", "Alpha", "Beta"]


def test_new_decks_sort_after_ordered_ones():
    from deckapp.core import deck_store, prefs

    known = deck_store.create_deck("Known")
    prefs.set_deck_order([prefs.deck_key(known)])
    deck_store.create_deck("Newcomer")

    decks, _ = deck_store.load_all_decks()
    assert [d.name for d in prefs.apply_deck_order(decks)] == ["Known", "Newcomer"]


def test_order_survives_a_deleted_deck():
    from deckapp.core import deck_store, prefs

    a = deck_store.create_deck("Alpha")
    b = deck_store.create_deck("Beta")
    prefs.set_deck_order([prefs.deck_key(b), prefs.deck_key(a), "deck-that-is-gone"])
    deck_store.delete_deck(a.path)

    decks, _ = deck_store.load_all_decks()
    assert [d.name for d in prefs.apply_deck_order(decks)] == ["Beta"]


def test_corrupt_prefs_file_is_ignored():
    from deckapp.core import prefs
    from deckapp.core.paths import get_config_dir

    (get_config_dir() / "prefs.json").write_text("{{{", encoding="utf-8")
    assert prefs.get_deck_order() == []
