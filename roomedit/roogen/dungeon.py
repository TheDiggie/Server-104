"""
dungeon.py -- chambers joined by corridors, on building2's 16-unit cell grid:
the engine behind the Marion Crypt and Sewer styles.

Why a third engine.  The town engine splits a rectangle into rooms that fill it,
and the cave engine grows blobby chambers.  The crypt and sewer rooms are
neither: measured from mardun01/02/03 + marcrypt4 and barlsew1-3 + jassew1-3,
they are small chambers strung on narrow corridors -- median wall length 24-32
(crypt) and 64 (sewer), only 11-42% and 11-26% angled walls, with a great many
floor levels (80-94 in a crypt) in small steps.

Movement (building2.compile_plan): a blocked edge is simply emitted as a wall,
and ValueError is raised only when neither side is `barrier`, when a ceilinged
zone has under 48 of headroom, or when the room does not seal.  Connectivity is
NOT checked there, so a corridor that dead-ends behind a blocked edge would pass
silently -- this module checks reachability itself and raises ValueError so
styles.generate simply tries another seed.

Heights therefore obey: every step <= STEP (16) and every gap >= 64, which keeps
`dest ceiling - source floor >= 48` on every join (64 - 16 = 48).
"""
import math
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from building2 import CELL, Plan, Zone, compile_plan  # noqa: E402
from cave import HEADROOM, MAX_STEP  # noqa: E402
from generate import SizeError, recentre  # noqa: E402

PAD = 2
STEP = 16                      # max floor step between neighbouring areas
MIN_CELLS = 24                 # a chamber, a corridor and a chamber


class Dungeon:
    """Palette and shape of one underground style."""

    def __init__(self, name, walls, floors, ceils, light, gaps, corridor_gaps,
                 room_cells=(5, 12), corridor_width=(3, 4), per_room=420, trim=None, relief=48,
                 water=0, water_flags=0xaa, water_drop=32, water_chance=0.0, water_floor=0,
                 tomb=0, tomb_chance=0.0, tomb_rise=32, alcove_chance=0.0,
                 round_chance=0.0, chamfer_chance=0.0):
        self.name = name
        self.walls, self.floors, self.ceils = list(walls), list(floors), list(ceils)
        self.light = light
        self.gaps, self.corridor_gaps = list(gaps), list(corridor_gaps)
        self.room_cells, self.corridor_width = room_cells, corridor_width
        self.per_room, self.trim, self.relief = per_room, trim, relief
        self.water, self.water_flags = water, water_flags
        self.water_drop, self.water_chance = water_drop, water_chance
        self.water_floor = water_floor or water
        self.tomb, self.tomb_chance, self.tomb_rise = tomb, tomb_chance, tomb_rise
        self.alcove_chance = alcove_chance
        self.round_chance, self.chamfer_chance = round_chance, chamfer_chance
        assert min(self.gaps + self.corridor_gaps) - STEP >= HEADROOM, \
            "a gap under %d would make some joins impassable" % (HEADROOM + STEP)


def _apart(a, b, gap):
    return (a[0] - gap > b[2] or b[0] - gap > a[2] or a[1] - gap > b[3] or b[1] - gap > a[3])


