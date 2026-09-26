#!/usr/bin/env python3
"""
jungle.py -- Ko'catan jungle rooms.  build_jungle() turns a trail layout into a
checked room of any width and height; run directly it builds "The Overgrown
Glade" for the empty kd5 slot of the kcforest grid (south of kd4, east of kc5).
style_jungle.py feeds it random layouts for the map generator app.

Construction copied from the shipped jungle rooms (kb3, kc2, kd3, kc4), not
invented:
  * room box 49x49 squares for a normal jungle room; there, trails run past the
    box and are capped (the app instead keeps everything inside the box)
  * one ground sector: floor 500, 9069 mossy floor, canopy 9068 at 756, light
    178; open-sky clearings have no ceiling texture at 810
  * jungle wall: one-sided 9089 at 0x22a
  * bush line ~72 inside the jungle wall: two-sided 9070, same sector both
    sides; the side facing the jungle wall is the LEFT of x0->x1 and carries
    0x202, the trail side 0x207 (222 of 222 such walls in kb3)
  * canopy/sky edge: canopy side 9100 at 0xe, sky side 9067 above at 0x2e
  * trails ~190-220 wide, clearings up to ~750
  * shallow pond like kc5's: pale water 1802, a little below the ground, depth 1

Geometry: trails are painted onto a 16-unit grid as wobbling splines, the
edges traced (marching squares), smoothed and simplified (Douglas-Peucker) into
long angled walls.  Bush lines, sky edges and the pond are distance bands from
the jungle wall, so they cannot cross it or each other.

Checks (a failure raises, so a random layout just tries another seed):
floor area of the BSP leaves == area of the traced floor outline, no two walls
cross, texture alignment via align.py.

Usage:  python roomedit/roogen/jungle.py        (run from the repo root)
Writes: out/kd5_jungle.roo, out/kd5_jungle.txt, out/kd5_jungle.png
"""
import math
import os
import random
import struct
import sys
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from generate import RoomBuilder  # noqa: E402
from roofile import Room, BSP_LEAF  # noqa: E402
from align import align_room, continuity  # noqa: E402

CELL = 16
PAD = 448                  # grid reaches this far past the room box

GROUND, CANOPY_H, SKY_H = 500, 756, 810
LIGHT = 178
JUNGLE_FLOOR, CANOPY, JUNGLE_WALL, BUSH = 9069, 9068, 9089, 9070
# 1802 is the pale shallow water kc5's pond uses; 9084 is deep blue sea water
VINES, VINE_FRINGE, WATER, MUD = 9100, 9067, 1802, 9141
JUNGLE_WALL_FLAGS = 0x22a
BUSH_WALL_SIDE, BUSH_TRAIL_SIDE = 0x202, 0x207
VINE_CANOPY_SIDE, VINE_SKY_SIDE = 0x0e, 0x2e
POND_EDGE = 0x0c
POND_FLAGS = 0xb5          # kc5's pond: depth 1, scrolling
POND_DROP = 12

BUSH_DIST, SKY_DIST, POND_DIST = 72, 150, 230


class Wood:
    """One wooded area's look.  canopy=0 means open sky everywhere (the mainland
    forest and the Quilicia Wood have no canopy sectors; Ko'catan's jungle does)."""

    def __init__(self, name, ground, canopy, wall, bush, water, mud, light=LIGHT,
                 vines=VINES, fringe=VINE_FRINGE, ground_h=GROUND, canopy_h=CANOPY_H, sky_h=SKY_H,
                 wall_flags=JUNGLE_WALL_FLAGS, bush_flags=(BUSH_WALL_SIDE, BUSH_TRAIL_SIDE),
                 pond_flags=POND_FLAGS, pond_drop=POND_DROP):
        self.name, self.ground, self.canopy = name, ground, canopy
        self.wall, self.bush = wall, bush
        self.water, self.mud, self.light = water, mud, light
        self.vines, self.fringe = vines, fringe
        self.ground_h, self.canopy_h, self.sky_h = ground_h, canopy_h, sky_h
        self.wall_flags, self.bush_flags = wall_flags, bush_flags
        self.pond_flags, self.pond_drop = pond_flags, pond_drop


