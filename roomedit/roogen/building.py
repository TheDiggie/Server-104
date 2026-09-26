#!/usr/bin/env python3
"""
building.py -- a hand-designed building interior ("the keep"), laid out as
rectangles on a cell grid and turned into a real .roo: sectors, one-sided walls,
two-sided step/lintel walls, pillars, stairs, and the BSP.

For opening in the room editor; not wired into the game.

Palette borrowed from Barloque castle (castle1 / castle1c) so it reads as a
Meridian building rather than a texture sampler.

Layout (cells, x to the right, row 0 at the top of this plan):
  * entrance vestibule (south) -> low doorway -> GREAT HALL
  * great hall: tall ceiling, two rows of pillars, a sunken hearth in the middle,
    three steps up to a dais, and a throne alcove behind it
  * west corridor off the hall -> library (north) and barracks (south),
    each through its own doorway
  * east corridor -> a flight of stairs down -> kitchen -> storeroom

Usage:  python roomedit/roogen/building.py          (run from the repo root)
Writes: out/keep_interior.roo, out/keep_interior.txt
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from generate import RoomBuilder  # noqa: E402
from cave import _merge_collinear, MAX_STEP, HEADROOM, STEP_FLAGS  # noqa: E402
from roofile import Room, BSP_LEAF  # noqa: E402

CELL = 32          # editor units per cell (half a server square)
W, H = 80, 56      # plan size in cells
MARGIN = 128

# Barloque castle palette
STONE_FLOOR = 2104
HALL_CEIL = 2016
HALL_WALL = 2103
FLAG_FLOOR = 4601
PLAIN = 2011
DAIS_FLOOR = 4410
TILE_FLOOR = 2123
WOOD = 1602
PANEL_WALL = 2012
BRICK_FLOOR = 3101
PILLAR = 4407
DARK_STONE = 1701


class Zone:
    def __init__(self, name, floorh, ceilh, floor, ceil, wall, light=160, trim=None):
        self.name = name
        self.floorh, self.ceilh = floorh, ceilh
        self.floor, self.ceil, self.wall = floor, ceil, wall
        self.trim = trim or wall
        self.light = light

    def key(self):
        return (self.floorh, self.ceilh, self.floor, self.ceil, self.light)


def plan():
    """Paint the plan.  Later rectangles override earlier ones.
    Each cell is a Zone, or a str 'solid:<texture>' for pillars, or None."""
    g = [[None] * W for _ in range(H)]
    legend = []

    def rect(x0, y0, x1, y1, z):
        """inclusive cell rectangle"""
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                g[y][x] = z
        if isinstance(z, Zone) and z.name not in [l[0] for l in legend]:
            legend.append((z.name, x0, y0, x1, y1, z))

    # --- great hall and its parts
    hall = Zone("great hall", 128, 352, STONE_FLOOR, HALL_CEIL, HALL_WALL, light=200)
    rect(20, 19, 60, 46, hall)
    rect(30, 23, 50, 23, Zone("dais step 1", 144, 352, TILE_FLOOR, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    rect(30, 22, 50, 22, Zone("dais step 2", 160, 352, TILE_FLOOR, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    rect(30, 19, 50, 21, Zone("dais", 176, 352, DAIS_FLOOR, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    # stone rails down both sides, so the dais is only climbed from the front
    # (otherwise the hall floor meets the upper step and dais directly: 32/48 steps)
    rect(29, 19, 29, 22, "solid:%d" % PILLAR)
    rect(51, 19, 51, 22, "solid:%d" % PILLAR)
    rect(36, 14, 44, 18, Zone("throne alcove", 176, 272, DAIS_FLOOR, WOOD, PANEL_WALL, 180))
    rect(36, 32, 44, 36, Zone("sunken hearth", 112, 352, DARK_STONE, HALL_CEIL, HALL_WALL, 220, trim=PILLAR))
    for py in (27, 40):
        for px in (24, 30, 49, 55):
            rect(px, py, px + 1, py + 1, "solid:%d" % PILLAR)

    # --- entrance
    rect(34, 48, 46, 55, Zone("entrance vestibule", 128, 224, FLAG_FLOOR, PLAIN, PLAIN, 150))
    rect(37, 47, 43, 47, Zone("hall doorway", 128, 208, FLAG_FLOOR, PLAIN, PLAIN, 150))

    # --- west wing
    rect(2, 30, 19, 34, Zone("west corridor", 128, 208, FLAG_FLOOR, PLAIN, PLAIN, 140))
    rect(2, 8, 17, 28, Zone("library", 136, 240, TILE_FLOOR, PLAIN, PANEL_WALL, 150))
    rect(8, 29, 11, 29, Zone("library doorway", 132, 200, TILE_FLOOR, PLAIN, PLAIN, 140))
    rect(2, 36, 17, 53, Zone("barracks", 120, 216, BRICK_FLOOR, HALL_CEIL, PLAIN, 130))
    rect(8, 35, 11, 35, Zone("barracks doorway", 124, 200, BRICK_FLOOR, PLAIN, PLAIN, 130))

    # --- east wing: corridor, stairs down, kitchen, storeroom
    rect(61, 26, 66, 30, Zone("east corridor", 128, 208, FLAG_FLOOR, PLAIN, PLAIN, 140))
    for i in range(4):
        fh = 112 - 16 * i
        rect(67 + i, 26, 67 + i, 30,
             Zone("stairs step %d" % (i + 1), fh, fh + 128, BRICK_FLOOR, PLAIN, PLAIN, 130, trim=PILLAR))
    rect(71, 10, 78, 50, Zone("kitchen", 64, 208, DARK_STONE, WOOD, PILLAR, 140))
    # starts at x62: a column of solid wall keeps it off the hall's east side
    rect(62, 36, 69, 50, Zone("storeroom", 64, 160, DARK_STONE, PLAIN, PLAIN, 110))
    rect(70, 42, 70, 44, Zone("storeroom doorway", 64, 144, DARK_STONE, PLAIN, PLAIN, 110))
    return g, legend


def is_open(g, x, y):
    return 0 <= x < W and 0 <= y < H and isinstance(g[y][x], Zone)


def main():
    g, legend = plan()

    # sectors keyed on everything that makes two cells render differently
    b = RoomBuilder((-MARGIN, -MARGIN, W * CELL + MARGIN, H * CELL + MARGIN))
    sector_of = {}
    zone_of_sector = {}
    for row in g:
        for z in row:
            if isinstance(z, Zone) and z.key() not in sector_of:
                sid = b.add_sector(z.floor, z.ceil, z.floorh, z.ceilh, z.light)
                sector_of[z.key()] = sid
                zone_of_sector[sid] = z

    sidedefs = {}

    def sidedef(normal, above=0, below=0, flags=0):
        k = (normal, above, below, flags)
        if k not in sidedefs:
            sidedefs[k] = b.add_sidedef(normal, above=above, below=below, flags=flags)
        return sidedefs[k]

    def facing(view, other):
        """sidedef seen from `view` looking across into `other`"""
        below = other.trim if other.floorh > view.floorh else 0
        above = view.wall if other.ceilh < view.ceilh else 0
        return sidedef(0, above=above, below=below, flags=STEP_FLAGS)

    # movement rules check (blakserv BSPCanMoveInRoomTreeInternal)
    problems = []
    open_cells = 0
    for y in range(H):
        for x in range(W):
            z = g[y][x]
            if not isinstance(z, Zone):
                continue
            open_cells += 1
            if z.ceilh - z.floorh < HEADROOM:
                problems.append("%s: headroom %d" % (z.name, z.ceilh - z.floorh))
            mine = sector_of[z.key()]
            for (dx, dy, p, q) in ((0, -1, (x, y), (x + 1, y)),
                                   (1, 0, (x + 1, y), (x + 1, y + 1)),
                                   (0, 1, (x + 1, y + 1), (x, y + 1)),
                                   (-1, 0, (x, y + 1), (x, y))):
                nx, ny = x + dx, y + dy
                inside = ((p[0] + q[0]) / 2 * CELL + (x + 0.5 - (p[0] + q[0]) / 2) * CELL * 0.35,
                          (p[1] + q[1]) / 2 * CELL + (y + 0.5 - (p[1] + q[1]) / 2) * CELL * 0.35)
                x0, y0, x1, y1 = p[0] * CELL, p[1] * CELL, q[0] * CELL, q[1] * CELL
                if not is_open(g, nx, ny):
                    cell = g[ny][nx] if 0 <= nx < W and 0 <= ny < H else None
                    tex = int(cell.split(":")[1]) if isinstance(cell, str) else z.wall
                    b.add_wall_facing(x0, y0, x1, y1, inside, sidedef(tex), mine)
                    continue
                o = g[ny][nx]
                other = sector_of[o.key()]
                if other == mine or (ny, nx) < (y, x):
                    continue
                for a, c in ((z, o), (o, z)):
                    if c.floorh - a.floorh > MAX_STEP:
                        problems.append("%s -> %s: step %d" % (a.name, c.name, c.floorh - a.floorh))
                    if c.ceilh - a.floorh < HEADROOM:
                        problems.append("%s -> %s: clearance %d" % (a.name, c.name, c.ceilh - a.floorh))
                b.add_wall_facing(x0, y0, x1, y1, inside, facing(z, o), mine,
                                  neg_sidedef=facing(o, z), neg_sector=other)

    if problems:
        print("movement rule problems:")
        for pr in sorted(set(problems)):
            print("  ", pr)
        return 1

    _merge_collinear(b)   # needs the shared sidedef ids to know what may join

    # Then give every wall side its own sidedef, so retexturing one wall in the
    # room editor doesn't change every other wall that happened to share it.
    shared = b.sidedefs
    b.sidedefs = []

    def own_copy(ref):
        if not ref:
            return 0
        src = shared[ref - 1]
        return b.add_sidedef(src.type_normal, above=src.type_above,
                             below=src.type_below, flags=src.flags)

    b.walls = [(x0, y0, x1, y1, own_copy(sd), sec, own_copy(nsd), nsec)
               for (x0, y0, x1, y1, sd, sec, nsd, nsec) in b.walls]
    room = b.build()

    # seal: floor area covered by sector leaves must equal the open cells exactly
    leaf_area = 0.0
    for n in room.bsp.walk():
        if n.type == BSP_LEAF and n.sector:
            pts = n.points
            acc = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                      for i in range(len(pts)))
            leaf_area += abs(acc) / 2
    cell_area = open_cells * (CELL * 16) ** 2
    seal = leaf_area / cell_area
    assert abs(seal - 1.0) < 1e-6, "room is not sealed: leaf/cell area = %f" % seal

    out = os.path.join(HERE, "out", "keep_interior.roo")
    room.save(out)
    again = Room.load(out)
    with open(out, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"

    lines = ["The keep -- %d x %d editor units, %d cells of floor" % (W * CELL, H * CELL, open_cells),
             "coordinates below are editor units (x, y); the plan's row 0 is at the top", ""]
    for name, x0, y0, x1, y1, z in legend:
        lines.append("%-20s x %4d-%-4d y %4d-%-4d floor h %3d  ceiling h %3d  floor %d  ceiling %d  walls %d"
                     % (name, x0 * CELL, (x1 + 1) * CELL, y0 * CELL, (y1 + 1) * CELL,
                        z.floorh, z.ceilh, z.floor, z.ceil, z.wall))
    lines.append("pillars: texture %d" % PILLAR)
    with open(os.path.join(HERE, "out", "keep_interior.txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print(again.summary())
    print("sectors %d, walls %d, sidedefs %d, seal %.6f, movement problems 0"
          % (len(room.sectors), len(room.linedefs), len(room.sidedefs), seal))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
