#!/usr/bin/env python3
"""Render the tray menu's play glyph to PNG.

Drawn with cairo so the corners get real round joins — a plain polygon has
needle-sharp points that look harsh at menu size.
"""
import os
import sys

import cairo

SIZE = 32
GREY = 0x8b / 255
CORNER = 6.0          # how much the points are rounded off
# Small insets: the glyph fills the canvas, so it reads large even
# after the shell scales it down to menu size.
INSET_X, INSET_Y = 6.5, 5.0

out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "assets", "app")
path = os.path.join(out_dir, "deck-play.png")

surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
ctx = cairo.Context(surface)
ctx.set_source_rgba(GREY, GREY, GREY, 1.0)
ctx.set_line_join(cairo.LINE_JOIN_ROUND)
ctx.set_line_cap(cairo.LINE_CAP_ROUND)
ctx.set_line_width(CORNER)

# The triangle is drawn inset by half the line width, then stroked *and*
# filled: the stroke rounds the corners back out to the intended size.
half = CORNER / 2
ctx.move_to(INSET_X + half, INSET_Y + half)
ctx.line_to(SIZE - INSET_X - half, SIZE / 2)
ctx.line_to(INSET_X + half, SIZE - INSET_Y - half)
ctx.close_path()
ctx.fill_preserve()
ctx.stroke()

surface.write_to_png(path)
print(f"wrote {path} ({SIZE}×{SIZE})", file=sys.stderr)
