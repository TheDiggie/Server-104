#!/usr/bin/env python3
"""
cave2.py -- caves and open terrain for the map generator (the old single-level
cave.py stays as it is: the live orc warren was built with it).

Two layouts, both painted as region labels on a 32-unit grid and traced into
boundary chains shared by the regions either side, so smoothing and simplifying
cannot open cracks between them:

  * CHAMBERS (the orc caves, the spider nest, the ruins of Brax).  Measured from
    oc01-oc07: floors span 250-1530 units, chambers sit on separate height tiers
    joined by long straight RAMPS (sloped floor sectors, rise per unit of run
    median 0.35, 64-448 wide), with DROPS where tiers meet (80-500).  Gaps are
    mostly 100-175.  A tier change of 24 or less is just a step, not a ramp.
  * TERRAIN (the Cragged Mountains, a beach, the desert).  One broad landmass
    whose height field is quantised into terraces a step apart, so the ground is
    continuous and walkable everywhere, with water below a shore level and the
    odd rock island.  Measured from g8/i8: 23-72 floor levels over 0-490 with NO
    sloped sectors, which is what stepped terraces give.

Outdoor styles give every area the sky (no ceiling texture) at one shared
height, so no upper wall textures are drawn against it, as in the shipped
outdoor rooms.

Slopes are written the way roomedit's ComputeSlopeInfo does (save.cpp): the
three points in client space, their cross product scaled to FINENESS (1024),
d from the first point, floor normals pointing up.

Checks (a failure raises ValueError, so the app retries with another seed):
  * every region can be reached from every other by legal moves -- a step up of
    at most 24 and 48 of headroom -- tested along the actual boundary walls
  * BSP floor area == traced floor area; no two walls cross
"""
import math
import os
import random
import sys
from collections import defaultdict, deque

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from generate import RoomBuilder  # noqa: E402
from roofile import BSP_LEAF, Slope  # noqa: E402
from align import align_room  # noqa: E402
from jungle import rdp, crosses, side_points  # noqa: E402

C = 32                     # grid cell, editor units
BLAK = 16
FINENESS = 1024
MAX_STEP, HEADROOM = 24, 48
TWO_SIDED_FLAGS = 0x0c
WF_TRANSPARENT = 0x02          # normal texture has transparent pixels (clientd3d/bsp.h)
SF_SLOPED_FLOOR = 0x400


class CaveStyle:
    """Palette and terrain shape.  Heights are editor units."""

    def __init__(self, name, floors, ramp, ceils, walls, light, wall_height=0,
                 gaps=(100, 125, 150, 150, 175, 200, 250, 300, 400),
                 sky=False, sky_gap=700, water=None, water_flags=0xad, water_drop=16, water_chance=0.0,
                 tier_max=700, tier_step=25, grade=(0.25, 0.45), chamber_area=1.4e6, patch_rate=160,
                 patch_steps=(-16, 16, 24), patch_ceils=(-50, 50, 100, 150),
                 tunnel_gaps=(100, 125, 150), tunnel_width=(96, 176),
                 terrain=False, terrace_step=24, terraces=(8, 20), water_level=0.0, island_chance=0.0,
                 plateau=0.0, web=0, web_chance=0.0):
        self.name = name
        self.floors, self.ramp, self.ceils, self.walls = list(floors), ramp, list(ceils), list(walls)
        self.light, self.gaps = light, list(gaps)
        # Where a palette's wall textures are all one height (Brax: 64 and 128
        # tall stones), every wall must be a whole number of them or the carved
        # band is sliced mid-wall and restarts at the next height change.  The
        # shipped Brax rooms do exactly this: 100/140/160/260/320 walls, and the
        # 160-tall column only ever on a 160-tall wall.
        self.wall_height = wall_height
        self.sky, self.sky_gap = sky, sky_gap
        self.water, self.water_flags = water, water_flags
        self.water_drop, self.water_chance = water_drop, water_chance
        self.tier_max, self.tier_step, self.grade = tier_max, tier_step, grade
        self.chamber_area, self.patch_rate = chamber_area, patch_rate
        self.patch_steps = list(patch_steps)
        self.patch_ceils = list(patch_ceils)
        self.tunnel_gaps, self.tunnel_width = list(tunnel_gaps), tunnel_width
        # A curtain texture strung across openings between chambers: the normal
        # texture of a two-sided wall, marked WF_TRANSPARENT and left passable,
        # which is the only way the shipped rooms ever hang a spider web (3302).
        # Never put such a texture in `walls` -- on a solid wall its transparent
        # pixels read as a hole in the rock.
        self.web, self.web_chance = web, web_chance
        # terrain mode
        self.terrain, self.terrace_step, self.terraces = terrain, terrace_step, terraces
        self.water_level, self.island_chance = water_level, island_chance
        self.plateau = plateau


ORC = CaveStyle("orc cave", floors=[8991, 8991, 8991, 9005], ramp=8999, ceils=[9001, 9001, 8998],
                walls=[8994, 8994, 8994, 9021, 8995, 8996], light=203)


