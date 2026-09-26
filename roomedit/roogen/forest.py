#!/usr/bin/env python3
"""
forest.py -- generate a Fey Forest room for the Quilicia Wood.

A forest room is almost the opposite of a cave, and the shipped ones say so
plainly.  a1.roo ("North Quilicia Wood") has 17 sectors and every one of them is
identical: floor 2303, `ceiling_type = 0` (open sky), floor height 128, ceiling
256, light 192.  It is flat open ground with thickets standing in it -- the
drama comes from the FeyForest karma system, not the terrain.  So this reuses
the cave machinery with the height fields switched off.

What FeyForest requires of the geometry, which is easy to miss:

    SetRoomKarma() repaints the forest by SIDEDEF ID --
        ChangeTexture(id=2, karma2)   karma2 = 8859 + 2*karma
        ChangeTexture(id=3, karma3)   karma3 = 8860 + 2*karma
        ChangeTexture(id=1, 8871 when KVERY_EVIL, else karma2)

    so the walls must carry ids 1, 2 and 3 or the room simply will not respond
    to the wood's mood.  Textures run 8861..8870 across KVERY_EVIL..KVERY_GOOD,
    with 8871 as the special blighted wall.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cave as C
from generate import RoomBuilder

FOREST_FLOOR = 2303       # grass, from a1.roo
SKY = 0                   # ceiling_type 0 == open sky
# a1.roo ships 8869/8870/8871 -- the KVERY_GOOD end of the gradient -- as its
# baseline, and 8869 carries 425 of its ~700 walls.  Do not pick a mid-gradient
# number instead: WF_NO_VTILE (0x200) means the texture is drawn ONCE rather than
# tiled, so a texture that does not fill the wall leaves sky showing through it.
TREE_MAIN = 8869          # id=2, the treeline
TREE_ALT = 8870           # id=3
TREE_BLIGHT = 8871        # id=1, swapped in at KVERY_EVIL

# 0x222 = TRANSPARENT | NOLOOKTHROUGH | NO_VTILE -- a1's solid treeline.
# a1 also has id=3 walls at 0x20e/0x20f, which are PASSABLE: those are trees
# standing INSIDE the clearing, not its edge.  Every wall this generator emits is
# the room boundary, so they all have to stay solid or players walk out.
FOREST_WALL_FLAGS = 0x222


def build_forest(room_id, seed=1, n=52, cell=56, fill=0.42, steps=4,
                 floor_h=128, ceil_h=256, light=192, margin=192,
                 exits=(), exit_width=4, chamfer=0.5):
    rnd = random.Random(seed)
    g = C._automata(n, fill, steps, rnd)
    g, keep = C._largest_blob(g, n)
    keep = set(keep)

    # `exits` names SERVER directions.  The cell grid's row axis is inverted
    # relative to them -- ey() grows with the cell row while RoomBuilder.cy()
    # flips Y, so cell row 0 ends up at the SOUTH of the finished room.  Translate
    # once here rather than reasoning about it at every use; getting this wrong
    # puts the corridor at the opposite end of the room from the exit.
    GRID_SIDE = {"N": "S", "S": "N", "E": "E", "W": "W"}
    entries, mouths = {}, {}
    for side in exits:
        gs = GRID_SIDE[side]
        e, m = C._carve_exit(g, keep, n, gs, width=exit_width)
        entries[side], mouths[gs] = e, m
    if len(keep) < (n * n) // 8:
        raise ValueError("forest came out too small; try another seed")

    xs = [x for (x, y) in keep]
    ys = [y for (x, y) in keep]
    x0c, x1c = min(xs), max(xs) + 1
    y0c, y1c = min(ys), max(ys) + 1

    def ex(cx):
        return int(round((cx - x0c) * cell))

    def ey(cy):
        return int(round((cy - y0c) * cell))

    tb_l = ex(x0c) - margin
    tb_r = ex(x1c) + margin
    tb_b = ey(y0c) - margin
    tb_t = ey(y1c) + margin
    if "W" in exits:
        tb_l = ex(1.5)
    if "E" in exits:
        tb_r = ex(n - 2.5)
    if "N" in exits:          # server north == high cell row
        tb_t = ey(n - 2.5)
    if "S" in exits:          # server south == cell row 0
        tb_b = ey(1.5)

    b = RoomBuilder((tb_l, tb_b, tb_r, tb_t), room_id=room_id)

    # One flat sector for the whole clearing -- exactly what a1 does.
    sec = b.add_sector(FOREST_FLOOR, SKY, floor_h, ceil_h, light)

    # Three karma-swappable wall sidedefs.  Without ids 1/2/3 the room will not
    # darken or brighten with the forest.
    sd_evil = b.add_sidedef(TREE_BLIGHT, flags=FOREST_WALL_FLAGS, sid=1)
    sd_a = b.add_sidedef(TREE_MAIN, flags=FOREST_WALL_FLAGS, sid=2)
    sd_b = b.add_sidedef(TREE_ALT, flags=FOREST_WALL_FLAGS, sid=3)

    def rock(x, y):
        return x < 0 or y < 0 or x >= n or y >= n or g[y][x]

    def cell_polygon(x, y):
        c = chamfer
        pts = []
        if rock(x, y - 1) and rock(x - 1, y):
            pts += [(x, y + c), (x + c, y)]
        else:
            pts += [(x, y)]
        if rock(x, y - 1) and rock(x + 1, y):
            pts += [(x + 1 - c, y), (x + 1, y + c)]
        else:
            pts += [(x + 1, y)]
        if rock(x, y + 1) and rock(x + 1, y):
            pts += [(x + 1, y + 1 - c), (x + 1 - c, y + 1)]
        else:
            pts += [(x + 1, y + 1)]
        if rock(x, y + 1) and rock(x - 1, y):
            pts += [(x + c, y + 1), (x, y + 1 - c)]
        else:
            pts += [(x, y + 1)]
        return pts

    def neighbour_of(x, y, p, q):
        if abs(p[0] - q[0]) > 1e-9 and abs(p[1] - q[1]) > 1e-9:
            return None
        if abs(p[1] - q[1]) < 1e-9:
            return (x, y - 1) if abs(p[1] - y) < 1e-9 else (x, y + 1)
        return (x - 1, y) if abs(p[0] - x) < 1e-9 else (x + 1, y)

    open_area = 0.0
    wall_rnd = random.Random(seed * 7919)

    for y in range(n):
        for x in range(n):
            if g[y][x]:
                continue
            poly = cell_polygon(x, y)
            acc = 0.0
            for k in range(len(poly)):
                ax, ay = poly[k]
                bx, by = poly[(k + 1) % len(poly)]
                acc += ex(ax) * ey(by) - ex(bx) * ey(ay)
            open_area += abs(acc) / 2.0 * (16 * 16)

            for i in range(len(poly)):
                p = poly[i]
                q = poly[(i + 1) % len(poly)]
                if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9:
                    continue
                nb = neighbour_of(x, y, p, q)
                if nb is not None and (nb[0] < 0 or nb[1] < 0
                                       or nb[0] >= n or nb[1] >= n):
                    side = ("W" if nb[0] < 0 else "E" if nb[0] >= n
                            else "N" if nb[1] < 0 else "S")
                    if (x, y) in mouths.get(side, ()):
                        continue
                if nb is not None and not rock(nb[0], nb[1]):
                    continue                      # same sector: no wall at all

                # Spread the three karma ids over the treeline so the whole
                # forest changes together when the mood does.
                roll = wall_rnd.random()
                # a1's mix: id=2 ~60%, id=3 ~34%, id=1 ~2%
                sd = sd_evil if roll < 0.02 else (sd_a if roll < 0.64 else sd_b)

                inside = (ex((p[0] + q[0]) * 0.5 + (x + 0.5 - (p[0] + q[0]) * 0.5) * 0.35),
                          ey((p[1] + q[1]) * 0.5 + (y + 0.5 - (p[1] + q[1]) * 0.5) * 0.35))
                b.add_wall_facing(ex(p[0]), ey(p[1]), ex(q[0]), ey(q[1]),
                                  inside, sd, sec)

    C._merge_collinear(b)
    room = b.build()

    entry_squares = {}
    for side, (cy, cx) in entries.items():
        client_x = (ex(cx + 0.5) - tb_l) * 16
        client_y = (tb_t - ey(cy + 0.5)) * 16
        entry_squares[side] = (int(client_y // 1024), int(client_x // 1024))

    # generator / teleport spots: the biggest open leaves
    leaves = []
    for nd in room.bsp.walk():
        if nd.type == 2 and nd.sector > 0:
            px = [q[0] for q in nd.points]
            py = [q[1] for q in nd.points]
            leaves.append(((max(px) - min(px)) * (max(py) - min(py)),
                           int(sum(py) / len(py) // 1024),
                           int(sum(px) / len(px) // 1024)))
    leaves.sort(reverse=True)

    return room, open_area, entry_squares, leaves


def main():
    room, area, entries, leaves = build_forest(room_id=0, seed=3, exits=("N",))
    print("sectors=%d walls=%d  %dx%d squares  entries=%s"
          % (len(room.sectors), len(room.linedefs),
             room.width // 1024, room.height // 1024, entries))
    return 0


if __name__ == "__main__":
    sys.exit(main())
