"""Shared UI helpers.

DeckApp targets libadwaita 1.2 / GTK 4.8 (Debian bookworm) but must also run
cleanly on newer releases where some of those APIs are deprecated. The helpers
below pick the best widget available at runtime.
"""
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, Gtk, Pango  # noqa: E402

_css_loaded = False


def load_css():
    """Load the app-specific CSS once per process."""
    global _css_loaded
    if _css_loaded:
        return
    css_path = Path(__file__).resolve().parent / "style.css"
    display = Gdk.Display.get_default()
    if display is None:
        return
    provider = Gtk.CssProvider()
    try:
        provider.load_from_path(str(css_path))
    except Exception:
        return
    Gtk.StyleContext.add_provider_for_display(
        display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )
    _css_loaded = True


# ── Dialogs ──

SUGGESTED = Adw.ResponseAppearance.SUGGESTED
DESTRUCTIVE = Adw.ResponseAppearance.DESTRUCTIVE
NEUTRAL = Adw.ResponseAppearance.DEFAULT


def alert(parent, heading, body, responses, on_response=None,
          default=None, close=None):
    """Message dialog.

    `responses` is a list of (id, label, appearance) tuples; `on_response(id)`
    fires with the chosen id. Uses Adw.AlertDialog where available and falls
    back to Adw.MessageDialog on libadwaita < 1.5.
    """
    alert_cls = getattr(Adw, "AlertDialog", None)
    if alert_cls is not None:  # libadwaita >= 1.5
        dialog = alert_cls(heading=heading, body=body)
    else:
        dialog = Adw.MessageDialog(
            transient_for=_window_of(parent), heading=heading, body=body
        )

    for response_id, label, appearance in responses:
        dialog.add_response(response_id, label)
        if appearance is not None:
            dialog.set_response_appearance(response_id, appearance)

    first = responses[0][0]
    dialog.set_default_response(default or first)
    dialog.set_close_response(close or first)

    if on_response is not None:
        dialog.connect("response", lambda _d, response_id: on_response(response_id))

    if alert_cls is not None:
        dialog.present(parent)
    else:
        dialog.present()
    return dialog


def confirm(parent, heading, body, confirm_label, on_confirm,
            destructive=True, cancel_label="Cancel"):
    """Yes/no dialog. `on_confirm()` runs only if the user confirms."""
    return alert(
        parent, heading, body,
        [
            ("cancel", cancel_label, None),
            ("confirm", confirm_label, DESTRUCTIVE if destructive else SUGGESTED),
        ],
        on_response=lambda response: on_confirm() if response == "confirm" else None,
    )


def show_error(parent, heading, body):
    return alert(parent, heading, body, [("ok", "OK", None)])


def _window_of(widget):
    if widget is None:
        return None
    if isinstance(widget, Gtk.Window):
        return widget
    root = widget.get_root()
    return root if isinstance(root, Gtk.Window) else None


# ── File chooser ──

def _image_filters():
    store = Gio.ListStore.new(Gtk.FileFilter)
    images = Gtk.FileFilter()
    images.set_name("Images")
    for pattern in ("*.png", "*.jpg", "*.jpeg", "*.svg", "*.webp",
                    "*.bmp", "*.gif", "*.ico"):
        images.add_pattern(pattern)
    store.append(images)
    all_files = Gtk.FileFilter()
    all_files.set_name("All files")
    all_files.add_pattern("*")
    store.append(all_files)
    return store, images, all_files


def choose_image(parent, on_chosen):
    """Open an image picker. `on_chosen(path)` runs with the selected path."""
    window = _window_of(parent)
    filters, images, _all = _image_filters()

    file_dialog_cls = getattr(Gtk, "FileDialog", None)
    if file_dialog_cls is not None:  # GTK >= 4.10
        dialog = file_dialog_cls()
        dialog.set_title("Choose Icon")
        dialog.set_filters(filters)
        dialog.set_default_filter(images)

        def _ready(source, result, _data=None):
            try:
                gfile = source.open_finish(result)
            except Exception:
                return  # dismissed
            if gfile and gfile.get_path():
                on_chosen(gfile.get_path())

        dialog.open(window, None, _ready)
        return dialog

    # GTK 4.8 — native chooser so the portal/file manager dialog is used
    dialog = Gtk.FileChooserNative.new(
        "Choose Icon", window, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel"
    )
    dialog.set_modal(True)
    dialog.add_filter(images)
    dialog.set_filter(images)

    def _response(chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            gfile = chooser.get_file()
            if gfile and gfile.get_path():
                on_chosen(gfile.get_path())
        chooser.destroy()
        # Drop the reference we parked on the parent
        if getattr(parent, "_deckapp_file_chooser", None) is chooser:
            parent._deckapp_file_chooser = None

    dialog.connect("response", _response)
    # Gtk.FileChooserNative is not a widget — keep it alive ourselves
    if parent is not None:
        parent._deckapp_file_chooser = dialog
    dialog.show()
    return dialog


# ── Tiles ──

# The box an icon is scaled into, with and without a label under it.
# Gtk.Image keeps the aspect ratio inside this box, so a wide logo fills the
# width of the tile rather than sitting tiny in the middle.
ICON_WITH_LABEL = 54
ICON_ALONE = 68


def make_tile_content(button, icon_size=None, max_chars=10):
    """The icon + label box shown inside a deck tile."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.set_halign(Gtk.Align.CENTER)
    box.set_valign(Gtk.Align.CENTER)

    icon_path = button.icon_path
    if icon_path:
        size = icon_size or (ICON_WITH_LABEL if button.label else ICON_ALONE)
        # Gtk.Image, not Gtk.Picture: a Picture reports the whole image as its
        # natural size, which stretches the tile to the image's width.
        image = Gtk.Image.new_from_file(icon_path)
        image.set_pixel_size(size)
        box.append(image)
    elif not button.label:
        image = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        image.set_pixel_size(icon_size or 36)
        image.add_css_class("dim-label")
        box.append(image)

    if button.label:
        label = Gtk.Label(label=button.label)
        label.set_justify(Gtk.Justification.CENTER)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(max_chars)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_lines(2)
        box.append(label)

    return box