KOCATAN_JUNGLE = Wood("Ko'catan jungle", ground=JUNGLE_FLOOR, canopy=CANOPY, wall=JUNGLE_WALL, bush=BUSH,
                      water=WATER, mud=MUD)

# ---- the fixed kd5 layout
KD5_BOX = 3136             # 49 x 49 squares
KD5_SEED = 5
# The first layout was a compact star with straight-ish arms; the shipped rooms
# (kb3, kd3) snake in S-curves across most of the box, so every trail gets extra
# meander points and two more branches wander off to hollows.
KD5_TRAILS = [
    ([(1760, 3440), (1850, 3100), (1650, 2900), (1750, 2650), (1550, 2400), (1600, 2100), (1500, 1650)], 220),  # north edge -> clearing
    ([(-300, 1150), (300, 1100), (600, 1350), (900, 1250), (1200, 1550), (1500, 1650)], 200),                 # west edge -> clearing
    ([(1750, 2650), (2150, 2750), (2450, 2450), (2300, 2100), (2000, 1950), (1500, 1650)], 190),              # loop round the island
    ([(1500, 1650), (1900, 1250), (2250, 1300), (2450, 1000), (2650, 900)], 180),                             # east branch
    ([(1500, 1650), (1350, 1250), (1600, 950), (1350, 650), (1300, 450)], 170),                               # south branch
    ([(1550, 2400), (1200, 2550), (900, 2350), (600, 2600), (450, 2850)], 160),                               # north-west wander
    ([(900, 1250), (700, 850), (400, 700), (350, 400)], 160),                                                 # south-west wander
]
# glades: (centre, radius, name, open sky, pond)
KD5_GLADES = [((1500, 1650), 380, "central clearing", True, True),
              ((2650, 900), 250, "east glade", True, False),
              ((1300, 450), 220, "south hollow", False, False),
              ((450, 2850), 210, "vine hollow", False, False),
              ((350, 400), 190, "sunlit hollow", True, False)]


# ---------------------------------------------------------------------------
# raster (grids are rows of columns: grid[y][x])
# ---------------------------------------------------------------------------
def catmull(points, step=16.0):
    pts = [points[0]] + list(points) + [points[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        n = max(2, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[j]) + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3) for j in (0, 1)))
    out.append(points[-1])
    return out