class Region:
    """A floor area that becomes one sector.  ramp = (ax, ay, ux, uy, s0, s1, h0, h1):
    the floor rises from h0 at distance s0 to h1 at s1 along the unit axis (ux, uy)
    from (ax, ay)."""

    def __init__(self, kind, floorh, ceilh, floor, ceil, wall, ramp=None, flags=0):
        self.kind, self.floorh, self.ceilh = kind, floorh, ceilh
        self.floor, self.ceil, self.wall = floor, ceil, wall
        self.ramp, self.flags = ramp, flags

    def fh(self, x, y):
        if not self.ramp:
            return self.floorh
        ax, ay, ux, uy, s0, s1, h0, h1 = self.ramp
        s = (x - ax) * ux + (y - ay) * uy
        return h0 + (s - s0) * (h1 - h0) / (s1 - s0)

    def ch(self, _x, _y):
        return self.ceilh

    def shift(self, dz):
        self.floorh += dz
        self.ceilh += dz
        if self.ramp:
            ax, ay, ux, uy, s0, s1, h0, h1 = self.ramp
            self.ramp = (ax, ay, ux, uy, s0, s1, h0 + dz, h1 + dz)


class Chamber:
    def __init__(self, x, y, R, rnd):
        self.x, self.y, self.R = x, y, R
        self.p = [rnd.uniform(0, 6.28) for _ in range(3)]

    def inside(self, px, py):
        d = math.hypot(px - self.x, py - self.y)
        th = math.atan2(py - self.y, px - self.x)
        return d <= self.R * (1 + 0.18 * math.sin(3 * th + self.p[0]) + 0.10 * math.sin(5 * th + self.p[1])
                              + 0.05 * math.sin(9 * th + self.p[2]))


def make_slope(points, left, top, floor=True):
    """roomedit's ComputeSlopeInfo, from three editor points (x, y, z)."""
    p = [((x - left) * BLAK, (top - y) * BLAK, z * BLAK) for x, y, z in points]
    u = [p[1][i] - p[0][i] for i in range(3)]
    v = [p[2][i] - p[0][i] for i in range(3)]
    uv = [u[2] * v[1] - u[1] * v[2], u[0] * v[2] - u[2] * v[0], u[1] * v[0] - u[0] * v[1]]
    n = math.sqrt(sum(c * c for c in uv))
    if n == 0:
        raise ValueError("degenerate slope")
    a, b, c = (uv[i] * FINENESS / n for i in range(3))
    d = -(a * p[0][0] + b * p[0][1] + c * p[0][2])
    if (floor and c < 0) or (not floor and c > 0):
        a, b, c, d = -a, -b, -c, -d
    s = Slope()
    s.a, s.b, s.c, s.d = a, b, c, d
    s.x, s.y, s.angle = int(p[0][0]), int(p[0][1]), 0
    s.points = [(int(x), int(y), int(z)) for x, y, z in points]
    return s