def _centre(r):
    return ((r[0] + r[2]) // 2, (r[1] + r[3]) // 2)


def generate(dg, width, height, seed):
    rnd = random.Random(seed)
    cw, ch = width // CELL - 2 * PAD, height // CELL - 2 * PAD
    if cw < MIN_CELLS or ch < MIN_CELLS:
        need = (MIN_CELLS + 2 * PAD) * CELL
        raise SizeError("a %s needs at least %d x %d editor units (two chambers and a corridor on a %d-unit "
                        "grid); you entered %d x %d" % (dg.name, need, need, CELL, width, height))
    p = Plan(cw + 2 * PAD, ch + 2 * PAD)
    X0, Y0, X1, Y1 = PAD, PAD, PAD + cw - 1, PAD + ch - 1

    # ---- chambers
    rooms = []
    target = max(2, int(cw * ch / dg.per_room * rnd.uniform(0.75, 1.25)))
    for _ in range(target * 40):
        if len(rooms) >= target:
            break
        w = rnd.randint(*dg.room_cells)
        h = rnd.randint(*dg.room_cells)
        if w > cw - 2 or h > ch - 2:
            continue
        x = rnd.randint(X0, X1 - w + 1)
        y = rnd.randint(Y0, Y1 - h + 1)
        rect = (x, y, x + w - 1, y + h - 1)
        if all(_apart(rect, r, 3) for r in rooms):
            rooms.append(rect)
    if len(rooms) < 2:
        raise ValueError("no space for two chambers")

    # ---- a spanning tree over the chambers, so everything is connected, plus a
    # few extra links so the plan is a network rather than a strict tree
    linked, rest = [0], list(range(1, len(rooms)))
    edges = []
    while rest:
        best = min(((a, b) for a in linked for b in rest),
                   key=lambda ab: abs(_centre(rooms[ab[0]])[0] - _centre(rooms[ab[1]])[0])
                   + abs(_centre(rooms[ab[0]])[1] - _centre(rooms[ab[1]])[1]))
        edges.append(best)
        linked.append(best[1])
        rest.remove(best[1])
    for _ in range(len(rooms) // 4):
        a, b = rnd.randrange(len(rooms)), rnd.randrange(len(rooms))
        if a != b and (a, b) not in edges and (b, a) not in edges:
            edges.append((a, b))

    # ---- heights come from a smooth SPATIAL field, not from a walk over the
    # connection tree.  A tree walk keeps linked areas close, but says nothing
    # about two areas that merely end up touching -- and with chambers packed a
    # few cells apart that happens constantly, so an unrelated corridor landed
    # beside a chamber 96 units below it: a blocked edge with neither side a
    # barrier, which is exactly what compile_plan rejects ("chamber 7 <-> corridor
    # 3-9: floor 0/96").  With a field, anything near anything else is at a
    # similar height by construction, whatever the plan does.
    # Wavelength >= 28 cells against a relief of 48 keeps the gradient under
    # 3 units per cell, so even a 10-cell chamber's edges stay within one step.
    phase_x, phase_y = rnd.uniform(0, 2 * math.pi), rnd.uniform(0, 2 * math.pi)
    wave_x, wave_y = rnd.uniform(28, 55), rnd.uniform(28, 55)

    def field(x, y):
        v = (math.sin(x / wave_x + phase_x) + math.sin(y / wave_y + phase_y)) / 2.0    # -1..1
        return int(round(dg.relief * (v + 1) / 2 / 8.0)) * 8     # 0..relief, in 8s, never negative

    floorh = {i: field(*_centre(r)) for i, r in enumerate(rooms)}

    # ---- paint the chambers
    zones = {}
    for i, r in enumerate(rooms):
        gap = rnd.choice(dg.gaps)
        z = Zone("chamber %d" % (i + 1), floorh[i], floorh[i] + gap,
                 rnd.choice(dg.floors), rnd.choice(dg.ceils), rnd.choice(dg.walls), dg.light,
                 trim=dg.trim, chamfer=rnd.random() < dg.chamfer_chance)
        zones[i] = z
        w, h = r[2] - r[0] + 1, r[3] - r[1] + 1
        if dg.round_chance and min(w, h) >= 7 and rnd.random() < dg.round_chance:
            cx, cy = _centre(r)
            p.octagon(cx + 0.5, cy + 0.5, min(w, h) / 2.0 - 0.5, z)
        else:
            p.rect(*r, z)

    # ---- corridors, carved only into solid ground so chambers keep their shape
    corridors = 0
    for a, b in edges:
        ax, ay = _centre(rooms[a])
        bx, by = _centre(rooms[b])
        gap = rnd.choice(dg.corridor_gaps)
        floor_t, ceil_t, wall_t = rnd.choice(dg.floors), rnd.choice(dg.ceils), rnd.choice(dg.walls)
        # one zone per height the corridor passes through, so a long corridor
        # steps gently along with the ground instead of holding one level and
        # meeting its far end with a cliff
        seg_zones = {}

        def corridor_zone(h):
            if h not in seg_zones:
                seg_zones[h] = Zone("corridor %d-%d at %d" % (a + 1, b + 1, h), h, h + gap,
                                    floor_t, ceil_t, wall_t, dg.light, trim=dg.trim)
            return seg_zones[h]
        wdt = rnd.randint(*dg.corridor_width)
        cells = []
        if rnd.random() < 0.5:
            cells += [(x, ay) for x in range(min(ax, bx), max(ax, bx) + 1)]
            cells += [(bx, y) for y in range(min(ay, by), max(ay, by) + 1)]
        else:
            cells += [(ax, y) for y in range(min(ay, by), max(ay, by) + 1)]
            cells += [(x, by) for x in range(min(ax, bx), max(ax, bx) + 1)]
        painted = 0
        for x, y in cells:
            for dx in range(wdt):
                for dy in range(wdt):
                    cx, cy = x + dx - wdt // 2, y + dy - wdt // 2
                    if X0 <= cx <= X1 and Y0 <= cy <= Y1 and p.g[cy][cx] is None:
                        p.g[cy][cx] = corridor_zone(field(cx, cy))
                        painted += 1
        if painted:
            corridors += 1
            for z in seg_zones.values():
                p._note(z, "corridor")

    # ---- a water channel down some corridors (sewers).  It is `barrier`, so the
    # engine emits its edges as walls instead of rejecting the map: you walk the
    # ledge beside it, as in barlsew.
    pools = 0
    if dg.water and dg.water_chance:
        for a, b in edges:
            if rnd.random() >= dg.water_chance:
                continue
            ax, ay = _centre(rooms[a])
            bx, by = _centre(rooms[b])
            if abs(ax - bx) >= abs(ay - by):
                span = [(x, ay) for x in range(min(ax, bx) + 2, max(ax, bx) - 1)]
            else:
                span = [(ax, y) for y in range(min(ay, by) + 2, max(ay, by) - 1)]
            made = False
            for x, y in span:
                z = p.g[y][x]
                if isinstance(z, Zone) and z.name.startswith("corridor"):
                    p.g[y][x] = Zone("channel", z.floorh - dg.water_drop, z.ceilh, dg.water_floor, z.ceil,
                                     z.wall, dg.light, trim=dg.trim, flags=dg.water_flags, barrier=True)
                    made = True
            pools += 1 if made else 0

    # ---- tombs: raised slabs against a chamber wall, impassable like the real ones
    tombs = 0
    if dg.tomb and dg.tomb_chance:
        for i, r in enumerate(rooms):
            z = zones[i]
            if z.ceilh - (z.floorh + dg.tomb_rise) < HEADROOM:
                continue                       # a low chamber simply gets none
            for _ in range(rnd.randint(1, 3)):
                if rnd.random() >= dg.tomb_chance:
                    continue
                tw, th = rnd.choice([(2, 3), (3, 2), (2, 4), (4, 2)])
                if r[2] - r[0] < tw + 2 or r[3] - r[1] < th + 2:
                    continue
                tx = rnd.randint(r[0] + 1, r[2] - tw)
                ty = rnd.randint(r[1] + 1, r[3] - th)
                cells = [(x, y) for y in range(ty, ty + th) for x in range(tx, tx + tw)]
                if all(p.g[y][x] is z for x, y in cells):
                    tomb = Zone("tomb %d" % (tombs + 1), z.floorh + dg.tomb_rise, z.ceilh, dg.tomb,
                                z.ceil, z.wall, dg.light, trim=dg.tomb, barrier=True)
                    for x, y in cells:
                        p.g[y][x] = tomb
                    tombs += 1

    # ---- reachability, which compile_plan does not check
    def blocked(a, c):
        return (c.floorh - a.floorh > MAX_STEP or c.ceilh - a.floorh < HEADROOM
                or (c.ceil and c.ceilh - c.floorh < HEADROOM))

    # ---- lift everything clear of zero.  The field starts at 0, so a water
    # channel dropped 32 below its corridor lands at -32, and blakserv reads
    # sector heights UNSIGNED -- a negative floor is silently enormous in game.
    # Done after every zone exists (channels and tombs included), and it shifts
    # floors and ceilings together so no join changes.
    placed = {id(z): z for row in p.g for z in row if isinstance(z, Zone)}
    low = min(z.floorh for z in placed.values())
    if low < 0:
        for z in placed.values():
            z.floorh -= low
            z.ceilh -= low

    # Judge a chamber by ALL of its open cells, never by its centre cell alone: a
    # tomb is a `barrier` the walk cannot enter, and with tombs common it often
    # sits on the very centre, which reported 21 of 133 perfectly walkable
    # chambers as stranded and rejected every large crypt.
    room_cells = []
    for r in rooms:
        cells = set()
        for y in range(r[1], r[3] + 1):
            for x in range(r[0], r[2] + 1):
                z = p.g[y][x]
                if isinstance(z, Zone) and not z.barrier:
                    cells.add((x, y))
        room_cells.append(cells)
    start = None
    for cells in room_cells:
        if cells:
            start = min(cells)
            break
    if start is None:
        raise ValueError("no open chamber cell to start from")
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        z = p.g[y][x]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) in seen or not (0 <= nx < p.w and 0 <= ny < p.h):
                continue
            o = p.g[ny][nx]
            if not isinstance(o, Zone) or o.barrier or blocked(z, o) or blocked(o, z):
                continue
            seen.add((nx, ny))
            stack.append((nx, ny))
    # a chamber buried entirely under tombs has no open cells and is not stranded
    stranded = [i for i, cells in enumerate(room_cells) if cells and not (cells & seen)]
    if stranded:
        raise ValueError("%d of %d chambers cannot be walked to" % (len(stranded), len(rooms)))

    room, _info = compile_plan(p, verbose=False)
    recentre(room, width, height)
    levels = sorted({s.floorh for s in room.sectors})
    summary = "%d chambers, %d corridors, %d tombs, %d channels, %d floor levels, floors %d..%d, %d walls" % (
        len(rooms), corridors, tombs, pools, len(levels), levels[0], levels[-1], len(room.linedefs))
    return room, summary
