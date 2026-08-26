"""Importing and housekeeping of button icons.

Icons are content-addressed: the same image picked twice lands in the same
file, so editing a button repeatedly can never fill the disk with copies.
"""
import hashlib
import logging
from pathlib import Path

from deckapp.core.paths import (get_icons_dir, is_stored_asset, resolve_asset,
                                to_relative_asset)

logger = logging.getLogger(__name__)

MAX_ICON_BYTES = 4 * 1024 * 1024  # 4 MB is plenty for a button icon
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".bmp", ".gif", ".ico"}


class IconError(Exception):
    pass


def import_icon(source_path: str) -> str:
    """Copy an image into the managed icons dir. Returns a relative asset path."""
    source = Path(source_path).expanduser()

    if is_stored_asset(str(source)):
        # Already ours — reuse it instead of making another copy.
        return to_relative_asset(str(source))

    try:
        if not source.is_file():
            raise IconError("That file no longer exists.")
        size = source.stat().st_size
    except OSError as e:
        raise IconError(f"Could not read the image: {e.strerror or e}") from e

    if size == 0:
        raise IconError("That file is empty.")
    if size > MAX_ICON_BYTES:
        raise IconError("Image is too large (limit is 4 MB).")

    suffix = source.suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise IconError("Unsupported image type. Use PNG, JPEG, SVG or WebP.")

    try:
        data = source.read_bytes()
    except OSError as e:
        raise IconError(f"Could not read the image: {e.strerror or e}") from e

    digest = hashlib.sha256(data).hexdigest()[:16]
    dest = get_icons_dir() / f"{digest}{suffix}"

    if not dest.exists():
        try:
            dest.write_bytes(data)
        except OSError as e:
            raise IconError(f"Could not save the icon: {e.strerror or e}") from e

    return f"icons/{dest.name}"


def prune_unused_icons(used: set) -> int:
    """Delete icons no deck references any more. Returns how many were removed."""
    used_names = {Path(rel).name for rel in used if rel}
    removed = 0
    try:
        entries = list(get_icons_dir().iterdir())
    except OSError as e:
        logger.warning("Could not scan the icons dir: %s", e)
        return 0

    for entry in entries:
        if not entry.is_file() or entry.name in used_names:
            continue
        if entry.suffix.lower() not in ALLOWED_SUFFIXES:
            continue
        try:
            entry.unlink()
            removed += 1
        except OSError as e:
            logger.warning("Could not remove unused icon %s: %s", entry.name, e)
    return removed


def looks_opaque(relative_or_path: str) -> bool:
    """True if an image has no transparent pixels worth speaking of.

    Buttons look best with a cut-out subject, and a very common mistake is
    saving the transparency *preview* (the grey checkerboard) as a flat image.
    Sampled rather than scanned: these are photos-sized files sometimes.
    """
    path = relative_or_path
    if not Path(path).is_absolute():
        path = resolve_asset(relative_or_path)

    # Imported here, not at module scope: core stays usable without GTK
    # (the MCP server and the tests run in plain Python).
    try:
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf
    except (ImportError, ValueError):
        logger.debug("GdkPixbuf unavailable; skipping the opacity check")
        return False

    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(path))
    except Exception as e:
        logger.debug("Could not inspect %s: %s", path, e)
        return False

    if not pixbuf.get_has_alpha():
        return True

    pixels = pixbuf.get_pixels()
    stride = pixbuf.get_rowstride()
    channels = pixbuf.get_n_channels()
    width, height = pixbuf.get_width(), pixbuf.get_height()
    if channels < 4 or not pixels:
        return True

    steps = 24
    for row in range(steps):
        y = min(height - 1, row * height // steps)
        for col in range(steps):
            x = min(width - 1, col * width // steps)
            offset = y * stride + x * channels + 3
            if offset < len(pixels) and pixels[offset] < 250:
                return False        # found real transparency
    return True
