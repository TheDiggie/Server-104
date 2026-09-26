#!/usr/bin/env python3
"""
library.py -- "The Barloque Library": a building interior meant to sit among
Barloque's real ones.  Built with building2.emit(); for the room editor, not
wired into the game.

Everything stylistic was measured from the ten Barloque interiors (barinn,
barlbar1, barcourt, barapoth, barmerch, barsmith, barjail, barvault, barhall,
barrent) and checked by rendering the textures, rather than picked by number:

  * size: ~1250 x 930 editor units, like the inn (1024x1056) and the Bhrama &
    Falcon (1504x1408); mostly axis-aligned walls
  * base floor 128; rooms ~128-240 tall; dim OWN light (<128) like barinn 67 /
    barlbar1 80; a flickering spot (0x200 is the common Barloque sector flag)
  * palette: green mossy stone 2001/2005, sandstone 2021, dark stone 2031, wood
    3101/4601/4610, wood panel 3102, red carpet 1018, bookshelf 7601
  * ceiling beams: strips 32 wide with the ceiling 16 lower in 4610, exactly the
    Bhrama & Falcon's (sectors 4/7: ceiling 240 against 256)
  * banner niches (4802-4807 are heraldic banners, not windows): 96 wide, 32
    deep, floor +32, 48-unit opening, as barlbar1 sector 35 / barinn 22
  * stairs: 16 rises, 32 deep (barinn sectors 15-21)
  * shelves/desks/rails are raised blocks the player cannot climb; a shelf is
    exactly one bookshelf texture (128) tall so it is not cropped

Usage:  python roomedit/roogen/library.py      (run from the repo root)
Writes: out/barloque_library.roo, out/barloque_library.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from building2 import Plan, Zone, Solid, emit, SF_FLICKER  # noqa: E402

GREEN_STONE, GREEN_FLOOR, SANDSTONE, DARK_STONE = 2001, 2005, 2021, 2031
WOOD_FLOOR, DARK_WOOD, WOOD_GRAIN, PANEL, PLANK_RAIL = 3101, 4601, 4610, 3102, 3701
CARPET, BOOKSHELF, DOOR = 1018, 7601, 2033
PLANKS_CEIL, GREY_WOOD = 4607, 4608
PHOENIX, FLEUR, ROSE, GRIFFIN, HORSE, LION = 4802, 4803, 4804, 4805, 4806, 4807

FLOOR = 128
LIGHT = 72


def build_plan():
    p = Plan(82, 66)

    # ---- reading hall
    hall = Zone("reading hall", FLOOR, 320, WOOD_FLOOR, GREEN_FLOOR, GREEN_STONE, LIGHT)
    carpet = Zone("carpet aisle", FLOOR, 320, CARPET, GREEN_FLOOR, GREEN_STONE, LIGHT)
    p.rect(16, 18, 63, 49, hall)
    p.rect(36, 24, 43, 49, carpet)

    # ---- gallery across the north end, three steps up, railed
    gallery = Zone("gallery", 176, 320, WOOD_GRAIN, GREEN_FLOOR, GREEN_STONE, LIGHT)
    p.rect(16, 10, 63, 17, gallery)
    p.rect(36, 10, 43, 17, Zone("gallery carpet", 176, 320, CARPET, GREEN_FLOOR, GREEN_STONE, LIGHT))
    for i, fh in enumerate((176, 160, 144)):
        p.rect(36, 18 + 2 * i, 43, 19 + 2 * i,
               Zone("gallery stair %d" % (3 - i), fh, 320, CARPET, GREEN_FLOOR, GREEN_STONE, LIGHT, trim=WOOD_GRAIN))
    rail = Zone("gallery rail", 200, 320, WOOD_GRAIN, GREEN_FLOOR, GREEN_STONE, LIGHT, trim=PLANK_RAIL, barrier=True)
    p.rect(16, 17, 34, 17, rail)
    p.rect(45, 17, 63, 17, rail)
    p.rect(35, 17, 35, 23, rail)
    p.rect(44, 17, 44, 23, rail)
    p.rect(34, 12, 45, 13, Zone("librarian's desk", 216, 320, DARK_WOOD, GREEN_FLOOR, GREEN_STONE, LIGHT,
                                trim=PANEL, barrier=True))
    for bx, tex, name in ((20, FLEUR, "fleur-de-lis"), (37, PHOENIX, "phoenix"), (54, LION, "lion")):
        p.rect(bx, 8, bx + 5, 9, Zone("gallery banner (%s)" % name, 208, 256, 0, 0, GREEN_STONE, LIGHT,
                                      barrier=True, banner=tex))

    # ---- bookshelves down both side walls, forming reading bays
    shelf = Zone("bookshelves", 256, 320, WOOD_GRAIN, GREEN_FLOOR, GREEN_STONE, LIGHT, trim=BOOKSHELF, barrier=True)
    table = Zone("reading tables", 168, 320, DARK_WOOD, GREEN_FLOOR, GREEN_STONE, LIGHT, trim=WOOD_GRAIN, barrier=True)
    for wall_x, stub_x0, stub_x1, table_x0 in ((16, 16, 23, 19), (63, 56, 63, 58)):
        for sy0, sy1 in ((18, 23), (25, 30), (37, 42), (44, 49)):
            p.rect(wall_x, sy0, wall_x, sy1, shelf)                 # shelf against the wall
        for sy in (24, 31, 36, 43):
            p.rect(stub_x0, sy, stub_x1, sy, shelf)                  # shelf sticking out into the room
        for ty in (26, 38):
            p.rect(table_x0, ty, table_x0 + 2, ty + 3, table)
    p.rect(63, 32, 63, 35, shelf)                                    # east wall only: no doorway there
    p.rect(58, 32, 60, 34, table)
    for tx in (27, 48):
        p.rect(tx, 29, tx + 4, 32, table)
        p.rect(tx, 39, tx + 4, 42, table)

    # ceiling beams across the hall (Bhrama & Falcon: 32-wide strips 16 lower, in 4610)
    beam_of = {}
    for by in (26, 34, 42):
        for yy in (by, by + 1):
            for xx in range(p.w):
                z = p.g[yy][xx]
                if z is hall or z is carpet:
                    if z.name not in beam_of:
                        beam_of[z.name] = Zone("ceiling beam", FLOOR, 304, z.floor, WOOD_GRAIN, GREEN_STONE, LIGHT)
                    p.g[yy][xx] = beam_of[z.name]
    p.legend.append(("ceiling beam", "rows y %d-%d, %d-%d, %d-%d" % (26 * 16, 28 * 16, 34 * 16, 36 * 16, 42 * 16, 44 * 16),
                     beam_of["reading hall"]))

    # ---- foyer (south) with the front door and two banners
    p.rect(32, 51, 47, 62, Zone("foyer", FLOOR, 256, DARK_WOOD, WOOD_GRAIN, SANDSTONE, LIGHT))
    p.rect(36, 50, 43, 50, Zone("hall doorway", FLOOR, 224, CARPET, WOOD_GRAIN, SANDSTONE, LIGHT))
    # Door, built like a painting: a shallow fake sector whose opening shows the
    # door texture.  grd02033 is 64 wide x 96 tall (repeat = header height/shrink),
    # so the opening is exactly 64 x 96 and the texture is neither tiled nor cut.
    p.rect(38, 63, 41, 64, Zone("front door", FLOOR, FLOOR + 96, 0, 0, SANDSTONE, LIGHT,
                                barrier=True, banner=DOOR))
    p.rect(30, 54, 31, 59, Zone("foyer banner (griffin)", 160, 208, 0, 0, SANDSTONE, LIGHT, barrier=True, banner=GRIFFIN))
    p.rect(48, 54, 49, 59, Zone("foyer banner (horse)", 160, 208, 0, 0, SANDSTONE, LIGHT, barrier=True, banner=HORSE))

    # ---- scriptorium (west), wood panelled, candlelit
    p.rect(2, 26, 13, 41, Zone("scriptorium", FLOOR, 240, CARPET, PLANKS_CEIL, PANEL, 64))
    p.rect(14, 32, 15, 35, Zone("scriptorium doorway", FLOOR, 224, WOOD_FLOOR, PLANKS_CEIL, PANEL, 64))
    desk = Zone("writing desks", 164, 240, DARK_WOOD, PLANKS_CEIL, PANEL, 64, trim=WOOD_GRAIN, barrier=True)
    for dx in (4, 9):
        for dy in (28, 37):
            p.rect(dx, dy, dx + 2, dy + 2, desk)
    p.rect(7, 33, 8, 34, Zone("candle light", FLOOR, 240, CARPET, PLANKS_CEIL, PANEL, 110, flags=SF_FLICKER))
    p.rect(0, 31, 1, 36, Zone("scriptorium banner (rose)", 144, 192, 0, 0, PANEL, 64, barrier=True, banner=ROSE))

    # ---- archive (behind the gallery, east), dark stone, freestanding stacks
    p.rect(66, 6, 77, 25, Zone("archive", 176, 368, WOOD_GRAIN, GREY_WOOD, DARK_STONE, 56))
    p.rect(64, 12, 65, 15, Zone("archive doorway", 176, 256, WOOD_GRAIN, GREY_WOOD, DARK_STONE, 60))
    stack = Zone("archive stacks", 304, 368, WOOD_GRAIN, GREY_WOOD, DARK_STONE, 56, trim=BOOKSHELF, barrier=True)
    for sx in (69, 73):
        p.rect(sx, 9, sx + 1, 20, stack)
    return p


def main():
    return emit(build_plan(), "barloque_library", "The Barloque Library")


if __name__ == "__main__":
    sys.exit(main())
