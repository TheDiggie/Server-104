#!/usr/bin/env python3
"""
cave.py -- generate cave rooms for Meridian.

What actually makes a cave read as a cave in this engine is not the outline. It
is the FLOOR. Compare the shipped rooms:

    banditcave   34 sectors, floor heights 480..608 across 19 distinct values
    cave3        69 sectors, floor heights 208..792 across 45 distinct values

Both are a mass of small sectors at slightly different heights, separated by
two-sided walls whose only visible part is the step between them (their sidedefs
have normal=0 and a texture on `below`). An irregular boundary around one flat
sector looks like a star-shaped room, not a cave.

So this builds a cave as:

  1. cellular automata on a grid -> which cells are open
  2. keep only the largest connected blob, so the room is never split in two
  3. a smoothed height field, quantised into a few levels -> uneven ground
  4. cells sharing a height and touching each other become one SECTOR
  5. walls only where something changes:
        open | rock            -> one-sided rock wall
        sector A | sector B    -> two-sided wall, showing the height step
        same sector            -> no wall at all
  6. runs of collinear wall segments are merged, which matters: it is the
     difference between ~1500 walls and ~250, and the BSP builder is O(n^2) in
     the walls at each node.
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from generate import RoomBuilder

# Textures lifted from the orc caves (oc02/oc04/oc06), which is the look being
# modelled -- banditcave's 7301 is a different, flatter rock.
ORC_FLOOR = 8991      # oc04/oc06 main floor
ORC_CEIL = 9001       # oc02/oc06 main ceiling
ORC_WALL = 8994       # the wall face used across all of them
ORC_STEP = 8999       # the texture on floor/ceiling steps
ROCK = ORC_WALL       # kept for callers that just want "the rock texture"

# Wall flags, from roomedit/include/bsp.h.  These are not cosmetic:
# blakserv/roofile.c BSPCanMoveInRoomTreeInternal blocks ANY move across a side
# that does not have WF_PASSABLE set.  An interior step wall without it turns the
# cave into a set of sealed cells you cannot walk between.
WF_PASSABLE = 0x0004
WF_MAP_NEVER = 0x0008     # keep interior steps off the automap

# banditcave.roo uses exactly this combination on its interior walls (0xc).
STEP_FLAGS = WF_PASSABLE | WF_MAP_NEVER


def _neighbours(g, x, y, n):
    c = 0
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            i, j = x + dx, y + dy
            if 0 <= i < n and 0 <= j < n:
                c += 1 if g[j][i] else 0
            else:
                c += 1          # treat outside as rock, keeps caves closed
    return c


def _automata(n, fill, steps, rnd):
    """The 4-5 rule.

    A cell stays rock if it already is and has >=4 rock neighbours, and becomes
    rock if it is open but has >=5.  Being 'sticky' about the cell's existing
    state is the whole trick: a rule that looks only at the neighbours erodes
    rock every iteration (the average cell has ~3.6 rock neighbours at 45% fill),
    so the map converges to one big open room with a border -- which is exactly
    what it did before this was fixed, at 92% open.
    """
    g = [[1 if rnd.random() < fill else 0 for _ in range(n)] for _ in range(n)]
    for _ in range(steps):
        g = [[1 if ((g[y][x] and _neighbours(g, x, y, n) >= 4) or
                    (not g[y][x] and _neighbours(g, x, y, n) >= 5))
              else 0 for x in range(n)] for y in range(n)]
    # a hard rock border so the cave never touches the room edge
    for i in range(n):
        g[0][i] = g[n - 1][i] = g[i][0] = g[i][n - 1] = 1
    return g


def _carve_exit(g, keep, n, side, width=3):
    """Open a corridor from the cave out through one edge of the grid.

    Rooms are joined by EDGE exits: blakserv fires the exit when you cross the
    room's THINGS bounding box (room.kod SomethingMoved -> StandardLeaveDir), so
    there has to be walkable floor spanning that boundary.  Every shipped orc
    cave has geometry extending past its things box for exactly this reason.

    Returns ((row, col) to arrive at, set of cells forming the mouth).  The
    mouth cells must NOT get a wall across them: an exit has to be a visible
    opening in the room outline, or the player has no way to tell where it is --
    on the automap a walled-off corridor just looks like a dead end.
    """
    mouth = set()
    mid = n // 2
    if side in ("W", "E"):
        rows = sorted({y for (x, y) in keep},
                      key=lambda y: abs(y - mid))
        row = rows[0]
        xs = [x for (x, y) in keep if y == row]
        if side == "W":
            edge_x, stop = 0, min(xs)
        else:
            edge_x, stop = n - 1, max(xs)
        lo, hi = (edge_x, stop) if edge_x < stop else (stop, edge_x)
        for x in range(lo, hi + 1):
            for dy in range(-(width // 2), width // 2 + 1):
                yy = row + dy
                if 0 <= yy < n:
                    g[yy][x] = 0
                    keep.add((x, yy))
        # a few cells in from the edge: arriving exactly on the things-box
        # boundary re-triggers the exit and bounces the player straight back
        # the mouth is the cell column right at the grid edge
        for dy in range(-(width // 2), width // 2 + 1):
            yy = row + dy
            if 0 <= yy < n:
                mouth.add((edge_x, yy))
        entry = (row, 4 if side == "W" else n - 5)
    else:
        cols = sorted({x for (x, y) in keep}, key=lambda x: abs(x - mid))
        col = cols[0]
        ys = [y for (x, y) in keep if x == col]
        if side == "N":
            edge_y, stop = 0, min(ys)
        else:
            edge_y, stop = n - 1, max(ys)
        lo, hi = (edge_y, stop) if edge_y < stop else (stop, edge_y)
        for y in range(lo, hi + 1):
            for dx in range(-(width // 2), width // 2 + 1):
                xx = col + dx
                if 0 <= xx < n:
                    g[y][xx] = 0
                    keep.add((xx, y))
        for dx in range(-(width // 2), width // 2 + 1):
            xx = col + dx
            if 0 <= xx < n:
                mouth.add((xx, edge_y))
        entry = (4 if side == "N" else n - 5, col)
    return entry, mouth


def _largest_blob(g, n):
    """Keep only the biggest open region. Cellular automata happily produce
    several disconnected pockets, and a room you cannot walk across is worse
    than a boring one."""
    seen = [[False] * n for _ in range(n)]
    best = []
    for y in range(n):
        for x in range(n):
            if g[y][x] or seen[y][x]:
                continue
            stack, blob = [(x, y)], []
            seen[y][x] = True
            while stack:
                cx, cy = stack.pop()
                blob.append((cx, cy))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    i, j = cx + dx, cy + dy
                    if 0 <= i < n and 0 <= j < n and not g[j][i] and not seen[j][i]:
                        seen[j][i] = True
                        stack.append((i, j))
            if len(blob) > len(best):
                best = blob
    keep = set(best)
    return [[0 if (x, y) in keep else 1 for x in range(n)] for y in range(n)], keep


def _height_field(n, levels, step, rnd, smooth=2, scale=1):
    """Smoothed noise, quantised, optionally computed on a COARSER lattice and
    upsampled.

    Quantising is what lets neighbouring cells share a level and merge into one
    sector.  `scale` decouples the floor from the outline: the cave shape wants a
    fine grid (or it looks like it was built from bricks), but sampling the
    height that finely shatters the floor into hundreds of tiny sectors.  Coarse
    heights + fine shape gives an organic outline with a banditcave-like sector
    count."""
    m = max(2, (n + scale - 1) // scale)
    h = [[rnd.random() for _ in range(m)] for _ in range(m)]
    for _ in range(smooth):
        h = [[sum(h[max(0, min(m - 1, y + dy))][max(0, min(m - 1, x + dx))]
                  for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
              for x in range(m)] for y in range(m)]
    lo = min(min(r) for r in h)
    hi = max(max(r) for r in h)
    span = (hi - lo) or 1.0
    q = [[int(((h[y][x] - lo) / span) * (levels - 1) + 0.5) * step
          for x in range(m)] for y in range(m)]
    # upsample back to the shape grid
    return [[q[min(m - 1, y // scale)][min(m - 1, x // scale)]
             for x in range(n)] for y in range(n)]


MAX_STEP = 24      # MAXSTEPHEIGHT (24<<4 ROO units) in editor units
HEADROOM = 48      # OBJECTHEIGHTROO (768 ROO units) in editor units


def _enforce_walkable(g, floors, ceils, n):
    """Adjust the height fields until every adjacent pair of open cells passes
    blakserv's movement test, so no wall can become an invisible barrier.

    The three rules, from BSPCanMoveInRoomTreeInternal:
      * a floor step over MAXSTEPHEIGHT blocks (when a lower texture is set)
      * the destination ceiling must clear the SOURCE floor by OBJECTHEIGHTROO
        (when an upper texture is set)
      * the destination sector needs OBJECTHEIGHTROO of headroom of its own

    Doing this as a constraint rather than tuning the noise until the blockers
    happen to disappear: tuning got 5 seeds out of 10, and the failures were
    1-4 walls buried somewhere in a 900-wall room -- exactly the kind of defect
    nobody finds by walking around.
    """
    for _ in range(100):
        changed = False
        for y in range(n):
            for x in range(n):
                if g[y][x]:
                    continue
                if ceils[y][x] - floors[y][x] < HEADROOM:
                    ceils[y][x] = floors[y][x] + HEADROOM
                    changed = True
                for dx, dy in ((1, 0), (0, 1)):
                    i, j = x + dx, y + dy
                    if i >= n or j >= n or g[j][i]:
                        continue
                    d = floors[j][i] - floors[y][x]
                    if d > MAX_STEP:
                        floors[j][i] = floors[y][x] + MAX_STEP
                        changed = True
                    elif -d > MAX_STEP:
                        floors[y][x] = floors[j][i] + MAX_STEP
                        changed = True
                    if ceils[j][i] - floors[y][x] < HEADROOM:
                        ceils[j][i] = floors[y][x] + HEADROOM
                        changed = True
                    if ceils[y][x] - floors[j][i] < HEADROOM:
                        ceils[y][x] = floors[j][i] + HEADROOM
                        changed = True
        if not changed:
            return floors, ceils
    return floors, ceils


def _sectors(g, floors, ceils, n):
    """Flood fill open cells that share BOTH floor and ceiling height.

    Keying on the pair is what gives orc-cave-like sector counts: the shipped
    orc caves have 86-136 sectors and 10-35 distinct ceiling heights, because a
    change in the roof starts a new sector even where the floor is unchanged.
    (In oc06, 157 of ~330 sector boundaries have a floor step of exactly 0 --
    they are ceiling changes.)"""
    sid = [[-1] * n for _ in range(n)]
    sector_fh = []
    sector_ch = []
    for y in range(n):
        for x in range(n):
            if g[y][x] or sid[y][x] >= 0:
                continue
            k = len(sector_fh)
            fh, ch = floors[y][x], ceils[y][x]
            stack = [(x, y)]
            sid[y][x] = k
            while stack:
                cx, cy = stack.pop()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    i, j = cx + dx, cy + dy
                    if (0 <= i < n and 0 <= j < n and not g[j][i]
                            and sid[j][i] < 0 and floors[j][i] == fh
                            and ceils[j][i] == ch):
                        sid[j][i] = k
                        stack.append((i, j))
            sector_fh.append(fh)
            sector_ch.append(ch)
    return sid, sector_fh, sector_ch


def _merge_runs(edges):
    """Collapse consecutive collinear segments that share the same two sides."""
    out = []
    for key, segs in edges.items():
        horizontal = key[0] == "h"
        segs = sorted(segs)
        run_start = run_end = None
        for a, b in segs:
            if run_end is not None and a == run_end:
                run_end = b
            else:
                if run_end is not None:
                    out.append((key, run_start, run_end))
                run_start, run_end = a, b
        if run_end is not None:
            out.append((key, run_start, run_end))
    return out


def _merge_collinear(b):
    """Join wall segments that continue each other in a straight line and have
    identical sides.  Chamfering emits one segment per cell edge, which triples
    the wall count; merging brings it back to roughly what a hand-built cave has.
    The BSP builder is O(n^2) in the walls at each node, so this is not just
    tidiness."""
    def dir_of(w):
        dx, dy = w[2] - w[0], w[3] - w[1]
        gg = math.gcd(abs(int(dx)), abs(int(dy))) or 1
        return (dx // gg, dy // gg)

    changed = True
    while changed:
        changed = False
        by_start = {}
        for i, w in enumerate(b.walls):
            by_start.setdefault((w[0], w[1], dir_of(w), w[4], w[5], w[6], w[7]), []).append(i)
        dead = set()
        for i, w in enumerate(b.walls):
            if i in dead:
                continue
            key = (w[2], w[3], dir_of(w), w[4], w[5], w[6], w[7])
            for j in by_start.get(key, ()):
                if j == i or j in dead:
                    continue
                nxt = b.walls[j]
                b.walls[i] = (w[0], w[1], nxt[2], nxt[3], w[4], w[5], w[6], w[7])
                dead.add(j)
                changed = True
                break
        if dead:
            b.walls = [w for k, w in enumerate(b.walls) if k not in dead]
    return b


def build_cave(room_id, seed=1, n=60, cell=48, fill=0.48, steps=5,
               levels=24, height_step=4, base_floor=0, ceiling=440,
               light=255, margin=192, smooth=3, height_scale=6,
               chamfer=0.5, jitter=0.0,
               gap_levels=8, gap_step=24, gap_min=88, gap_scale=6,
               exits=(), exit_width=3):
    # Defaults tuned against oc02/oc06 rather than by eye:
    #     oc02  96 sectors, 863 walls, 26 floor levels, 15 ceiling levels
    #     here  83 sectors, 893 walls, 22 floor levels, 35 ceiling levels
    # Pushing the floor variety higher (levels 30+, coarser scales) starts to
    # produce steps the server treats as impassable, so this is the limit that
    # still leaves every wall walkable.
    # jitter defaults OFF.  Displacing vertices looks like the right idea and
    # measurably is not: it prevents collinear walls from merging, so the long
    # runs that give a cave its shape get shattered into cell-sized fragments.
    # Measured against the shipped caves (max wall length, which is the statistic
    # that actually separates them from a grid):
    #     jitter 0.08 -> 997 walls, longest 140, 16.6 walls/sector
    #     jitter 0    -> 616 walls, longest 576, 10.3 walls/sector
    #     cave3        -> 480 walls, longest 1344, 7.0 walls/sector
    # Angle variety is not the thing: cave3 is 50% axis-aligned and reads fine.
    # Jitter is also capped at ~0.08 anyway before displaced polygons overlap and
    # the room starts leaking.
    rnd = random.Random(seed)
    g = _automata(n, fill, steps, rnd)
    g, keep = _largest_blob(g, n)
    keep = set(keep)
    entries = {}
    mouths = {}                     # side -> cells whose outward edge stays open
    for side in exits:
        entries[side], mouths[side] = _carve_exit(g, keep, n, side,
                                                  width=exit_width)
    if len(keep) < (n * n) // 10:
        raise ValueError("cave came out too small; try another seed")

    floors = _height_field(n, levels, height_step, rnd, smooth=smooth,
                           scale=height_scale)
    # An independent field for HEADROOM.  The ceiling is not a lid at a fixed
    # height above the floor: in the orc caves the roof rises and falls on its
    # own, so a low crawl can open into a high chamber.  The gap has a floor of
    # its own because blakserv refuses any move into a sector with less than
    # OBJECTHEIGHTROO (48 editor units) of headroom.
    gaps = _height_field(n, gap_levels, gap_step, rnd, smooth=smooth,
                         scale=gap_scale)
    ceils = [[floors[y][x] + gap_min + gaps[y][x] for x in range(n)]
             for y in range(n)]
    floors, ceils = _enforce_walkable(g, floors, ceils, n)
    sid, sector_fh, sector_ch = _sectors(g, floors, ceils, n)

    xs = [x for (x, y) in keep]
    ys = [y for (x, y) in keep]
    x0c, x1c = min(xs), max(xs) + 1
    y0c, y1c = min(ys), max(ys) + 1

    def ex(cx):
        return int(round((cx - x0c) * cell))

    def ey(cy):
        return int(round((cy - y0c) * cell))

    # The things box is what the engine treats as the room's extent, and
    # crossing it is what fires an edge exit.  On a side with an exit the box
    # edge is pulled INSIDE the corridor, so there is walkable floor spanning it
    # -- otherwise the player just walks into the rock at the grid edge and the
    # exit never triggers.  (Every shipped orc cave has geometry outside its
    # things box for the same reason.)
    # ey() grows with the cell row while RoomBuilder.cy() flips Y, so cell row 0
    # ends up at the BOTTOM of the room in editor terms.  Only W/E exits are used
    # here, which sidesteps that inversion entirely.
    tb_l = ex(x0c) - margin
    tb_r = ex(x1c) + margin
    tb_b = ey(y0c) - margin
    tb_t = ey(y1c) + margin
    if "W" in exits:
        tb_l = ex(1.5)
    if "E" in exits:
        tb_r = ex(n - 2.5)

    b = RoomBuilder((tb_l, tb_b, tb_r, tb_t), room_id=room_id)

    sec_ids = [b.add_sector(ORC_FLOOR, ORC_CEIL, base_floor + fh, base_floor + ch, light)
               for fh, ch in zip(sector_fh, sector_ch)]
    sd_rock = b.add_sidedef(ORC_WALL)         # outer wall: solid rock face
    # above AND below: the roof step needs a face too, now that it moves.
    sd_step = b.add_sidedef(0, above=ORC_STEP, below=ORC_STEP, flags=STEP_FLAGS)

    # ---------------------------------------------------------------
    # Walls.
    #
    # A grid of squares reads as brickwork, not rock, so every open cell is
    # emitted as a POLYGON whose corners are chamfered wherever the rock forms a
    # convex corner (both orthogonal neighbours solid).  That turns the staircase
    # edges into 45-degree faces and is what the hand-built cave maps look like.
    #
    # Chamfering only convex rock corners is what keeps this consistent: where
    # two open cells share a side, neither of them cuts that side, so the shared
    # edge stays straight and the two cells still meet exactly.  Nothing is
    # approximated away, so the interior stays sealed.
    # ---------------------------------------------------------------
    def rock(x, y):
        return x < 0 or y < 0 or x >= n or y >= n or g[y][x]

    # ---- vertex displacement -------------------------------------------
    # Chamfering corners only bevels a lattice; the walls are still axis-aligned
    # or 45 degrees and it still reads as a grid.  Displacing the grid VERTICES
    # puts the walls at arbitrary angles and the lattice disappears.
    #
    # The displacement has to be a function of the vertex, not of the cell using
    # it: every polygon touching a vertex then moves it identically, so the mesh
    # stays watertight.  Jitter a cell's own copy of a corner instead and the
    # room fills with cracks you can fall through.
    disp_cache = {}

    def disp(vx, vy):
        key = (vx, vy)
        d = disp_cache.get(key)
        if d is None:
            r = random.Random((vx * 73856093) ^ (vy * 19349663) ^ (seed * 83492791))
            d = (r.uniform(-jitter, jitter), r.uniform(-jitter, jitter))
            disp_cache[key] = d
        return d

    def warp(fx, fy):
        """Displace a point given in grid units.  Points that lie along a grid
        edge (chamfer cuts) interpolate between the two endpoint displacements,
        so they stay on the shared edge."""
        ix, iy = int(math.floor(fx + 1e-9)), int(math.floor(fy + 1e-9))
        tx, ty = fx - ix, fy - iy
        if tx < 1e-9 and ty < 1e-9:
            d = disp(ix, iy)
        elif ty < 1e-9:                       # along a horizontal edge
            d0, d1 = disp(ix, iy), disp(ix + 1, iy)
            d = (d0[0] + (d1[0] - d0[0]) * tx, d0[1] + (d1[1] - d0[1]) * tx)
        elif tx < 1e-9:                       # along a vertical edge
            d0, d1 = disp(ix, iy), disp(ix, iy + 1)
            d = (d0[0] + (d1[0] - d0[0]) * ty, d0[1] + (d1[1] - d0[1]) * ty)
        else:
            d = disp(ix, iy)
        return fx + d[0], fy + d[1]

    def cell_polygon(x, y):
        """Corner points clockwise from NW, in grid units, with convex rock
        corners cut back by `chamfer`."""
        c = chamfer
        pts = []
        if rock(x, y - 1) and rock(x - 1, y):            # NW
            pts += [(x, y + c), (x + c, y)]
        else:
            pts += [(x, y)]
        if rock(x, y - 1) and rock(x + 1, y):            # NE
            pts += [(x + 1 - c, y), (x + 1, y + c)]
        else:
            pts += [(x + 1, y)]
        if rock(x, y + 1) and rock(x + 1, y):            # SE
            pts += [(x + 1, y + 1 - c), (x + 1 - c, y + 1)]
        else:
            pts += [(x + 1, y + 1)]
        if rock(x, y + 1) and rock(x - 1, y):            # SW
            pts += [(x + c, y + 1), (x, y + 1 - c)]
        else:
            pts += [(x, y + 1)]
        return pts

    def neighbour_of(x, y, p, q):
        """Which cell an edge of cell (x,y) faces.  A diagonal always faces the
        rock corner it cuts, so it is never shared with another open cell."""
        if abs(p[0] - q[0]) > 1e-9 and abs(p[1] - q[1]) > 1e-9:
            return None                                   # diagonal -> rock
        if abs(p[1] - q[1]) < 1e-9:                       # horizontal
            return (x, y - 1) if abs(p[1] - y) < 1e-9 else (x, y + 1)
        return (x - 1, y) if abs(p[0] - x) < 1e-9 else (x + 1, y)

    open_area = 0.0            # exact area of the warped floor, for validation

    for y in range(n):
        for x in range(n):
            if g[y][x]:
                continue
            mine = sid[y][x]
            poly = cell_polygon(x, y)
            wpoly = [warp(*pt) for pt in poly]
            acc = 0.0
            for k in range(len(wpoly)):
                ax, ay = wpoly[k]
                bx, by = wpoly[(k + 1) % len(wpoly)]
                acc += ex(ax) * ey(by) - ex(bx) * ey(ay)
            # ex/ey are EDITOR units; the BSP works in client units (x16 per axis)
            open_area += abs(acc) / 2.0 * (16 * 16)
            for i in range(len(poly)):
                p = poly[i]
                q = poly[(i + 1) % len(poly)]
                if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9:
                    continue                              # zero-length
                nb = neighbour_of(x, y, p, q)
                # leave the exit mouth open: no wall on the outward edge of a
                # corridor cell sitting at the grid boundary
                if nb is not None and (nb[0] < 0 or nb[1] < 0
                                       or nb[0] >= n or nb[1] >= n):
                    side = ("W" if nb[0] < 0 else "E" if nb[0] >= n
                            else "N" if nb[1] < 0 else "S")
                    if (x, y) in mouths.get(side, ()):
                        continue
                other = -1
                if nb is not None and not rock(nb[0], nb[1]):
                    other = sid[nb[1]][nb[0]]
                if other == mine:
                    continue                              # same sector, no wall
                # an interior wall is shared by two cells; emit it once
                if other >= 0 and (nb[1], nb[0]) < (y, x):
                    continue

                wp, wq = warp(*p), warp(*q)
                px0, py0 = ex(wp[0]), ey(wp[1])
                px1, py1 = ex(wq[0]), ey(wq[1])
                inside = (ex((p[0] + q[0]) * 0.5 + (x + 0.5 - (p[0] + q[0]) * 0.5) * 0.35),
                          ey((p[1] + q[1]) * 0.5 + (y + 0.5 - (p[1] + q[1]) * 0.5) * 0.35))

                if other < 0:
                    b.add_wall_facing(px0, py0, px1, py1, inside,
                                      sd_rock, sec_ids[mine])
                else:
                    b.add_wall_facing(px0, py0, px1, py1, inside,
                                      sd_step, sec_ids[mine],
                                      neg_sidedef=sd_step,
                                      neg_sector=sec_ids[other])

    _merge_collinear(b)

    room = b.build()
    # Where an arriving player should be placed, per side, in SERVER squares
    # (client units / FINENESS).  The room class needs these for plEdge_Exits.
    entry_squares = {}
    for side, (cy, cx) in entries.items():
        client_x = (ex(cx + 0.5) - tb_l) * 16
        client_y = (tb_t - ey(cy + 0.5)) * 16      # cy() flips Y
        entry_squares[side] = (int(client_y // 1024), int(client_x // 1024))

    return room, len(sector_fh), len(b.walls), open_area, entry_squares


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "out/cave.roo"
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    room, nsec, nwall, _, _ = build_cave(room_id=0, seed=seed)
    room.save(out)
    print("wrote %s: %d sectors, %d walls" % (out, nsec, nwall))
    return 0


if __name__ == "__main__":
    sys.exit(main())
