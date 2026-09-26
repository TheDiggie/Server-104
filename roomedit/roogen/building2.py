#!/usr/bin/env python3
"""
building2.py -- a more complex building interior than building.py: a castle
compound built on a finer 16-unit cell grid with 45-degree chamfers, so rooms
can be round or octagonal.

For opening in the room editor; not wired into the game.

What is in it, and the shipped rooms each value was taken from:
  * courtyard open to the sky (ceiling_type 0) with a round pool of scrolling
    deep water (8895, flags 0xaa: SF_SCROLL_FLOOR | E | medium | depth 2 --
    the most common water setup in the shipped rooms) and a round fountain base
  * great hall: octagonal pillars, dais with rails, throne alcove, raised
    balconies down both sides with stairs, grand doorway with a door wall (id 1)
  * octagonal chapel: raised round apse, pews you can step onto, window slits
    into the courtyard (1501 at 0x202, as shipped windows use), door wall (id 2)
  * round tower: a 16-step spiral stair wrapped round a central column
  * crypt: long stair down from the courtyard, dark hall, raised tombs you
    cannot walk over, flickering torch spots (SF_FLICKER)

Door walls use texture 30 at flags 0x206, the only textured KOD door walls in
the shipped rooms.  Door ids are sidedef ids: AnimateWall(#wall=<id>).

Movement: every passable edge is checked against blakserv's three movement
rules.  An edge that breaks them is only allowed where one side is a zone
marked `barrier` (tombs, balcony edges, windows); those walls are emitted
without WF_PASSABLE.

Usage:  python roomedit/roogen/building2.py        (run from the repo root)
Writes: out/castle_compound.roo, out/castle_compound.txt
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from generate import RoomBuilder  # noqa: E402
from cave import _merge_collinear, MAX_STEP, HEADROOM, STEP_FLAGS  # noqa: E402
from roofile import Room, BSP_LEAF  # noqa: E402

CELL = 16
W, H = 200, 150
MARGIN = 128
CHAMFER = 0.5

WF_TRANSPARENT = 0x02
WF_MAP_NEVER = 0x08
WF_NO_VTILE = 0x200
SF_FLICKER = 0x200
WATER_FLAGS = 0xaa
WINDOW_FLAGS = WF_TRANSPARENT | WF_NO_VTILE          # 0x202
DOOR_FLAGS = 0x206
DOOR_TEX = 30
WINDOW_TEX = 1501

# textures (castle1/castle1c, temple, castle2, toscrypt palettes)
STONE_FLOOR, HALL_CEIL, HALL_WALL = 2104, 2016, 2103
PLAIN, TILE, DAIS_FLOOR, WOOD, PANEL = 2011, 2123, 4410, 1602, 2012
PILLAR, DARK_STONE, BRICK, FLAG = 4407, 1701, 3101, 4601
GRASS, WATER = 2303, 8895
CHAPEL_FLOOR, CHAPEL_CEIL, CHAPEL_WALL = 4408, 4503, 3401
TOWER_FLOOR, TOWER_CEIL, TOWER_WALL = 2126, 1703, 3404
CRYPT_WALL, CRYPT_CEIL = 2031, 2003

GROUND = 128


class Zone:
    def __init__(self, name, floorh, ceilh, floor, ceil, wall, light=160, trim=None,
                 flags=0, barrier=False, chamfer=False, door=None, window=False, banner=0):
        self.name = name
        self.floorh, self.ceilh = floorh, ceilh
        self.floor, self.ceil, self.wall = floor, ceil, wall
        self.trim = trim or wall
        self.light, self.flags = light, flags
        self.barrier, self.chamfer = barrier, chamfer
        self.door, self.window = door, window
        # Banner niche, as every Barloque building has them (barlbar1 sector 35,
        # barinn 22): a shallow recess with no floor/ceiling texture whose OPENING
        # shows a banner (4802-4807) with the room's wall above and below, flags
        # 0, and untextured back walls flagged WF_MAP_NEVER.
        self.banner = banner

    def key(self):
        return (self.floorh, self.ceilh, self.floor, self.ceil, self.light, self.flags)


class Solid:
    def __init__(self, tex, round_=False):
        self.tex, self.round = tex, round_


class Plan:
    def __init__(self, w=W, h=H):
        self.w, self.h = w, h
        self.g = [[None] * w for _ in range(h)]
        self.legend = []

    def _note(self, z, where):
        if isinstance(z, Zone) and z.name not in [l[0] for l in self.legend]:
            self.legend.append((z.name, where, z))

    def cells(self, test, z, where):
        for y in range(self.h):
            for x in range(self.w):
                if test(x + 0.5, y + 0.5):
                    self.g[y][x] = z
        self._note(z, where)

    def rect(self, x0, y0, x1, y1, z):
        self.cells(lambda x, y: x0 <= x < x1 + 1 and y0 <= y < y1 + 1, z,
                   "rect x %d-%d y %d-%d" % (x0 * CELL, (x1 + 1) * CELL, y0 * CELL, (y1 + 1) * CELL))

    def circle(self, cx, cy, r, z):
        self.cells(lambda x, y: math.hypot(x - cx, y - cy) <= r, z,
                   "circle at (%d, %d) radius %d" % (cx * CELL, cy * CELL, r * CELL))

    def octagon(self, cx, cy, r, z):
        self.cells(lambda x, y: max(abs(x - cx), abs(y - cy)) <= r
                   and abs(x - cx) + abs(y - cy) <= r * 1.35, z,
                   "octagon at (%d, %d) radius %d" % (cx * CELL, cy * CELL, r * CELL))


def build_plan():
    p = Plan()

    # ---- great hall (north)
    hall = Zone("great hall", GROUND, 352, STONE_FLOOR, HALL_CEIL, HALL_WALL, 200)
    p.rect(60, 10, 140, 45, hall)
    for px in (75, 88, 109, 122):
        for py in (20, 33):
            p.octagon(px + 1.5, py + 1.5, 2.5, Solid(PILLAR, round_=True))
    # dais, reached from the front only
    p.rect(90, 15, 110, 15, Zone("dais step 1", 144, 352, TILE, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    p.rect(90, 14, 110, 14, Zone("dais step 2", 160, 352, TILE, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    p.rect(90, 10, 110, 13, Zone("dais", 176, 352, DAIS_FLOOR, HALL_CEIL, HALL_WALL, 200, trim=PILLAR))
    p.rect(89, 10, 89, 15, Solid(PILLAR))
    p.rect(111, 10, 111, 15, Solid(PILLAR))
    p.rect(95, 3, 105, 9, Zone("throne alcove", 176, 280, DAIS_FLOOR, WOOD, PANEL, 180))
    # balconies down both sides, each with a stair at its south end
    for side, bx0 in (("west", 60), ("east", 133)):
        p.rect(bx0, 10, bx0 + 7, 38, Zone("%s balcony" % side, 200, 352, WOOD, HALL_CEIL, HALL_WALL, 190,
                                          trim=PILLAR, barrier=True))
        for i in range(6):
            fh = 188 - 12 * i
            p.rect(bx0, 39 + i, bx0 + 7, 39 + i,
                   Zone("%s balcony stair %d" % (side, 6 - i), fh, 352, BRICK, HALL_CEIL, HALL_WALL, 190,
                        trim=PILLAR, barrier=True))
    # grand doorway through the hall's south wall; the door is its courtyard face
    p.rect(95, 46, 105, 54, Zone("grand doorway", GROUND, 240, FLAG, PLAIN, PLAIN, 170,
                                 door=(1, "courtyard")))

    # ---- courtyard (centre), open sky
    court = Zone("courtyard", GROUND, 512, GRASS, 0, PLAIN, 210, chamfer=True)
    p.rect(70, 55, 130, 100, court)
    p.circle(100, 77, 11, Zone("pool", 104, 512, WATER, 0, PLAIN, 210, trim=PILLAR, flags=WATER_FLAGS,
                               chamfer=True))
    p.circle(100, 77, 3.2, Solid(PILLAR, round_=True))

    # ---- octagonal chapel (west)
    chapel = Zone("chapel", GROUND, 320, CHAPEL_FLOOR, CHAPEL_CEIL, CHAPEL_WALL, 170, chamfer=True)
    p.octagon(35, 77, 26, chapel)
    p.circle(17, 77, 8, Zone("apse step", 140, 320, CHAPEL_FLOOR, CHAPEL_CEIL, CHAPEL_WALL, 180,
                             trim=PILLAR, chamfer=True))
    p.circle(15, 77, 5, Zone("altar", 152, 320, DAIS_FLOOR, CHAPEL_CEIL, CHAPEL_WALL, 190,
                             trim=PILLAR, chamfer=True))
    for py in (62, 66, 70, 82, 86, 90):
        p.rect(32, py, 52, py + 1, Zone("pews", 148, 320, WOOD, CHAPEL_CEIL, CHAPEL_WALL, 170, trim=WOOD))
    p.rect(61, 74, 69, 80, Zone("chapel passage", GROUND, 208, FLAG, PLAIN, PLAIN, 160, door=(2, "courtyard")))
    for wy in (64, 89):
        p.rect(62, wy, 69, wy + 1, Zone("chapel windows", 176, 232, FLAG, PLAIN, PLAIN, 170, trim=PLAIN,
                                        barrier=True, window=True))

    # ---- round tower with a spiral stair (east)
    tcx, tcy, tr = 170, 77, 22
    p.rect(131, 78, 149, 81, Zone("tower passage", GROUND, 208, FLAG, PLAIN, PLAIN, 160))
    entry = math.atan2(79.5 - tcy, 148.5 - tcx)          # where the passage meets the ring
    steps = 16

    def offset(x, y):
        return (math.atan2(y - tcy, x - tcx) - entry) % (2 * math.pi)

    # pick the winding so the passage mouth sits at the START of the spiral
    sign = 1 if offset(148.5, 81.5) < math.pi else -1

    def turn(x, y):
        return (sign * (math.atan2(y - tcy, x - tcx) - entry) + 0.25) % (2 * math.pi)

    for i in range(steps):
        fh = GROUND + 16 * i
        lo, hi = 2 * math.pi * i / steps, 2 * math.pi * (i + 1) / steps
        p.cells(lambda x, y, lo=lo, hi=hi: math.hypot(x - tcx, y - tcy) <= tr and lo <= turn(x, y) < hi,
                Zone("spiral step %d" % (i + 1), fh, fh + 136, TOWER_FLOOR, TOWER_CEIL, TOWER_WALL, 150,
                     trim=PILLAR, chamfer=True),
                "wedge of circle at (%d, %d) radius %d" % (tcx * CELL, tcy * CELL, tr * CELL))
    # the top step must not meet the bottom one: a solid radial wall between them
    p.cells(lambda x, y: math.hypot(x - tcx, y - tcy) <= tr + 1 and turn(x, y) > 2 * math.pi - 0.22,
            Solid(TOWER_WALL), "")
    p.circle(tcx, tcy, 5, Solid(TOWER_WALL, round_=True))

    # ---- crypt (south), down a long stair from the courtyard
    for i in range(8):
        fh = 112 - 16 * i
        p.rect(96, 101 + i, 104, 101 + i,
               Zone("crypt stair %d" % (i + 1), fh, fh + 128, BRICK, CRYPT_CEIL, CRYPT_WALL, 120 - 8 * i, trim=PILLAR))
    crypt = Zone("crypt", 0, 112, PLAIN, CRYPT_CEIL, CRYPT_WALL, 60)
    p.rect(66, 109, 134, 146, crypt)
    for tx in (74, 86, 110, 122):
        for ty in (116, 132):
            p.rect(tx, ty, tx + 4, ty + 9, Zone("tombs", 40, 112, DARK_STONE, CRYPT_CEIL, CRYPT_WALL, 60,
                                                trim=DARK_STONE, barrier=True))
    for tx, ty in ((67, 112), (67, 140), (132, 112), (132, 140), (99, 145)):
        p.rect(tx, ty, tx + 1, ty + 1, Zone("torch light", 0, 112, PLAIN, CRYPT_CEIL, CRYPT_WALL, 150,
                                            flags=SF_FLICKER))
    return p


def main():
    return emit(build_plan(), "castle_compound", "Castle compound")


def compile_plan(p, verbose=True):
    """Turn a Plan into a checked, texture-aligned Room.

    Raises ValueError when a passable edge breaks blakserv's movement rules or
    the room does not seal, so a random generator can simply try another seed.
    Returns (room, info)."""
    g = p.g
    W, H = p.w, p.h

    def zone(x, y):
        if 0 <= x < W and 0 <= y < H and isinstance(g[y][x], Zone):
            return g[y][x]
        return None

    def solid(x, y):
        return zone(x, y) is None

    def solid_round(x, y):
        c = g[y][x] if 0 <= x < W and 0 <= y < H else None
        return isinstance(c, Solid) and c.round

    b = RoomBuilder((-MARGIN, -MARGIN, W * CELL + MARGIN, H * CELL + MARGIN))
    sector_of = {}
    for row in g:
        for z in row:
            if isinstance(z, Zone) and z.key() not in sector_of:
                sector_of[z.key()] = b.add_sector(z.floor, z.ceil, z.floorh, z.ceilh, z.light, flags=z.flags)

    sidedefs = {}

    def sidedef(normal, above=0, below=0, flags=0, sid=0):
        k = (normal, above, below, flags, sid)
        if k not in sidedefs:
            sidedefs[k] = b.add_sidedef(normal, above=above, below=below, flags=flags, sid=sid)
        return sidedefs[k]

    problems, barrier_walls = [], 0

    def blocked(a, c):
        return (c.floorh - a.floorh > MAX_STEP or c.ceilh - a.floorh < HEADROOM
                or (c.ceil and c.ceilh - c.floorh < HEADROOM))

    def facing(view, other, block):
        if other.banner:
            return sidedef(other.banner, above=view.wall, below=view.wall, flags=0)
        if view.banner:
            return sidedef(0, flags=0)
        below = other.trim if other.floorh > view.floorh else 0
        above = view.wall if (other.ceilh < view.ceilh and other.ceil) else 0
        normal, sid = 0, 0
        flags = 0 if block else STEP_FLAGS
        for z, o in ((view, other), (other, view)):
            if z.door and o.name == z.door[1]:
                normal, sid, flags = DOOR_TEX, z.door[0], DOOR_FLAGS
        if view.window or other.window:
            normal, flags = WINDOW_TEX, WINDOW_FLAGS
        return sidedef(normal, above=above, below=below, flags=flags, sid=sid)

    def cell_polygon(x, y, z):
        c = CHAMFER

        def cut(n1, n2):
            if not (solid(*n1) and solid(*n2)):
                return False
            return z.chamfer or (solid_round(*n1) and solid_round(*n2))

        # A cell with solid on exactly two adjacent sides is cut along its FULL
        # diagonal.  On a 45-degree staircase every step is such a cell, so the
        # cuts line up into one straight wall.  Half-cell cuts left an 8-unit
        # square notch between each 45-degree piece: a sawtooth, very visible
        # in GZDoom Builder.  The removed half only touches the two solid sides,
        # so the room stays sealed.
        N, S, E, Wc = (x, y - 1), (x, y + 1), (x + 1, y), (x - 1, y)
        for (n1, n2, o1, o2, tri) in (
                (N, Wc, S, E, [(x + 1, y), (x + 1, y + 1), (x, y + 1)]),     # NW cut
                (N, E, S, Wc, [(x, y), (x + 1, y + 1), (x, y + 1)]),         # NE cut
                (S, E, N, Wc, [(x, y), (x + 1, y), (x, y + 1)]),             # SE cut
                (S, Wc, N, E, [(x, y), (x + 1, y), (x + 1, y + 1)])):        # SW cut
            if cut(n1, n2) and not solid(*o1) and not solid(*o2):
                return tri

        pts = []
        pts += [(x, y + c), (x + c, y)] if cut((x, y - 1), (x - 1, y)) else [(x, y)]
        pts += [(x + 1 - c, y), (x + 1, y + c)] if cut((x, y - 1), (x + 1, y)) else [(x + 1, y)]
        pts += [(x + 1, y + 1 - c), (x + 1 - c, y + 1)] if cut((x, y + 1), (x + 1, y)) else [(x + 1, y + 1)]
        pts += [(x + c, y + 1), (x, y + 1 - c)] if cut((x, y + 1), (x - 1, y)) else [(x, y + 1)]
        return pts

    open_area = 0.0
    for y in range(H):
        for x in range(W):
            z = zone(x, y)
            if z is None:
                continue
            if z.ceil and z.ceilh - z.floorh < HEADROOM:
                problems.append("%s: headroom %d" % (z.name, z.ceilh - z.floorh))
            mine = sector_of[z.key()]
            poly = cell_polygon(x, y, z)
            acc = sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                      for i in range(len(poly)))
            open_area += abs(acc) / 2 * (CELL * 16) ** 2
            # Nudge "inside" toward the polygon's own centroid, not the cell centre:
            # for a half-cell triangle the cell centre lies ON the diagonal, so the
            # facing test was a coin toss and flipped walls leaked (seal 1.22).
            pcx = sum(pt[0] for pt in poly) / len(poly)
            pcy = sum(pt[1] for pt in poly) / len(poly)
            for i in range(len(poly)):
                a, q = poly[i], poly[(i + 1) % len(poly)]
                inside = (((a[0] + q[0]) / 2 + (pcx - (a[0] + q[0]) / 2) * 0.35) * CELL,
                          ((a[1] + q[1]) / 2 + (pcy - (a[1] + q[1]) / 2) * 0.35) * CELL)
                # chamfer points are half-cells, so these are whole numbers -- but floats
                x0, y0, x1, y1 = (int(round(v * CELL)) for v in (a[0], a[1], q[0], q[1]))
                if abs(a[0] - q[0]) > 1e-9 and abs(a[1] - q[1]) > 1e-9:
                    # chamfer diagonal: faces the solid corner
                    n = g[y - 1][x] if a[1] < y + 0.5 and y > 0 else (g[y + 1][x] if y + 1 < H else None)
                    tex = n.tex if isinstance(n, Solid) and n.round else z.wall
                    b.add_wall_facing(x0, y0, x1, y1, inside, sidedef(tex), mine)
                    continue
                if abs(a[1] - q[1]) < 1e-9:
                    nb = (x, y - 1) if abs(a[1] - y) < 1e-9 else (x, y + 1)
                else:
                    nb = (x - 1, y) if abs(a[0] - x) < 1e-9 else (x + 1, y)
                o = zone(*nb)
                if o is None:
                    c = g[nb[1]][nb[0]] if 0 <= nb[0] < W and 0 <= nb[1] < H else None
                    tex = c.tex if isinstance(c, Solid) else z.wall
                    sd = sidedef(0, flags=WF_MAP_NEVER) if z.banner else sidedef(tex)
                    b.add_wall_facing(x0, y0, x1, y1, inside, sd, mine)
                    continue
                other = sector_of[o.key()]
                if (other == mine and not ((z.door or o.door) and z.name != o.name)) or (nb[1], nb[0]) < (y, x):
                    continue
                block = blocked(z, o) or blocked(o, z) or z.window or o.window
                if block:
                    if not (z.barrier or o.barrier):
                        problems.append("%s <-> %s: floor %d/%d ceiling %d/%d"
                                        % (z.name, o.name, z.floorh, o.floorh, z.ceilh, o.ceilh))
                    barrier_walls += 1
                b.add_wall_facing(x0, y0, x1, y1, inside, facing(z, o, block), mine,
                                  neg_sidedef=facing(o, z, block), neg_sector=other)

    if problems:
        raise ValueError("movement rule problems: " + "; ".join(sorted(set(problems))[:8]))

    _merge_collinear(b)
    shared, b.sidedefs = b.sidedefs, []

    def own_copy(ref):
        if not ref:
            return 0
        s = shared[ref - 1]
        return b.add_sidedef(s.type_normal, above=s.type_above, below=s.type_below, flags=s.flags, sid=s.id)

    b.walls = [(x0, y0, x1, y1, own_copy(sd), sec, own_copy(nsd), nsec)
               for (x0, y0, x1, y1, sd, sec, nsd, nsec) in b.walls]
    room = b.build()

    from align import align_room, continuity
    joins_before = continuity(room)
    unmatched = align_room(room)
    joins_after = continuity(room)
    if verbose:
        print("texture alignment: seamless joins %d/%d -> %d/%d, unmatched client wall sides %d"
              % (joins_before[1], joins_before[0], joins_after[1], joins_after[0], unmatched))

    leaf_area = 0.0
    for n in room.bsp.walk():
        if n.type == BSP_LEAF and n.sector:
            pts = n.points
            leaf_area += abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                                 for i in range(len(pts)))) / 2
    seal = leaf_area / open_area
    if abs(seal - 1.0) >= 1e-6:
        raise ValueError("room is not sealed: leaf/floor area = %f" % seal)
    return room, {"barrier_walls": barrier_walls, "seal": seal, "joins": joins_after, "unmatched": unmatched}


def emit(p, basename, title):
    """compile_plan, then write out/<basename>.roo (+ .txt) and check the file reads back identically."""
    W, H = p.w, p.h
    room, info = compile_plan(p)
    seal, barrier_walls = info["seal"], info["barrier_walls"]

    out = os.path.join(HERE, "out", basename + ".roo")
    room.save(out)
    again = Room.load(out)
    with open(out, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"

    diag = sum(1 for l in room.linedefs if l.x0 != l.x1 and l.y0 != l.y1)
    doors = sorted({(s.id, s.type_normal) for s in room.sidedefs if s.id})
    lines = ["%s -- %d x %d editor units (the plan's row 0 is at the top)" % (title, W * CELL, H * CELL),
             "%d sectors, %d walls (%d angled), %d impassable edges, door wall ids %s"
             % (len(room.sectors), len(room.linedefs), diag, barrier_walls, [d[0] for d in doors]), ""]
    for name, where, z in p.legend:
        lines.append("%-22s floor h %3d  ceiling %s  floor %5d  ceil %4d  walls %4d  light %3d%s  -- %s"
                     % (name, z.floorh, ("h %3d" % z.ceilh) if z.ceil else "sky  ", z.floor, z.ceil, z.wall,
                        z.light, "  flags 0x%x" % z.flags if z.flags else "", where))
    with open(os.path.join(HERE, "out", basename + ".txt"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print(again.summary())
    print("seal %.6f, movement problems 0" % seal)
    print("\n".join(lines[:2]))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
