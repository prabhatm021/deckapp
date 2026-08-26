#!/bin/bash
# Build a .deb for DeckApp.
#
#   ./tools/build-deb.sh
#
# Produces dist/deckapp_<version>_all.deb. Needs dpkg-deb and fakeroot, both in
# the dpkg-dev and fakeroot packages.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/__init__.py")"
APP_ID="io.github.prabhatm021.deckapp"

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

PKGDIR="$STAGE/usr/lib/python3/dist-packages/deckapp"
mkdir -p "$PKGDIR" \
         "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/doc/deckapp"

# ── The Python package ──
# Only what the app needs at runtime: no tests, tools, screenshots or git data.
cp "$REPO"/__init__.py "$REPO"/app.py "$PKGDIR/"
cp -r "$REPO"/core "$REPO"/ui "$PKGDIR/"
mkdir -p "$PKGDIR/assets" "$PKGDIR/decks"
cp -r "$REPO"/assets/app "$PKGDIR/assets/"
cp "$REPO"/decks/example.json "$PKGDIR/decks/"
find "$PKGDIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true

# ── Launchers ──
cat > "$STAGE/usr/bin/deckapp" <<'LAUNCHER'
#!/usr/bin/python3
import sys
from deckapp.app import main
sys.exit(main())
LAUNCHER

chmod 755 "$STAGE/usr/bin/deckapp"

# ── Desktop entry and icon ──
sed 's|^Exec=.*|Exec=deckapp|' "$REPO/packaging/$APP_ID.desktop" \
    > "$STAGE/usr/share/applications/$APP_ID.desktop"
sed -i "s|^Icon=.*|Icon=$APP_ID|" "$STAGE/usr/share/applications/$APP_ID.desktop"
cp "$REPO/assets/app/$APP_ID.svg" \
   "$STAGE/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"
cp "$REPO/LICENSE" "$STAGE/usr/share/doc/deckapp/copyright"

# ── Package metadata ──
INSTALLED_KB="$(du -sk "$STAGE" | cut -f1)"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: deckapp
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0 (>= 4.8), gir1.2-adw-1 (>= 1.2)
Recommends: gnome-shell-extension-appindicator
Suggests: python3-pytest
Installed-Size: $INSTALLED_KB
Maintainer: prabhatm021 <84736293+prabhatm021@users.noreply.github.com>
Homepage: https://github.com/prabhatm021/deckapp
Description: virtual macro pad that runs shell commands
 DeckApp is a macro pad for the Linux desktop. You build a grid of buttons,
 each one running a shell command, and open that grid as a small window with
 no title bar.
 .
 Buttons are either single, running one command per press, or toggles with
 separate ON and OFF commands that remember their state. Decks are plain JSON
 files. DeckApp can also sit in the top bar so your decks stay one click away.
CONTROL

cat > "$STAGE/DEBIAN/postinst" <<'POSTINST'
#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
    fi
fi
POSTINST

cat > "$STAGE/DEBIAN/postrm" <<'POSTRM'
#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -f /usr/share/icons/hicolor || true
    fi
fi
POSTRM
chmod 755 "$STAGE/DEBIAN/postinst" "$STAGE/DEBIAN/postrm"

# Your decks and icons live in ~/.local/share/deckapp, so removing the package
# never touches them.

mkdir -p "$REPO/dist"
DEB="$REPO/dist/deckapp_${VERSION}_all.deb"
fakeroot dpkg-deb --build "$STAGE" "$DEB" >/dev/null
echo "$DEB"
