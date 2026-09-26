#!/usr/bin/env python3
"""
showcase.py -- a texture sample hall built from out/texture_catalog.csv, for
looking at in the room editor (not wired into the game).

Layout (editor units): a 2048 x 1024 hall.
  * north and south walls: 8 panels, 256 wide, each a different wall texture
  * west and east walls: one panel each
  * a row of 256x256 floor patches down the middle, each a different floor
    texture, level with the hall floor (two-sided passable walls, no texture)
  * ceiling: the most used ceiling texture

Usage:  python roomedit/roogen/showcase.py      (run from the repo root;
        run texcatalog.py first)
Writes: out/texture_showcase.roo and out/texture_showcase.txt (the legend)
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from generate import RoomBuilder  # noqa: E402
from roofile import Room  # noqa: E402

WF_PASSABLE = 0x04
WF_MAP_NEVER = 0x08

PANEL = 256
PANELS_PER_SIDE = 8
DEPTH = 1024
FLOOR_PATCHES = 6
FLOORH, CEILH = 0, 256
LIGHT = 192


def top(rows, category, n, skip=()):
    picks = [r for r in rows if r["category"] == category
             and r["missing_file"] == "False" and int(r["texture"]) not in skip]
    picks.sort(key=lambda r: -int(r["rooms"]))
    return [int(r["texture"]) for r in picks[:n]]


def main():
    with open(os.path.join(HERE, "out", "texture_catalog.csv")) as fh:
        rows = list(csv.DictReader(fh))

    walls = top(rows, "wall", PANELS_PER_SIDE * 2 + 2)
    floors = top(rows, "floor", FLOOR_PATCHES + 1)
    ceiling = top(rows, "ceiling", 1)[0]
    hall_floor, patch_floors = floors[0], floors[1:]

    width = PANEL * PANELS_PER_SIDE
    margin = 64
    b = RoomBuilder((-margin, -margin, width + margin, DEPTH + margin))
    hall = b.add_sector(hall_floor, ceiling, FLOORH, CEILH, LIGHT)
    centre = (width / 2, DEPTH / 2)
    legend = ["Texture showcase -- editor units, north is +Y", "",
              "hall floor %d, ceiling %d" % (hall_floor, ceiling), ""]

    wi = iter(walls)
    # north (y = DEPTH) and south (y = 0) panels, west to east
    for side, y in (("north", DEPTH), ("south", 0)):
        for i in range(PANELS_PER_SIDE):
            tex = next(wi)
            x0, x1 = i * PANEL, (i + 1) * PANEL
            b.add_wall_facing(x0, y, x1, y, centre, b.add_sidedef(tex), hall)
            legend.append("%s wall panel %d (x %d-%d): %d" % (side, i + 1, x0, x1, tex))
    for side, x in (("west", 0), ("east", width)):
        tex = next(wi)
        b.add_wall_facing(x, 0, x, DEPTH, centre, b.add_sidedef(tex), hall)
        legend.append("%s wall: %d" % (side, tex))

    # floor patches, centred on the hall's long axis
    legend.append("")
    gap = (width - FLOOR_PATCHES * PANEL) // (FLOOR_PATCHES + 1)
    py0, py1 = DEPTH // 2 - PANEL // 2, DEPTH // 2 + PANEL // 2
    edge = WF_PASSABLE | WF_MAP_NEVER
    for i, tex in enumerate(patch_floors):
        px0 = gap + i * (PANEL + gap)
        px1 = px0 + PANEL
        sec = b.add_sector(tex, ceiling, FLOORH, CEILH, LIGHT)
        inside = ((px0 + px1) / 2, (py0 + py1) / 2)
        for (x0, y0, x1, y1) in ((px0, py0, px1, py0), (px1, py0, px1, py1),
                                 (px1, py1, px0, py1), (px0, py1, px0, py0)):
            b.add_wall_facing(x0, y0, x1, y1, inside,
                              b.add_sidedef(0, flags=edge), sec,
                              neg_sidedef=b.add_sidedef(0, flags=edge), neg_sector=hall)
        legend.append("floor patch %d (x %d-%d): %d" % (i + 1, px0, px1, tex))

    room = b.build()
    out = os.path.join(HERE, "out", "texture_showcase.roo")
    room.save(out)

    # sanity: re-read, and the rewrite must be byte-identical
    again = Room.load(out)
    with open(out, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"

    with open(os.path.join(HERE, "out", "texture_showcase.txt"), "w") as fh:
        fh.write("\n".join(legend) + "\n")
    print(again.summary())
    print("\n".join(legend))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