def _cell_range(v, r, origin, n):
    return max(0, int((v - r - origin) // CELL)), min(n - 1, int((v + r - origin) // CELL) + 1)


def paint(grid, origin, cx, cy, r):
    rows, cols = len(grid), len(grid[0])
    x0, x1 = _cell_range(cx, r, origin, cols)
    y0, y1 = _cell_range(cy, r, origin, rows)
    for y in range(y0, y1 + 1):
        py = origin + (y + 0.5) * CELL
        for x in range(x0, x1 + 1):
            px = origin + (x + 0.5) * CELL
            if (px - cx) ** 2 + (py - cy) ** 2 <= r * r:
                grid[y][x] = True


def paint_glade(grid, origin, c, R, p1, p2):
    rows, cols = len(grid), len(grid[0])
    x0, x1 = _cell_range(c[0], R * 1.2, origin, cols)
    y0, y1 = _cell_range(c[1], R * 1.2, origin, rows)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            px, py = origin + (x + 0.5) * CELL - c[0], origin + (y + 0.5) * CELL - c[1]
            th = math.atan2(py, px)
            if math.hypot(px, py) <= R * (1 + 0.12 * math.sin(3 * th + p1) + 0.07 * math.sin(5 * th + p2)):
                grid[y][x] = True


def morph(grid, grow):
    rows, cols = len(grid), len(grid[0])
    out = [row[:] for row in grid]
    for y in range(rows):
        for x in range(cols):
            if grid[y][x] != grow:
                for dy in (-1, 0, 1):
                    yy = y + dy
                    if 0 <= yy < rows and any(0 <= x + dx < cols and grid[yy][x + dx] == grow for dx in (-1, 0, 1)):
                        out[y][x] = grow
                        break
    return out


def fix_pinches(grid, allowed=None):
    """No two cells may touch only at a corner -- the outline tracer needs
    every corner to have one way in and one way out.  A pinch is filled; if
    filling would put floor where `allowed` forbids it, the pinch is cut
    instead."""
    rows, cols = len(grid), len(grid[0])
    changed = True
    while changed:
        changed = False
        for y in range(rows - 1):
            for x in range(cols - 1):
                a, b, c, d = grid[y][x], grid[y][x + 1], grid[y + 1][x], grid[y + 1][x + 1]
                if a and d and not b and not c:
                    fill, cut = ((y, x + 1), (y + 1, x)), ((y, x), (y + 1, x + 1))
                elif b and c and not a and not d:
                    fill, cut = ((y, x), (y + 1, x + 1)), ((y, x + 1), (y + 1, x))
                else:
                    continue
                if allowed is None or all(allowed[yy][xx] for yy, xx in fill):
                    for yy, xx in fill:
                        grid[yy][xx] = True
                else:
                    for yy, xx in cut:
                        grid[yy][xx] = False
                changed = True


def drop_small(grid, min_cells):
    rows, cols = len(grid), len(grid[0])
    seen = [[False] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if grid[y][x] and not seen[y][x]:
                comp, stack = [], [(x, y)]
                seen[y][x] = True
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        xx, yy = cx + dx, cy + dy
                        if 0 <= xx < cols and 0 <= yy < rows and grid[yy][xx] and not seen[yy][xx]:
                            seen[yy][xx] = True
                            stack.append((xx, yy))
                if len(comp) < min_cells:
                    for cx, cy in comp:
                        grid[cy][cx] = False


def distance(grid):
    rows, cols = len(grid), len(grid[0])
    INF = 10 ** 9
    D = [[INF if grid[y][x] else 0 for x in range(cols)] for y in range(rows)]
    for y in range(rows):
        for x in range(cols):
            if D[y][x]:
                for dx, dy, c in ((-1, 0, 16), (0, -1, 16), (-1, -1, 23), (1, -1, 23)):
                    xx, yy = x + dx, y + dy
                    D[y][x] = min(D[y][x], D[yy][xx] + c if 0 <= xx < cols and 0 <= yy < rows else c)
    for y in range(rows - 1, -1, -1):
        for x in range(cols - 1, -1, -1):
            if D[y][x]:
                for dx, dy, c in ((1, 0, 16), (0, 1, 16), (1, 1, 23), (-1, 1, 23)):
                    xx, yy = x + dx, y + dy
                    D[y][x] = min(D[y][x], D[yy][xx] + c if 0 <= xx < cols and 0 <= yy < rows else c)
    return D


# ---------------------------------------------------------------------------
# outlines
# ---------------------------------------------------------------------------
def trace(mask, origin):
    """Closed outline loops in editor units, with the mask on the LEFT."""
    rows, cols = len(mask), len(mask[0])
    nxt = {}

    def edge(a, b):
        if a in nxt:
            raise ValueError("outline pinch at %s" % (a,))
        nxt[a] = b

    for y in range(rows):
        for x in range(cols):
            if not mask[y][x]:
                continue
            if y == 0 or not mask[y - 1][x]:
                edge((x, y), (x + 1, y))
            if y == rows - 1 or not mask[y + 1][x]:
                edge((x + 1, y + 1), (x, y + 1))
            if x == 0 or not mask[y][x - 1]:
                edge((x, y + 1), (x, y))
            if x == cols - 1 or not mask[y][x + 1]:
                edge((x + 1, y), (x + 1, y + 1))
    loops = []
    while nxt:
        start = next(iter(nxt))
        loop, cur = [start], nxt.pop(start)
        while cur != start:
            loop.append(cur)
            cur = nxt.pop(cur)
        loops.append([(origin + cx * CELL, origin + cy * CELL) for cx, cy in loop])
    return loops


def rdp(points, tol):
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        i, j = stack.pop()
        ax, ay = points[i]
        bx, by = points[j]
        L = math.hypot(bx - ax, by - ay) or 1e-9
        best, bd = None, tol
        for k in range(i + 1, j):
            px, py = points[k]
            d = abs((bx - ax) * (ay - py) - (ax - px) * (by - ay)) / L
            if d > bd:
                best, bd = k, d
        if best is not None:
            keep[best] = True
            stack += [(i, best), (best, j)]
    return [p for p, k in zip(points, keep) if k]


def simplify_loop(loop, tol, window=3, passes=2, bounds=None):
    # Smooth first.  Simplifying the raw outline keeps the 16-unit staircase
    # (a diagonal's steps stray ~11 units from the true line, so a 10-12 tolerance
    # cannot drop them): the first build came out 29% angled with a median wall
    # of 32, against 70% and 128-143 in the shipped jungle rooms.  A rolling
    # average over the corner points erases the staircase before simplifying.
    n = len(loop)
    if n > 2 * window + 2:
        for _ in range(passes):
            loop = [(sum(loop[(i + k) % n][0] for k in range(-window, window + 1)) / (2 * window + 1),
                     sum(loop[(i + k) % n][1] for k in range(-window, window + 1)) / (2 * window + 1))
                    for i in range(n)]
    far = max(range(len(loop)), key=lambda k: (loop[k][0] - loop[0][0]) ** 2 + (loop[k][1] - loop[0][1]) ** 2)
    a = rdp(loop[:far + 1], tol)
    b = rdp(loop[far:] + [loop[0]], tol)
    out = [(int(round(x)), int(round(y))) for x, y in a[:-1] + b[:-1]]
    if bounds:
        x0, y0, x1, y1 = bounds
        out = [(min(max(x, x0), x1), min(max(y, y0), y1)) for x, y in out]
    return out


def signed_area(loop):
    return sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1]
               for i in range(len(loop))) / 2.0


def segments(loop):
    return [(loop[i], loop[(i + 1) % len(loop)]) for i in range(len(loop))]


def side_points(a, b, off=6.0):
    """(point to the left, point to the right) of a->b, near its midpoint."""
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1
    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
    return (mx + nx * off, my + ny * off), (mx - nx * off, my - ny * off)


def crosses(s, t):
    (a, b), (c, d) = s, t
    if {a, b} & {c, d}:
        return False

    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return (v > 0) - (v < 0)
    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    return o1 != o2 and o3 != o4


# ---------------------------------------------------------------------------
def build_jungle(trails, glades, box_w, box_h, seed, title, clip=False, wood=None):
    """-> (room, info), in local coordinates with the room box at (0,0)-(box_w,box_h).

    clip=True keeps every wall inside the box (trails end AT the edge); the
    shipped-room style (clip=False) lets trails run past it.  Raises
    ValueError/AssertionError if the layout does not produce a valid room."""
    wood = wood or KOCATAN_JUNGLE
    rnd = random.Random(seed)
    origin = -PAD
    cols = (box_w + 2 * PAD) // CELL
    rows = (box_h + 2 * PAD) // CELL
    wobble = min(1.0, max(0.6, min(box_w, box_h) / 3136.0))

    walk = [[False] * cols for _ in range(rows)]
    for pts, width in trails:
        path = catmull(pts)
        total = len(path)
        ph1, ph2, ph3 = rnd.uniform(0, 6.28), rnd.uniform(0, 6.28), rnd.uniform(0, 6.28)
        for k, (px, py) in enumerate(path):
            t = k / max(1, total - 1)
            s = k * 16.0
            a = path[min(k + 1, total - 1)]
            b = path[max(k - 1, 0)]
            L = math.hypot(a[0] - b[0], a[1] - b[1]) or 1
            nx, ny = -(a[1] - b[1]) / L, (a[0] - b[0]) / L
            wob = wobble * (120 * math.sin(2 * math.pi * s / 700 + ph1) + 50 * math.sin(2 * math.pi * s / 260 + ph2)) * math.sin(math.pi * t)
            r = width / 2 * (1 + 0.18 * math.sin(2 * math.pi * s / 430 + ph3))
            paint(walk, origin, px + nx * wob, py + ny * wob, r)
    for c, R, _name, _sky, _pond in glades:
        paint_glade(walk, origin, c, R, rnd.uniform(0, 6.28), rnd.uniform(0, 6.28))
    walk = morph(morph(walk, True), False)          # close small gaps
    walk = morph(morph(walk, False), True)          # knock off spikes

    allowed = None
    if clip:                                        # only whole cells inside the box
        allowed = [[origin + x * CELL >= 0 and origin + (x + 1) * CELL <= box_w
                    and origin + y * CELL >= 0 and origin + (y + 1) * CELL <= box_h
                    for x in range(cols)] for y in range(rows)]
        for y in range(rows):
            for x in range(cols):
                walk[y][x] = walk[y][x] and allowed[y][x]
    fix_pinches(walk, allowed)
    drop_small(walk, 40)

    D = distance(walk)

    def band(test):
        m = [[walk[y][x] and test(x, y) for x in range(cols)] for y in range(rows)]
        fix_pinches(m, walk)
        drop_small(m, 24)
        fix_pinches(m, walk)
        return m

    def in_glade(x, y, want, scale):
        px, py = origin + (x + 0.5) * CELL, origin + (y + 0.5) * CELL
        return any(math.hypot(px - c[0], py - c[1]) <= R * scale for c, R, _n, sky, pond in glades
                   if (sky if want == "sky" else pond))

    core = band(lambda x, y: D[y][x] >= BUSH_DIST)
    if wood.canopy:
        sky = band(lambda x, y: D[y][x] >= SKY_DIST and in_glade(x, y, "sky", 1.0))
    else:
        sky = [[False] * cols for _ in range(rows)]      # no canopy: the whole wood is open sky
    pond = band(lambda x, y: D[y][x] >= POND_DIST and in_glade(x, y, "pond", 0.6)
                and (sky[y][x] or not wood.canopy))

    bounds = (0, 0, box_w, box_h) if clip else None
    walk_loops = [simplify_loop(l, 10, bounds=bounds) for l in trace(walk, origin)]
    core_loops = [simplify_loop(l, 12) for l in trace(core, origin)]
    sky_loops = [simplify_loop(l, 12) for l in trace(sky, origin)]
    pond_loops = [simplify_loop(l, 8) for l in trace(pond, origin)]
    for group in (walk_loops, core_loops, sky_loops, pond_loops):
        group[:] = [l for l in group if len(l) >= 3 and abs(signed_area(l)) > 64]
    if not walk_loops:
        raise ValueError("no floor")

    b = RoomBuilder((0, 0, box_w, box_h))
    # with no canopy the ground itself is open to the sky, and the pond sits in it
    ground_ceil, ground_h = (wood.canopy, wood.canopy_h) if wood.canopy else (0, wood.sky_h)
    canopy_sec = b.add_sector(wood.ground, ground_ceil, wood.ground_h, ground_h, wood.light)
    sky_sec = b.add_sector(wood.ground, 0, wood.ground_h, wood.sky_h, wood.light) if wood.canopy else canopy_sec
    pond_sec = b.add_sector(wood.water, 0, wood.ground_h - wood.pond_drop,
                            wood.sky_h if wood.canopy else ground_h, wood.light, flags=wood.pond_flags)

    for loop in walk_loops:                         # tree wall, floor on the left
        for a, c in segments(loop):
            if a == c:
                continue
            left, _right = side_points(a, c)
            b.add_wall_facing(a[0], a[1], c[0], c[1], left,
                              b.add_sidedef(wood.wall, flags=wood.wall_flags), canopy_sec)
    for loop in core_loops:                         # bush line: LEFT of x0->x1 faces the tree wall
        for a, c in segments(loop):
            b.add_wall(c[0], c[1], a[0], a[1],
                       b.add_sidedef(wood.bush, flags=wood.bush_flags[0]), canopy_sec,
                       neg_sidedef=b.add_sidedef(wood.bush, flags=wood.bush_flags[1]), neg_sector=canopy_sec)
    for loop in sky_loops:                          # canopy edge: sky on the left, canopy on the right
        for a, c in segments(loop):
            _left, right = side_points(a, c)
            b.add_wall_facing(a[0], a[1], c[0], c[1], right,
                              b.add_sidedef(wood.vines, flags=VINE_CANOPY_SIDE), canopy_sec,
                              neg_sidedef=b.add_sidedef(0, above=wood.fringe, flags=VINE_SKY_SIDE),
                              neg_sector=sky_sec)
    for loop in pond_loops:                         # pond on the left, dry ground on the right
        for a, c in segments(loop):
            _left, right = side_points(a, c)
            b.add_wall_facing(a[0], a[1], c[0], c[1], right,
                              b.add_sidedef(0, flags=POND_EDGE), sky_sec,
                              neg_sidedef=b.add_sidedef(0, below=wood.mud, flags=POND_EDGE), neg_sector=pond_sec)

    # no two walls may cross
    segs = [((w[0], w[1]), (w[2], w[3])) for w in b.walls]
    boxes = [(min(s[0][0], s[1][0]), min(s[0][1], s[1][1]), max(s[0][0], s[1][0]), max(s[0][1], s[1][1])) for s in segs]
    order = sorted(range(len(segs)), key=lambda i: boxes[i][0])
    bad = 0
    for ii, i in enumerate(order):
        for j in order[ii + 1:]:
            if boxes[j][0] > boxes[i][2]:
                break
            if boxes[j][1] > boxes[i][3] or boxes[j][3] < boxes[i][1]:
                continue
            if crosses(segs[i], segs[j]):
                bad += 1
    if bad:
        raise ValueError("%d wall crossings" % bad)

    room = b.build()
    joins = continuity(room)
    unmatched = align_room(room)
    joins_after = continuity(room)

    floor_area = sum(signed_area(l) for l in walk_loops) * 256
    leaf_area = 0.0
    for node in room.bsp.walk():
        if node.type == BSP_LEAF and node.sector:
            p = node.points
            leaf_area += abs(sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                                 for i in range(len(p)))) / 2
    seal = leaf_area / floor_area if floor_area else 0
    if abs(seal - 1) >= 1e-6:
        raise ValueError("not sealed: leaf/floor area = %f" % seal)

    # where the floor meets each room edge (for plEdge_exits later)
    def spans(cells):
        runs, start = [], None
        for i, v in enumerate(cells + [False]):
            if v and start is None:
                start = i
            elif not v and start is not None:
                runs.append((origin + start * CELL, origin + i * CELL))
                start = None
        return runs
    inside = 1 if clip else 0
    edge_rows = {"north": (box_h - origin) // CELL - inside, "south": (0 - origin) // CELL - 1 + inside}
    edge_cols = {"east": (box_w - origin) // CELL - inside, "west": (0 - origin) // CELL - 1 + inside}
    exits = {}
    for side, r in edge_rows.items():
        s = spans([walk[r][x] for x in range(cols)]) if 0 <= r < rows else []
        if s:
            exits[side] = s
    for side, ci in edge_cols.items():
        s = spans([walk[y][ci] for y in range(rows)]) if 0 <= ci < cols else []
        if s:
            exits[side] = s

    lens = sorted(math.hypot(w[2] - w[0], w[3] - w[1]) for w in b.walls)
    angled = sum(1 for w in b.walls if w[0] != w[2] and w[1] != w[3])
    lines = [
        "%s -- room box %d x %d (%d x %d squares)" % (title, box_w, box_h, box_w * 16 // 1024, box_h * 16 // 1024),
        "%d walls (%d jungle wall, %d bush line, %d canopy edge, %d pond edge), %d%% angled, length median %.0f max %.0f"
        % (len(b.walls), sum(len(l) for l in walk_loops), sum(len(l) for l in core_loops),
           sum(len(l) for l in sky_loops), sum(len(l) for l in pond_loops),
           100 * angled // len(b.walls), lens[len(lens) // 2], lens[-1]),
        "sectors: %s ground %d %s; pond at %d (%d, flags 0x%x)"
        % (wood.name, wood.ground_h,
           ("under canopy %d at %d, open sky at %d" % (wood.canopy, wood.canopy_h, wood.sky_h))
           if wood.canopy else ("open to the sky at %d" % wood.sky_h),
           wood.ground_h - wood.pond_drop, wood.water, wood.pond_flags),
    ] + ["floor reaches the %s edge at %s" % (side, s) for side, s in exits.items()] + [
        "texture joins seamless %d/%d -> %d/%d; seal %.6f; 0 crossing walls" % (joins[1], joins[0], joins_after[1], joins_after[0], seal),
        "",
        "glades: " + ", ".join("%s at (%d, %d) radius %d%s%s" % (nm, c[0], c[1], R, ", open sky" if s else ", under canopy", ", pond" if pd else "")
                              for c, R, nm, s, pd in glades),
    ]
    info = {"lines": lines, "exits": exits, "unmatched": unmatched,
            "loops": {"walk": walk_loops, "core": core_loops, "sky": sky_loops, "pond": pond_loops},
            "summary": "%d walls, %d glades, exits: %s" % (len(b.walls), len(glades), ", ".join(exits) or "none")}
    return room, info


def render_png(path, info, box_w, box_h):
    """Layout picture: black jungle wall, green bushes, blue canopy edge, cyan pond, grey room box."""
    S, pad = 800, 12
    lo_x, lo_y = -PAD, -PAD
    span = max(box_w, box_h) + 2 * PAD
    hi_y = lo_y + span
    sc = (S - 2 * pad) / span
    px = [[255] * (S * 3) for _ in range(S)]

    def line(ax, ay, bx, by, col, th=1):
        ax, bx = (ax - lo_x) * sc + pad, (bx - lo_x) * sc + pad
        ay, by = (hi_y - ay) * sc + pad, (hi_y - by) * sc + pad
        n = int(max(abs(bx - ax), abs(by - ay))) + 1
        for i in range(n + 1):
            x, y = int(ax + (bx - ax) * i / n), int(ay + (by - ay) * i / n)
            for dx in range(th):
                for dy in range(th):
                    if 0 <= x + dx < S and 0 <= y + dy < S:
                        px[y + dy][3 * (x + dx):3 * (x + dx) + 3] = col
    for a, c in ((0, 0), (box_w, 0)), ((box_w, 0), (box_w, box_h)), ((box_w, box_h), (0, box_h)), ((0, box_h), (0, 0)):
        line(a[0], a[1], c[0], c[1], [190, 190, 190])
    loops = info["loops"]
    for key, col, th in (("core", [0, 150, 0], 1), ("sky", [0, 90, 220], 1), ("pond", [0, 190, 190], 1), ("walk", [0, 0, 0], 2)):
        for loop in loops[key]:
            for a, c in segments(loop):
                line(a[0], a[1], c[0], c[1], col, th)

    def chunk(tg, dd):
        return struct.pack(">I", len(dd)) + tg + dd + struct.pack(">I", zlib.crc32(tg + dd) & 0xffffffff)
    raw = b"".join(b"\x00" + bytes(px[y]) for y in range(S))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", S, S, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    room, info = build_jungle(KD5_TRAILS, KD5_GLADES, KD5_BOX, KD5_BOX, KD5_SEED,
                              "The Overgrown Glade (kd5) -- Ko'catan jungle")
    out = os.path.join(HERE, "out", "kd5_jungle.roo")
    room.save(out)
    again = Room.load(out)
    with open(out, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"
    with open(os.path.join(HERE, "out", "kd5_jungle.txt"), "w") as fh:
        fh.write("\n".join(info["lines"]) + "\n")
    render_png(os.path.join(HERE, "out", "kd5_jungle.png"), info, KD5_BOX, KD5_BOX)
    print(again.summary())
    print("\n".join(info["lines"][:-2]))
    print("unmatched client wall sides", info["unmatched"])
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