def _chamber_layout(style, rnd, cols, rows, regions, label):
    """Chambers on height tiers joined by tunnels, ramps and ledges."""
    W, H = cols * C, rows * C

    def add(region):
        regions.append(region)
        return len(regions) - 1

    area = W * H
    k = max(1, int(round(area / style.chamber_area * rnd.uniform(0.8, 1.25))))
    spacing = math.sqrt(area / k)
    chambers = []
    for _ in range(k * 80):
        if len(chambers) >= k:
            break
        R = spacing * rnd.uniform(0.26, 0.38)
        R = max(C * 1.6, min(R, min(W, H) / 2 / 1.35 - C))
        lo_x, hi_x = R * 1.35 + C, W - R * 1.35 - C
        lo_y, hi_y = R * 1.35 + C, H - R * 1.35 - C
        x = W / 2 if lo_x > hi_x else rnd.uniform(lo_x, hi_x)
        y = H / 2 if lo_y > hi_y else rnd.uniform(lo_y, hi_y)
        if all(math.hypot(x - c.x, y - c.y) > (R + c.R) * 1.35 + C * 3 for c in chambers):
            chambers.append(Chamber(x, y, R, rnd))
    if not chambers:
        raise ValueError("no chamber fits")
    n = len(chambers)

    def dist(i, j):
        return math.hypot(chambers[i].x - chambers[j].x, chambers[i].y - chambers[j].y)

    def passes_near_other(i, j):
        A, B = chambers[i], chambers[j]
        dx, dy = B.x - A.x, B.y - A.y
        L2 = dx * dx + dy * dy or 1
        for m, M in enumerate(chambers):
            if m in (i, j):
                continue
            t = max(0, min(1, ((M.x - A.x) * dx + (M.y - A.y) * dy) / L2))
            if math.hypot(M.x - A.x - t * dx, M.y - A.y - t * dy) < M.R * 1.35 + 120:
                return True
        return False

    in_tree, edges = {0}, []
    while len(in_tree) < n:
        i, j = min(((i, j) for i in in_tree for j in range(n) if j not in in_tree), key=lambda e: dist(*e))
        edges.append((i, j))
        in_tree.add(j)
    tree = set(edges)
    for i in range(n):
        for j in range(i + 1, n):
            if (i, j) not in tree and (j, i) not in tree and dist(i, j) < spacing * 1.7 \
                    and rnd.random() < 0.35 and not passes_near_other(i, j):
                edges.append((i, j))

    heights = [None] * n
    heights[0] = 0
    children = defaultdict(list)
    for i, j in tree:
        children[i].append(j)
        children[j].append(i)
    queue, seen = deque([0]), {0}
    while queue:
        i = queue.popleft()
        for j in children[i]:
            if j in seen:
                continue
            seen.add(j)
            gap_len = max(0.0, dist(i, j) - (chambers[i].R + chambers[j].R) * 1.1)
            max_dh = min(float(style.tier_max), 0.45 * max(0.0, gap_len - 2 * C))
            step = style.tier_step
            if max_dh < step or rnd.random() < 0.15:
                dh = 0
            else:
                dh = rnd.choice((-1, 1)) * int(round(rnd.uniform(0.35, 1.0) * max_dh / step)) * step
            heights[j] = heights[i] + dh
            queue.append(j)

    chamber_wall = [rnd.choice(style.walls) for _ in range(n)]
    ramps = ledges = 0
    for i, j in edges:
        A, B = chambers[i], chambers[j]
        hA, hB = heights[i], heights[j]
        D = dist(i, j)
        ux, uy = (B.x - A.x) / D, (B.y - A.y) / D
        s = 0.0
        while s < D and A.inside(A.x + ux * s, A.y + uy * s):
            s += 4
        s_exit = s
        s = D
        while s > s_exit and B.inside(A.x + ux * s, A.y + uy * s):
            s -= 4
        s_entry = s
        wide = rnd.uniform(*style.tunnel_width)
        tgap = rnd.choice(style.tunnel_gaps)
        ceil = rnd.choice(style.ceils)
        dh = hB - hA
        mid = (s_exit + s_entry) / 2
        if dh == 0:
            pieces = [(-1e18, 1e18, add(Region("tunnel", hA, hA + tgap, style.floors[0], ceil, chamber_wall[i])))]
        elif abs(dh) <= MAX_STEP:
            # small enough to walk up: a plain step in the tunnel, no ramp
            pieces = [(-1e18, mid, add(Region("tunnel", hA, hA + tgap, style.floors[0], ceil, chamber_wall[i]))),
                      (mid, 1e18, add(Region("tunnel", hB, hB + tgap, style.floors[0], ceil, chamber_wall[j])))]
        else:
            grade = rnd.uniform(*style.grade)
            Lr = abs(dh) / grade
            usable = s_entry - s_exit - 2 * C
            if Lr > usable:
                Lr = usable if usable > 0 and abs(dh) / usable <= 0.6 else None
            if Lr is None:
                hi = max(hA, hB)
                pieces = [(-1e18, 1e18, add(Region("ledge", hi, hi + tgap, style.floors[0], ceil, chamber_wall[i])))]
                ledges += 1
            else:
                s0, s1 = mid - Lr / 2, mid + Lr / 2
                ramp = Region("ramp", min(hA, hB), max(hA, hB) + tgap, style.ramp, ceil, chamber_wall[i],
                              ramp=(A.x, A.y, ux, uy, s0, s1, hA, hB))
                pieces = [(-1e18, s0, add(Region("tunnel", hA, hA + tgap, style.floors[0], ceil, chamber_wall[i]))),
                          (s0, s1, add(ramp)),
                          (s1, 1e18, add(Region("tunnel", hB, hB + tgap, style.floors[0], ceil, chamber_wall[j])))]
                ramps += 1
        x0 = max(0, int((min(A.x, B.x) - wide) // C)); x1 = min(cols - 1, int((max(A.x, B.x) + wide) // C) + 1)
        y0 = max(0, int((min(A.y, B.y) - wide) // C)); y1 = min(rows - 1, int((max(A.y, B.y) + wide) // C) + 1)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if label[y][x]:
                    continue
                px, py = (x + 0.5) * C, (y + 0.5) * C
                s = (px - A.x) * ux + (py - A.y) * uy
                if s < 0 or s > D or abs(-(px - A.x) * uy + (py - A.y) * ux) > wide / 2:
                    continue
                for lo, hi, rid in pieces:
                    if lo <= s < hi:
                        label[y][x] = rid
                        break

    chamber_region = []
    pools = 0
    for i, ch in enumerate(chambers):
        gap = rnd.choice(style.gaps)
        flooded = style.water and rnd.random() < style.water_chance
        if flooded:
            reg = Region("pool", heights[i] - style.water_drop, heights[i] + gap, style.water,
                         rnd.choice(style.ceils), chamber_wall[i], flags=style.water_flags)
            pools += 1
        else:
            reg = Region("chamber", heights[i], heights[i] + gap, rnd.choice(style.floors),
                         rnd.choice(style.ceils), chamber_wall[i])
        rid = add(reg)
        chamber_region.append(rid)
        reach = ch.R * 1.35
        for y in range(max(0, int((ch.y - reach) // C)), min(rows, int((ch.y + reach) // C) + 2)):
            for x in range(max(0, int((ch.x - reach) // C)), min(cols, int((ch.x + reach) // C) + 2)):
                if ch.inside((x + 0.5) * C, (y + 0.5) * C):
                    label[y][x] = rid

    def lab(x, y):
        return label[y][x] if 0 <= x < cols and 0 <= y < rows else 0

    patches = 0
    for i, rid in enumerate(chamber_region):
        cells = [(x, y) for y in range(rows) for x in range(cols) if label[y][x] == rid]
        if not cells:
            continue
        cellset = set(cells)
        entrance = set()
        for x, y in cells:
            if any(lab(x + dx, y + dy) not in (0, rid) for dx in range(-3, 4) for dy in range(-3, 4)):
                entrance.add((x, y))
        interior = [c for c in cells if c not in entrance
                    and all((c[0] + dx, c[1] + dy) in cellset for dx in (-1, 0, 1) for dy in (-1, 0, 1))]
        base = regions[rid]
        if base.kind == "pool":
            continue
        for _ in range(len(cells) // style.patch_rate):
            if not interior:
                break
            cx0, cy0 = rnd.choice(interior)
            r = rnd.uniform(1.5, 4.5)
            roll = rnd.random()
            if roll < 0.2:
                new = 0
                r = rnd.uniform(0.8, 1.6)                     # rock island / boulder
            else:
                if roll < 0.6:
                    dfloor, dceil = rnd.choice(style.patch_steps), rnd.choice([0] + style.patch_ceils[1:])
                else:
                    dfloor, dceil = 0, rnd.choice(style.patch_ceils)
                fh = base.floorh + dfloor
                chh = max(base.ceilh + dfloor + dceil, fh + HEADROOM + 16)
                new = add(Region("patch", fh, chh, base.floor if rnd.random() < 0.6 else rnd.choice(style.floors),
                                 base.ceil, base.wall))
            patches += 1
            for x, y in interior:
                if math.hypot(x - cx0, y - cy0) <= r and label[y][x] == rid:
                    label[y][x] = new
    return chamber_region, {"chambers": n, "ramps": ramps, "ledges": ledges, "pools": pools, "patches": patches}


def _terrain_layout(style, rnd, cols, rows, regions, label):
    """One broad landmass whose heights are quantised into walkable terraces,
    with water below a shore level and the odd rock island."""
    W, H = cols * C, rows * C

    def add(region):
        regions.append(region)
        return len(regions) - 1

    # the coastline / edge of the ground
    cx, cy = W / 2.0, H / 2.0
    ph = [rnd.uniform(0, 6.28) for _ in range(4)]
    lobes = [(rnd.uniform(0, 6.28), rnd.uniform(0.15, 0.3)) for _ in range(rnd.randint(2, 4))]

    def on_land(px, py):
        dx, dy = px - cx, py - cy
        th = math.atan2(dy, dx)
        r = math.hypot(dx / (W / 2.0), dy / (H / 2.0))
        edge = 0.90 * (1 + 0.16 * math.sin(2 * th + ph[0]) + 0.11 * math.sin(3 * th + ph[1])
                       + 0.07 * math.sin(5 * th + ph[2]))
        for a, amp in lobes:
            edge += amp * math.exp(-((math.atan2(math.sin(th - a), math.cos(th - a))) ** 2) / 0.2)
        return r <= edge

    # a smooth height field over a coarse grid, sampled bilinearly
    gw, gh = max(2, cols // 7), max(2, rows // 7)
    field = [[rnd.uniform(0.0, 1.0) for _ in range(gw + 2)] for _ in range(gh + 2)]
    smoothed = [[sum(field[min(gh + 1, max(0, y + dy))][min(gw + 1, max(0, x + dx))]
                     for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
                 for x in range(gw + 2)] for y in range(gh + 2)]

    # Smoothing pulls the field towards its middle (nine random values average
    # to about 0.5), so without stretching it back to 0..1 the quantiser only
    # ever reaches a third of the terraces asked for.
    flat = [v for row in smoothed for v in row]
    f_lo, f_span = min(flat), (max(flat) - min(flat)) or 1.0

    def height_at(x, y):
        fx, fy = x * gw / cols, y * gh / rows
        ix, iy = int(fx), int(fy)
        tx, ty = fx - ix, fy - iy
        a = smoothed[iy][ix] * (1 - tx) + smoothed[iy][ix + 1] * tx
        b = smoothed[iy + 1][ix] * (1 - tx) + smoothed[iy + 1][ix + 1] * tx
        return (a * (1 - ty) + b * ty - f_lo) / f_span

    n_terraces = rnd.randint(*style.terraces)
    # Keep the terrace COUNT roughly constant as the map grows, rather than the
    # density: the shipped desert rooms are ~22000 units across with about 15
    # floor levels, and every extra terrace boundary is another chance of a
    # stranded scrap (a 5000-wide Desert asking for 30 failed 3 builds in 8).
    n_terraces = max(style.terraces[0], min(n_terraces, int(28 * 3136 / max(W, H)) + 4))
    step = style.terrace_step
    # Real outdoor ground is mostly FLAT with occasional rises: desertdunes has a
    # single height across 311 boundaries, desertshore2 311 flat joins and a
    # handful of steps, g8 143 flat joins with steps of 6-24.  Quantising a noise
    # field gives the opposite -- every cell on a boundary -- so flatten the field
    # towards bands: push each sample to the nearest terrace and only let it move
    # when it is well past the halfway mark.
    plateau = style.plateau
    water_cut = style.water_level if style.water else -1.0

    # quantise into terraces; below the shore level is water
    level = [[None] * cols for _ in range(rows)]
    island = [[False] * cols for _ in range(rows)]
    for y in range(rows):
        for x in range(cols):
            px, py = (x + 0.5) * C, (y + 0.5) * C
            if not on_land(px, py):
                continue
            v = height_at(x, y)
            if v < water_cut:
                level[y][x] = "water"
            else:
                t = (v - max(0.0, water_cut)) / (1.0 - max(0.0, water_cut) or 1.0)
                # `plateau` widens each terrace band: at 0 this is plain rounding
                # (a boundary wherever the field crosses a half-step), at 0.8 the
                # field must climb most of a step before the ground rises, so the
                # map is broad flats with occasional rises, like the real rooms.
                f = t * (n_terraces - 1)
                base = math.floor(f)
                frac = f - base
                level[y][x] = int(base + (1 if frac > 0.5 + plateau * 0.45 else 0))
            if style.island_chance and rnd.random() < style.island_chance:
                island[y][x] = True

    # No two neighbouring cells may differ by more than one terrace.  Quantising
    # a smooth field leaves pockets two terraces below their surroundings, which
    # is a 48-unit step the server will not let a player climb, and the whole map
    # is then rejected as unreachable (the Desert failed 4 of 5 builds this way).
    # Same constraint the cave height fields use: relax it rather than reroll.
    # Water counts as one step below the shore here: a pool left ringed by ground
    # several terraces up is a pit you cannot climb out of, which is what kept
    # failing the Desert (its oases sit in rising dunes; the beach's sea borders
    # the lowest ground, so it escaped).
    def eff(v):
        return -1 if v == "water" else v

    for _ in range(80):
        changed = False
        for y in range(rows):
            for x in range(cols):
                a = eff(level[y][x])
                if not isinstance(a, int):
                    continue
                for dx, dy in ((1, 0), (0, 1)):
                    nx, ny = x + dx, y + dy
                    if nx >= cols or ny >= rows:
                        continue
                    b_ = eff(level[ny][nx])
                    if not isinstance(b_, int):
                        continue
                    if b_ - a > 1 and level[ny][nx] != "water":
                        level[ny][nx] = a + 1
                        changed = True
                    elif a - b_ > 1 and level[y][x] != "water":
                        level[y][x] = b_ + 1
                        changed = True
        if not changed:
            break

    # grow the rock islands a little so they read as outcrops, not speckle
    for _ in range(2):
        grown = [row[:] for row in island]
        for y in range(rows):
            for x in range(cols):
                if island[y][x]:
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            if 0 <= y + dy < rows and 0 <= x + dx < cols and rnd.random() < 0.45:
                                grown[y + dy][x + dx] = True
        island = grown

    # one region per connected patch of equal level
    seen = [[False] * cols for _ in range(rows)]
    pools = terraces = 0
    biggest, biggest_size = None, 0
    for y in range(rows):
        for x in range(cols):
            if seen[y][x] or level[y][x] is None or island[y][x]:
                continue
            L = level[y][x]
            comp, stack = [], [(x, y)]
            seen[y][x] = True
            while stack:
                ax, ay = stack.pop()
                comp.append((ax, ay))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = ax + dx, ay + dy
                    if 0 <= nx < cols and 0 <= ny < rows and not seen[ny][nx] \
                            and level[ny][nx] == L and not island[ny][nx]:
                        seen[ny][nx] = True
                        stack.append((nx, ny))
            if len(comp) < 3:
                continue
            wall = rnd.choice(style.walls)
            gap = rnd.choice(style.gaps)
            if L == "water":
                reg = Region("pool", -style.water_drop, gap, style.water, rnd.choice(style.ceils), wall,
                             flags=style.water_flags)
                pools += 1
            else:
                fh = L * step
                reg = Region("terrace", fh, fh + gap, rnd.choice(style.floors), rnd.choice(style.ceils), wall)
                terraces += 1
            rid = add(reg)
            for ax, ay in comp:
                label[ay][ax] = rid
            if len(comp) > biggest_size:
                biggest, biggest_size = rid, len(comp)
    if biggest is None:
        raise ValueError("no ground")
    return [biggest], {"chambers": 0, "ramps": 0, "ledges": 0, "pools": pools, "patches": terraces}


def generate_cave(width, height, seed, style=ORC):
    """-> (room, summary) in local coordinates with the room box at (0,0)-(width,height)."""
    rnd = random.Random(seed)
    cols, rows = width // C, height // C
    if cols < 3 or rows < 3:
        raise ValueError("too small for the grid")

    regions = [None]                      # label 0 is rock
    label = [[0] * cols for _ in range(rows)]
    layout = _terrain_layout if style.terrain else _chamber_layout
    chamber_region, counts = layout(style, rnd, cols, rows, regions, label)

    def add(region):
        regions.append(region)
        return len(regions) - 1

    def lab(x, y):
        return label[y][x] if 0 <= x < cols and 0 <= y < rows else 0

    # ---- tidy the label grid: no corner-only contacts, no tiny slivers
    def fix_pinches():
        changed = True
        while changed:
            changed = False
            for y in range(rows - 1):
                for x in range(cols - 1):
                    a, b = label[y][x], label[y][x + 1]
                    c, d = label[y + 1][x], label[y + 1][x + 1]
                    if a == d and b == c and a != b:
                        if a == 0:
                            label[y][x] = label[y + 1][x + 1] = b
                        else:
                            label[y][x + 1] = label[y + 1][x] = a
                        changed = True

    def drop_slivers(min_cells=3):
        seen = [[False] * cols for _ in range(rows)]
        for y in range(rows):
            for x in range(cols):
                if seen[y][x]:
                    continue
                L = label[y][x]
                comp, stack = [], [(x, y)]
                seen[y][x] = True
                while stack:
                    cx, cy = stack.pop()
                    comp.append((cx, cy))
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < cols and 0 <= ny < rows and not seen[ny][nx] and label[ny][nx] == L:
                            seen[ny][nx] = True
                            stack.append((nx, ny))
                if len(comp) < min_cells:
                    around = defaultdict(int)
                    for cx, cy in comp:
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            v = lab(cx + dx, cy + dy)
                            if v != L:
                                around[v] += 1
                    if around:
                        fill = max(around, key=around.get)
                        for cx, cy in comp:
                            label[cy][cx] = fill

    fix_pinches()
    drop_slivers()
    fix_pinches()

    if style.terrain:
        # Terrain leaves strays: an islet ringed by rock, a 3-cell shelf two
        # terraces up, a pool in a pocket.  The Desert failed most builds this
        # way (1-11 stranded areas per attempt) while the Beach, with a third as
        # many terraces, never did.  Keep the ground you can walk around and turn
        # the rest back into rock, instead of rerolling the seed.
        for _ in range(6):
            adj, size = defaultdict(set), defaultdict(int)
            for y in range(rows):
                for x in range(cols):
                    A = label[y][x]
                    if not A:
                        continue
                    size[A] += 1
                    for dx, dy in ((1, 0), (0, 1)):
                        B = lab(x + dx, y + dy)
                        if B and B != A:
                            adj[A].add(B)
                            adj[B].add(A)
            if not size:
                raise ValueError("no ground")
            steps = defaultdict(set)
            for A, nbrs in adj.items():
                for B in nbrs:
                    if regions[B].floorh - regions[A].floorh <= MAX_STEP:
                        steps[A].add(B)
                    if regions[A].floorh - regions[B].floorh <= MAX_STEP:
                        steps[B].add(A)
            main = max(size, key=size.get)
            keep, queue = {main}, deque([main])
            while queue:
                v = queue.popleft()
                for w in steps[v]:
                    if w not in keep and v in steps[w]:      # and you can get back
                        keep.add(w)
                        queue.append(w)
            if len(keep) == len(size):
                break
            for y in range(rows):
                for x in range(cols):
                    if label[y][x] and label[y][x] not in keep:
                        label[y][x] = 0
            fix_pinches()
            drop_slivers(6)
            fix_pinches()

    used = sorted({label[y][x] for y in range(rows) for x in range(cols)} - {0})
    if not used:
        raise ValueError("no floor")

    # normalise heights: the server reads floor/ceiling heights as unsigned
    low = min(min([regions[r].floorh] + (list(regions[r].ramp[6:8]) if regions[r].ramp else [])) for r in used)
    for r in range(1, len(regions)):
        regions[r].shift(-low)
    if style.wall_height:
        # snap every floor and ceiling to the texture grid, so each wall part --
        # a room's full height, a step's face, the gap under a lower ceiling --
        # comes out a whole number of wall textures
        u = style.wall_height
        for r in used:
            reg = regions[r]
            reg.floorh = int(round(reg.floorh / u)) * u
            reg.ceilh = max(int(round(reg.ceilh / u)) * u, reg.floorh + u * max(1, -(-HEADROOM // u)))
            if reg.ramp:
                ax, ay, ux, uy, s0, s1, h0, h1 = reg.ramp
                reg.ramp = (ax, ay, ux, uy, s0, s1, int(round(h0 / u)) * u, int(round(h1 / u)) * u)

    if style.sky:
        # outdoors every area shares one sky height, so no upper wall textures
        # are drawn against the sky (as in the shipped outdoor rooms)
        top = max(max([regions[r].floorh] + (list(regions[r].ramp[6:8]) if regions[r].ramp else [])) for r in used)
        for r in used:
            regions[r].ceil = 0
            regions[r].ceilh = top + style.sky_gap
    if max(regions[r].ceilh for r in used) > 32767:
        raise ValueError("heights overflow")

    # ---- boundary chains, each shared by the region on its left and the one on its right
    half = []
    for y in range(rows):
        for x in range(cols):
            A = label[y][x]
            if not A:
                continue
            for nx, ny, s, e in ((x, y - 1, (x, y), (x + 1, y)), (x, y + 1, (x + 1, y + 1), (x, y + 1)),
                                 (x - 1, y, (x, y + 1), (x, y)), (x + 1, y, (x + 1, y), (x + 1, y + 1))):
                B = lab(nx, ny)
                if B == A or (B and B < A):
                    continue
                half.append((s, e, A, B))
    by_start, by_end = defaultdict(list), defaultdict(list)
    for idx, (s, e, A, B) in enumerate(half):
        by_start[(s, A, B)].append(idx)
        by_end[(e, A, B)].append(idx)

    def vlabels(v):
        x, y = v
        return len({lab(x - 1, y - 1), lab(x, y - 1), lab(x - 1, y), lab(x, y)})

    def junction(v, A, B):
        return vlabels(v) >= 3 or len(by_start[(v, A, B)]) != 1 or len(by_end[(v, A, B)]) != 1

    used_half, chains = set(), []
    for idx in range(len(half)):
        if idx in used_half:
            continue
        _s, _e, A, B = half[idx]
        cur = idx
        while True:
            v = half[cur][0]
            if junction(v, A, B):
                break
            prev = by_end[(v, A, B)][0]
            if prev == idx:
                break
            cur = prev
        start = cur
        pts, closed = [half[start][0]], False
        while True:
            used_half.add(cur)
            e = half[cur][1]
            pts.append(e)
            if junction(e, A, B):
                break
            nxt = by_start[(e, A, B)][0]
            if nxt == start:
                closed = True
                break
            if nxt in used_half:
                break
            cur = nxt
        chains.append((pts, A, B, closed))

    def smooth(pts, closed, window=2, passes=2):
        n_ = len(pts)
        for _ in range(passes):
            if closed:
                pts = [(sum(pts[(i + k) % n_][0] for k in range(-window, window + 1)) / (2 * window + 1),
                        sum(pts[(i + k) % n_][1] for k in range(-window, window + 1)) / (2 * window + 1))
                       for i in range(n_)]
            else:
                new = [pts[0]]
                for i in range(1, n_ - 1):
                    kk = min(window, i, n_ - 1 - i)
                    seg = pts[i - kk:i + kk + 1]
                    new.append((sum(p[0] for p in seg) / len(seg), sum(p[1] for p in seg) / len(seg)))
                new.append(pts[-1])
                pts = new
        return pts

    simple = []
    for pts, A, B, closed in chains:
        pts = [(x * C, y * C) for x, y in pts]
        if closed:
            loop = smooth(pts[:-1], True)
            far = max(range(len(loop)), key=lambda q: (loop[q][0] - loop[0][0]) ** 2 + (loop[q][1] - loop[0][1]) ** 2)
            out = rdp(loop[:far + 1], 8)[:-1] + rdp(loop[far:] + [loop[0]], 8)
        else:
            out = rdp(smooth(pts, False), 8)
        out = [(int(round(x)), int(round(y))) for x, y in out]
        dedup = [out[0]]
        for q in out[1:]:
            if q != dedup[-1]:
                dedup.append(q)
        if len(dedup) >= 2:
            simple.append((dedup, A, B))

    # ---- build
    b = RoomBuilder((0, 0, width, height))
    sector_of = {}
    for rid in used:
        reg = regions[rid]
        sec = b.add_sector(reg.floor, reg.ceil, int(reg.floorh), int(reg.ceilh), style.light, flags=reg.flags)
        if reg.ramp:
            ax, ay, ux, uy, s0, s1, h0, h1 = reg.ramp
            p0 = (ax + ux * s0, ay + uy * s0)
            p1 = (ax + ux * s1, ay + uy * s1)
            p2 = (p0[0] - uy * 64, p0[1] + ux * 64)
            pts3 = [(round(p0[0]), round(p0[1]), round(h0)), (round(p1[0]), round(p1[1]), round(h1)),
                    (round(p2[0]), round(p2[1]), round(h0))]
            b.sectors[sec].floor_slope = make_slope(pts3, 0, height, floor=True)
            b.sectors[sec].blak_flags |= SF_SLOPED_FLOOR
        sector_of[rid] = sec

    graph = defaultdict(set)
    floor_area2 = 0.0
    for pts, A, B in simple:
        ra = regions[A]
        rb = regions[B] if B else None
        # decided per boundary, not per segment, so a whole opening is curtained
        web = style.web if (B and style.web and rnd.random() < style.web_chance) else 0
        for p, q in zip(pts, pts[1:]):
            left, _right = side_points(p, q)
            if not B:
                floor_area2 += p[0] * q[1] - q[0] * p[1]
                b.add_wall_facing(p[0], p[1], q[0], q[1], left, b.add_sidedef(ra.wall), sector_of[A])
                continue
            samples = [p, q, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)]

            def facing(view, other):
                below = other.wall if any(other.fh(*t) - view.fh(*t) > 0.5 for t in samples) else 0
                above = view.wall if any(other.ch(*t) < view.ch(*t) - 0.5 for t in samples) else 0
                return b.add_sidedef(web, above=above, below=below,
                                     flags=TWO_SIDED_FLAGS | (WF_TRANSPARENT if web else 0))

            def can_move(src, dst):
                return all(dst.fh(*t) - src.fh(*t) <= MAX_STEP and dst.ch(*t) - src.fh(*t) >= HEADROOM
                           and dst.ch(*t) - dst.fh(*t) >= HEADROOM for t in samples)

            b.add_wall_facing(p[0], p[1], q[0], q[1], left, facing(ra, rb), sector_of[A],
                              neg_sidedef=facing(rb, ra), neg_sector=sector_of[B])
            if can_move(ra, rb):
                graph[A].add(B)
            if can_move(rb, ra):
                graph[B].add(A)

    if style.terrain:
        # Flat terrain: judge reachability on the cell grid, not on the walls that
        # survived simplifying.  Where two terraces share only a sliver of border,
        # that border can simplify away to nothing, so no wall records the link
        # even though you walk straight across -- which rejected most large
        # Deserts while the pruning pass itself settled with nothing stranded.
        graph = defaultdict(set)
        for y in range(rows):
            for x in range(cols):
                A = label[y][x]
                if not A:
                    continue
                for dx, dy in ((1, 0), (0, 1)):
                    B = lab(x + dx, y + dy)
                    if not B or B == A:
                        continue
                    ra, rb = regions[A], regions[B]
                    if rb.floorh - ra.floorh <= MAX_STEP and rb.ceilh - ra.floorh >= HEADROOM:
                        graph[A].add(B)
                    if ra.floorh - rb.floorh <= MAX_STEP and ra.ceilh - rb.floorh >= HEADROOM:
                        graph[B].add(A)

    # every region reachable from the largest one, and able to get back
    start = chamber_region[0] if chamber_region and chamber_region[0] in sector_of else used[0]

    def reach(g):
        seen_, q_ = {start}, deque([start])
        while q_:
            v = q_.popleft()
            for w in g[v]:
                if w not in seen_:
                    seen_.add(w)
                    q_.append(w)
        return seen_
    reverse = defaultdict(set)
    for v, ws in list(graph.items()):
        for w in ws:
            reverse[w].add(v)
    missing = set(used) - (reach(graph) & reach(reverse))
    if missing:
        raise ValueError("%d areas cannot be reached and left again" % len(missing))

    segs = [((w[0], w[1]), (w[2], w[3])) for w in b.walls]
    boxes = [(min(s[0][0], s[1][0]), min(s[0][1], s[1][1]), max(s[0][0], s[1][0]), max(s[0][1], s[1][1])) for s in segs]
    order = sorted(range(len(segs)), key=lambda i: boxes[i][0])
    for ii, i in enumerate(order):
        for j in order[ii + 1:]:
            if boxes[j][0] > boxes[i][2]:
                break
            if boxes[j][1] > boxes[i][3] or boxes[j][3] < boxes[i][1]:
                continue
            if crosses(segs[i], segs[j]):
                raise ValueError("walls cross")

    room = b.build()
    leaf_area = 0.0
    for node in room.bsp.walk():
        if node.type == BSP_LEAF and node.sector:
            pp = node.points
            leaf_area += abs(sum(pp[i][0] * pp[(i + 1) % len(pp)][1] - pp[(i + 1) % len(pp)][0] * pp[i][1]
                                 for i in range(len(pp)))) / 2
    floor_area = floor_area2 / 2 * BLAK * BLAK
    if floor_area <= 0 or abs(leaf_area / floor_area - 1) >= 1e-6:
        raise ValueError("not sealed: %f" % (leaf_area / floor_area if floor_area else 0))
    align_room(room)

    floors = [regions[r].floorh for r in used]
    highest = max(floors + [max(regions[r].ramp[6:8]) for r in used if regions[r].ramp])
    if style.terrain:
        summary = "%d terraces, %d pools, %d floor levels, floors %d..%d, %d walls" % (
            counts["patches"], counts["pools"], len({regions[r].floorh for r in used}),
            min(floors), highest, len(room.linedefs))
    else:
        summary = "%d chambers, %d ramps, %d ledges, %d pools, %d patches, floors %d..%d, %d walls" % (
            counts["chambers"], counts["ramps"], counts["ledges"], counts["pools"], counts["patches"],
            min(floors), highest, len(room.linedefs))
    return room, summary
