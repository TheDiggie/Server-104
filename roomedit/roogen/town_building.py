"""
town_building.py -- the shared town-building generator.

A town is a Town: its palette plus which features its buildings use.  The
layout work is the same everywhere (split the footprint into rooms, one doorway
per split, a front door and wall niches, then furnish by room type); what makes
a Barloque building look like Barloque and a Ko'catan one like Ko'catan is the
Town.

Style values for each town are measured from that town's own interiors, and its
textures are checked by rendering them, not picked by number (4802-4807 turned
out to be heraldic banners, not windows).

Built on building2's cell engine, which checks blakserv's movement rules and
the seal and aligns textures; a failure raises so the app retries another seed.
"""
import random

from building2 import Plan, Zone, Solid, compile_plan, SF_FLICKER, CELL, HEADROOM
from generate import recentre, SizeError

CELLS_PER_ROOM = 650       # footprint cells per room
DOOR_WALL = 10             # cells: the door niche (4) plus 3 each side
PAD = 4                    # room outside the footprint for niches
WALL = 2                   # cells of wall between rooms
MIN_ROOM = 14
BIG_KINDS = ("great hall", "tavern", "court", "chapel")


class Town:
    """One town's look.  Heights are editor units."""

    def __init__(self, name, walls, floors, ceils, wall_trim, floor_trim, shelf, carpet, dais_floors,
                 door, banners=(), lights=(72,), base_floor=128, big_gaps=(176, 192), small_gaps=(112, 128, 144),
                 column_tex=None, bench_tex=None, beams=True, kinds=("library", "parlor", "storeroom", "study",
                                                                     "bedroom", "court", "chapel", "tavern")):
        self.name = name
        self.walls, self.floors, self.ceils = list(walls), list(floors), list(ceils)
        self.wall_trim = wall_trim          # panelling / riser face
        self.floor_trim = floor_trim        # table and counter tops
        self.shelf, self.carpet = shelf, carpet
        self.dais_floors = list(dais_floors)
        self.door, self.banners = door, list(banners)
        self.lights = list(lights)
        self.base_floor = base_floor
        self.big_gaps, self.small_gaps = list(big_gaps), list(small_gaps)
        self.column_tex = column_tex or wall_trim
        self.bench_tex = bench_tex or floor_trim
        self.beams = beams
        self.kinds = list(kinds)


def split_rooms(rnd, rect, target, min_room=MIN_ROOM):
    """Divide the footprint into rooms of VARIED size.

    Always splitting the largest room down the middle -- the obvious way -- ends
    with every room nearly the same size, which is not how Barloque's buildings
    look (a hall beside a nook).  So the room to split is drawn weighted by
    area (big rooms usually split, but not always) and the cut is often well
    off-centre."""
    rooms, splits = [rect], []
    while len(rooms) < target:
        candidates = [r for r in rooms
                      if max(r[2] - r[0] + 1, r[3] - r[1] + 1) >= 2 * min_room + WALL]
        if not candidates:
            break
        weights = [((r[2] - r[0] + 1) * (r[3] - r[1] + 1)) ** 2 for r in candidates]
        r = rnd.choices(candidates, weights)[0]
        x0, y0, x1, y1 = r
        w, h = x1 - x0 + 1, y1 - y0 + 1
        options = [v for v in (True, False) if (w if v else h) >= 2 * min_room + WALL]
        vertical = options[0] if len(options) == 1 else ((w >= h) if rnd.random() < 0.75 else (w < h))
        length = w if vertical else h
        lo, hi = min_room, length - min_room - WALL
        frac = rnd.choice([rnd.uniform(0.15, 0.35), rnd.uniform(0.35, 0.5),
                           rnd.uniform(0.5, 0.65), rnd.uniform(0.65, 0.85)])
        cut = max(lo, min(hi, int(round(length * frac))))
        if vertical:
            a, b = (x0, y0, x0 + cut - 1, y1), (x0 + cut + WALL, y0, x1, y1)
            wall = ("v", x0 + cut, x0 + cut + WALL - 1, y0, y1)
        else:
            a, b = (x0, y0, x1, y0 + cut - 1), (x0, y0 + cut + WALL, x1, y1)
            wall = ("h", y0 + cut, y0 + cut + WALL - 1, x0, x1)
        rooms.remove(r)
        rooms += [a, b]
        splits.append(wall)
    return rooms, splits


def generate(town, width, height, seed):
    rnd = random.Random(seed)
    max_fw, max_fh = width // CELL - 2 * PAD, height // CELL - 2 * PAD
    if max_fw < DOOR_WALL or max_fh < DOOR_WALL:
        need = (DOOR_WALL + 2 * PAD) * CELL
        raise SizeError("a %s building needs at least %d x %d (a %d-unit wall for the front door plus %d for the "
                        "niches on each side); you entered %d x %d"
                        % (town.name, need, need, DOOR_WALL * CELL, PAD * CELL, width, height))
    fw = max(DOOR_WALL, int(max_fw * rnd.uniform(0.85, 1.0)))
    fh = max(DOOR_WALL, int(max_fh * rnd.uniform(0.85, 1.0)))
    # per building: how densely it is divided, and how small its smallest room
    # may be -- some buildings are a few big rooms, others have nooks
    per_room = rnd.choice([450, 650, 650, 900])
    min_room = rnd.choice([8, 10, 14])
    target = int(max(1, round(fw * fh / per_room * rnd.uniform(0.8, 1.25))))
    p = Plan(fw + 2 * PAD, fh + 2 * PAD)
    X0, Y0, X1, Y1 = PAD, PAD, PAD + fw - 1, PAD + fh - 1
    rooms, splits = split_rooms(rnd, (X0, Y0, X1, Y1), target, min_room)
    light = rnd.choice(town.lights)
    occ = [[False] * p.w for _ in range(p.h)]
    features = []

    def mark(x0, y0, x1, y1):
        for y in range(max(0, y0), min(p.h - 1, y1) + 1):
            for x in range(max(0, x0), min(p.w - 1, x1) + 1):
                occ[y][x] = True

    def floor_is(x, y, z):
        return 0 <= x < p.w and 0 <= y < p.h and p.g[y][x] is z

    def clear(cells, z):
        return all(floor_is(x, y, z) and not occ[y][x] for x, y in cells)

    def fits(z, rise):
        """Anything standing `rise` above the floor still needs 48 of headroom
        under the room's ceiling.  Ko'catan's rooms are only 80-96 tall, so
        counters and crates (+48) do not fit there and are simply skipped --
        without this the whole building is rejected."""
        return z.ceilh - (z.floorh + rise) >= HEADROOM

    # ---- rooms
    order = sorted(rooms, key=lambda r: -(r[2] - r[0] + 1) * (r[3] - r[1] + 1))
    kinds = [rnd.choice(["great hall", "tavern"])] + [rnd.choice(town.kinds) for _ in order[1:]]
    info = {}
    two_storey = set()
    for i, (r, kind) in enumerate(zip(order, kinds)):
        rw, rh = r[2] - r[0] + 1, r[3] - r[1] + 1
        if min(rw, rh) < 10:
            kind = "closet"                          # too small for furniture
        elif kind in BIG_KINDS and min(rw, rh) < 16:
            kind = rnd.choice(["parlor", "study", "storeroom", "bedroom"])
        floorh = town.base_floor if kind in BIG_KINDS or rnd.random() < 0.7 else town.base_floor + 16
        if kind in BIG_KINDS and min(rw, rh) >= 22 and rnd.random() < 0.6:
            # a room tall enough to carry an upper gallery
            gap = rnd.choice([288, 320, 352])
            two_storey.add(r)
        elif kind in BIG_KINDS:
            gap = rnd.choice(town.big_gaps)
        elif kind in ("library", "study"):
            gap = 192           # wall shelves: 128 of shelf + 64 headroom
        else:
            gap = rnd.choice(town.small_gaps)
        z = Zone("%s %d" % (kind, i + 1), floorh, floorh + gap, rnd.choice(town.floors), rnd.choice(town.ceils),
                 rnd.choice(town.walls), light)
        p.rect(*r, z)
        info[r] = (kind, z)

    # ---- one doorway per split, so every room is reachable
    doorways = []
    for kind, c0, c1, s0, s1 in splits:
        if kind == "v":
            left = [r for r in rooms if r[2] == c0 - 1 and r[1] <= s1 and r[3] >= s0]
            right = [r for r in rooms if r[0] == c1 + 1 and r[1] <= s1 and r[3] >= s0]
        else:
            left = [r for r in rooms if r[3] == c0 - 1 and r[0] <= s1 and r[2] >= s0]
            right = [r for r in rooms if r[1] == c1 + 1 and r[0] <= s1 and r[2] >= s0]
        pairs = []
        for ra in left:
            for rb in right:
                if kind == "v":
                    lo, hi = max(ra[1], rb[1], s0), min(ra[3], rb[3], s1)
                else:
                    lo, hi = max(ra[0], rb[0], s0), min(ra[2], rb[2], s1)
                if hi - lo + 1 >= 8:
                    pairs.append((ra, rb, lo, hi))
        if not pairs:
            raise ValueError("no room for a doorway")
        ra, rb, lo, hi = rnd.choice(pairs)
        dw = min(rnd.choice([4, 5, 6]), hi - lo + 1 - 4)
        pos = rnd.randint(lo + 2, hi - 1 - dw)
        za, zb = info[ra][1], info[rb][1]
        dz = Zone("doorway", (za.floorh + zb.floorh) // 2, min(za.ceilh, zb.ceilh) - 16, za.floor, za.ceil,
                  za.wall, light)
        rect = (c0, pos, c1, pos + dw - 1) if kind == "v" else (pos, c0, pos + dw - 1, c1)
        p.rect(*rect, dz)
        mark(rect[0] - 4, rect[1] - 4, rect[2] + 4, rect[3] + 4)
        doorways.append((kind, rect, ra, rb))

    # ---- room shapes
    def carve(cells):
        for x, y in cells:
            p.g[y][x] = None

    def cut_corners(r, z):
        x0, y0, x1, y1 = r
        kmax = min(7, (x1 - x0 + 1) // 4, (y1 - y0 + 1) // 4)
        if kmax < 3:
            return 0
        n = 0
        for cx, cy, sx, sy in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            if rnd.random() > 0.6:
                continue
            k = rnd.randint(3, kmax)
            cells = [(cx + sx * i, cy + sy * j) for i in range(k) for j in range(k - i)]
            if clear(cells, z):
                carve(cells)
                z.chamfer = True
                n += 1
        return n

    def notch(r, z):
        x0, y0, x1, y1 = r
        rw, rh = x1 - x0 + 1, y1 - y0 + 1
        nw, nh = max(6, int(rw * rnd.uniform(0.3, 0.45))), max(6, int(rh * rnd.uniform(0.3, 0.45)))
        corner = rnd.randrange(4)
        nx0 = x0 if corner in (0, 2) else x1 - nw + 1
        ny0 = y0 if corner in (0, 1) else y1 - nh + 1
        cells = [(x, y) for x in range(nx0, nx0 + nw) for y in range(ny0, ny0 + nh)]
        ring = [(x, y) for x in range(nx0 - 2, nx0 + nw + 2) for y in range(ny0 - 2, ny0 + nh + 2)
                if 0 <= x < p.w and 0 <= y < p.h]
        if all(floor_is(x, y, z) for x, y in cells) and not any(occ[y][x] for x, y in ring):
            carve(cells)
            return True
        return False

    def make_round(r, z):
        x0, y0, x1, y1 = r
        cx, cy = (x0 + x1 + 1) / 2.0, (y0 + y1 + 1) / 2.0
        rad = min(x1 - x0 + 1, y1 - y0 + 1) / 2.0
        carve([(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
               if not (max(abs(x + 0.5 - cx), abs(y + 0.5 - cy)) <= rad
                       and abs(x + 0.5 - cx) + abs(y + 0.5 - cy) <= rad * 1.35)])
        z.chamfer = True
        for kind, (dx0, dy0, dx1, dy1), ra, rb in doorways:
            if r not in (ra, rb):
                continue
            if kind == "v":
                xs = range(x0, int(cx)) if dx1 < x0 else range(x1, int(cx), -1)
                for x in xs:
                    done = all(p.g[y][x] is z for y in range(dy0, dy1 + 1))
                    for y in range(dy0, dy1 + 1):
                        p.g[y][x] = z
                    if done:
                        break
            else:
                ys = range(y0, int(cy)) if dy1 < y0 else range(y1, int(cy), -1)
                for y in ys:
                    done = all(p.g[y][x] is z for x in range(dx0, dx1 + 1))
                    for x in range(dx0, dx1 + 1):
                        p.g[y][x] = z
                    if done:
                        break

    for r in order:
        kind, z = info[r]
        rw, rh = r[2] - r[0] + 1, r[3] - r[1] + 1
        roll = rnd.random()
        if roll < 0.15 and min(rw, rh) >= 18 and max(rw, rh) <= 1.4 * min(rw, rh) \
                and kind in ("great hall", "chapel", "parlor", "bedroom"):
            make_round(r, z)
            features.append("round %s" % kind.split()[-1])
        else:
            if roll < 0.4 and rw >= 22 and rh >= 22 and notch(r, z):
                features.append("L-shaped room")
            if rnd.random() < 0.5 and cut_corners(r, z):
                features.append("cut corners")

    # ---- outside walls
    def outer_sides(r):
        x0, y0, x1, y1 = r
        out = []
        if y0 == Y0:
            out.append(("n", x0, x1))
        if y1 == Y1:
            out.append(("s", x0, x1))
        if x0 == X0:
            out.append(("w", y0, y1))
        if x1 == X1:
            out.append(("e", y0, y1))
        return out

    def niche_rect(side, a, width_):
        if side == "n":
            return (a, Y0 - 2, a + width_ - 1, Y0 - 1)
        if side == "s":
            return (a, Y1 + 1, a + width_ - 1, Y1 + 2)
        if side == "w":
            return (X0 - 2, a, X0 - 1, a + width_ - 1)
        return (X1 + 1, a, X1 + 2, a + width_ - 1)

    def inside_of(side, rect):
        x0, y0, x1, y1 = rect
        if side == "n":
            return [(x, Y0) for x in range(x0, x1 + 1)]
        if side == "s":
            return [(x, Y1) for x in range(x0, x1 + 1)]
        if side == "w":
            return [(X0, y) for y in range(y0, y1 + 1)]
        return [(X1, y) for y in range(y0, y1 + 1)]

    def front_of(side, rect, depth):
        x0, y0, x1, y1 = rect
        if side == "n":
            return (x0 - 1, Y0, x1 + 1, Y0 + depth - 1)
        if side == "s":
            return (x0 - 1, Y1 - depth + 1, x1 + 1, Y1)
        if side == "w":
            return (X0, y0 - 1, X0 + depth - 1, y1 + 1)
        return (X1 - depth + 1, y0 - 1, X1, y1 + 1)

    def niche_free(rect):
        x0, y0, x1, y1 = rect
        return all(p.g[y][x] is None for y in range(max(0, y0 - 2), min(p.h, y1 + 3))
                   for x in range(max(0, x0 - 2), min(p.w, x1 + 3))
                   if not (X0 <= x <= X1 and Y0 <= y <= Y1))

    def side_frame(r, side):
        """(u along the wall, v away from it) -> cell, wall length, room depth"""
        x0, y0, x1, y1 = r
        if side == "n":
            return (lambda u, v: (x0 + u, y0 + v)), x1 - x0 + 1, y1 - y0 + 1
        if side == "s":
            return (lambda u, v: (x0 + u, y1 - v)), x1 - x0 + 1, y1 - y0 + 1
        if side == "w":
            return (lambda u, v: (x0 + v, y0 + u)), y1 - y0 + 1, x1 - x0 + 1
        return (lambda u, v: (x1 - v, y0 + u)), y1 - y0 + 1, x1 - x0 + 1

    # front door, built like a painting
    candidates = [(r, s) for r in order for s in outer_sides(r) if s[2] - s[1] + 1 >= DOOR_WALL]
    rnd.shuffle(candidates)
    candidates.sort(key=lambda c: info[c[0]][0] not in ("great hall", "tavern"))
    placed_door = False
    for r, (side, a0, a1) in candidates:
        z = info[r][1]
        for _ in range(12):
            pos = rnd.randint(a0 + 3, a1 - 6)
            rect = niche_rect(side, pos, 4)
            if niche_free(rect) and all(floor_is(x, y, z) and not occ[y][x] for x, y in inside_of(side, rect)):
                p.rect(*rect, Zone("front door", z.floorh, z.floorh + 96, 0, 0, z.wall, light,
                                   barrier=True, banner=town.door))
                mark(*front_of(side, rect, 6))
                placed_door = True
                break
        if placed_door:
            break
    if not placed_door:
        raise ValueError("no outside wall for the front door")

    # ---- furniture helpers
    def place(r, z, w, h, zone, ring=3, tries=40):
        if zone.ceilh - zone.floorh < HEADROOM:      # too low a room for this furniture
            return False
        x0, y0, x1, y1 = r
        for _ in range(tries):
            rw, rh = (w, h) if rnd.random() < 0.5 else (h, w)
            if x1 - ring - rw + 1 < x0 + ring or y1 - ring - rh + 1 < y0 + ring:
                return False
            x = rnd.randint(x0 + ring, x1 - ring - rw + 1)
            y = rnd.randint(y0 + ring, y1 - ring - rh + 1)
            foot = [(xx, yy) for yy in range(y, y + rh) for xx in range(x, x + rw)]
            around = [(xx, yy) for yy in range(y - ring, y + rh + ring) for xx in range(x - ring, x + rw + ring)
                      if 0 <= xx < p.w and 0 <= yy < p.h]
            if all(floor_is(xx, yy, z) for xx, yy in foot) and not any(occ[yy][xx] for xx, yy in around):
                p.rect(x, y, x + rw - 1, y + rh - 1, zone)
                mark(x - ring, y - ring, x + rw + ring - 1, y + rh + ring - 1)
                return True
        return False

    def wall_shelves(r, z, sides):
        if not fits(z, 128):
            return
        shelf = Zone("shelves", z.floorh + 128, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                     trim=town.shelf, barrier=True)
        for side in sides:
            f, L, _D = side_frame(r, side)
            run = []
            for u in list(range(L)) + [None]:
                cell = f(u, 0) if u is not None else None
                if cell is not None and floor_is(cell[0], cell[1], z) and not occ[cell[1]][cell[0]]:
                    run.append(cell)
                    continue
                if len(run) >= 4:
                    for x, y in run:
                        p.g[y][x] = shelf
                    xs, ys = [c[0] for c in run], [c[1] for c in run]
                    mark(min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
                run = []

    def dais(r, z):
        if not fits(z, 32):
            return None
        for side in rnd.sample("nswe", 4):
            f, L, D = side_frame(r, side)
            depth = rnd.randint(4, 6)
            if D < depth + 8:
                continue
            cells = [f(u, v) for u in range(L) for v in range(depth + 2)]
            if not clear(cells, z):
                continue
            top = Zone("dais", z.floorh + 32, z.ceilh, rnd.choice(town.dais_floors), z.ceil, z.wall, light,
                       trim=rnd.choice([town.wall_trim, town.floor_trim]))
            step = Zone("dais step", z.floorh + 16, z.ceilh, top.floor, z.ceil, z.wall, light, trim=top.trim)
            for u in range(L):
                for v in range(depth):
                    x, y = f(u, v)
                    p.g[y][x] = top if v < depth - 2 else step
            for x, y in cells:
                occ[y][x] = True
            features.append("dais")
            return side
        return None

    def columns(r, z, spacing=7):
        x0, y0, x1, y1 = r
        n = 0
        for fy in (1 / 3.0, 2 / 3.0):
            cy = int(y0 + (y1 - y0 + 1) * fy)
            for cx in range(x0 + 4, x1 - 3, spacing):
                cells = [(x, y) for x in range(cx - 2, cx + 3) for y in range(cy - 2, cy + 3)]
                if clear(cells, z):
                    p.octagon(cx + 0.5, cy + 0.5, 1.4, Solid(town.column_tex, round_=True))
                    mark(cx - 3, cy - 3, cx + 3, cy + 3)
                    n += 1
        if n:
            features.append("columns")
        return n

    def stairs_up(r, z):
        if z.ceilh - z.floorh < 176:
            return False
        sides = outer_sides(r)
        for side, a0, a1 in rnd.sample(sides, len(sides)):
            f, L, D = side_frame(r, side)
            if L < 20 or D < 10:
                continue
            for _ in range(8):
                a = rnd.randint(3, L - 17)
                run = [f(a + u, v) for u in range(-1, 14) for v in range(7)]
                if not clear(run, z):
                    continue
                lx, ly = f(a + 8, 0)
                rect = niche_rect(side, lx if side in "ns" else ly, 4)
                if not niche_free(rect):
                    continue
                for i in range(4):          # 16-unit rises, 32 deep (barinn)
                    step = Zone("stairs", z.floorh + 16 * (i + 1), z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                                trim=town.wall_trim)
                    for u in (2 * i, 2 * i + 1):
                        for v in range(4):
                            x, y = f(a + u, v)
                            p.g[y][x] = step
                landing = Zone("landing", z.floorh + 64, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                               trim=town.wall_trim)
                for u in range(8, 12):
                    for v in range(4):
                        x, y = f(a + u, v)
                        p.g[y][x] = landing
                rail = Solid(town.wall_trim)
                for u in range(2, 13):
                    x, y = f(a + u, 4)
                    p.g[y][x] = rail
                for v in range(4):
                    x, y = f(a + 12, v)
                    p.g[y][x] = rail
                p.rect(*rect, Zone("upstairs door", z.floorh + 64, z.floorh + 160, 0, 0, z.wall, light,
                                   barrier=True, banner=town.door))
                for x, y in run:
                    occ[y][x] = True
                features.append("stairs up")
                return True
        return False

    def upper_floor(r, z):
        """An upper floor is a raised gallery over part of a tall room: the
        engine cannot stack a room on a room (one floor and one ceiling per
        area).  Real upper rooms climb 100-150 above the ground floor in 10-15
        unit steps (kocinn, koctav, koctower, jasstore), so the gallery sits 160
        up a ten-step stair, and its open edge is a drop you cannot climb."""
        rise, steps = 16, 10
        top = z.floorh + rise * steps
        if z.ceilh - top < HEADROOM:
            return False
        for side in rnd.sample("nswe", 4):
            f, L, D = side_frame(r, side)
            dg = rnd.randint(6, 10)
            if L < 12 or D < dg + steps + 3:
                continue
            band = [f(u, v) for u in range(L) for v in range(dg)]
            stair = [f(u, dg + i) for u in range(3) for i in range(steps)]
            if not clear(band + stair, z):
                continue
            gallery = Zone("upper floor", top, z.ceilh, rnd.choice(town.floors), z.ceil, z.wall, light,
                           trim=town.wall_trim, barrier=True)
            for x, y in band:
                p.g[y][x] = gallery
            for i in range(steps):                    # the step beside the gallery is highest
                st = Zone("upper stair", top - rise * (i + 1), z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                          trim=town.wall_trim, barrier=True)
                for u in range(3):
                    x, y = f(u, dg + i)
                    p.g[y][x] = st
            for x, y in stair:
                occ[y][x] = True
            xs, ys = [c[0] for c in band], [c[1] for c in band]
            grect = (min(xs) + 1, min(ys) + 1, max(xs) - 1, max(ys) - 1)
            bed = Zone("bed", top + 32, z.ceilh, town.carpet, z.ceil, z.wall, light,
                       trim=town.floor_trim, barrier=True)
            table = Zone("table", top + 40, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                         trim=town.wall_trim, barrier=True)
            for _ in range(rnd.randint(1, 2)):
                place(grect, gallery, 4, 6, bed)
            place(grect, gallery, 3, 4, table)
            features.append("upper floor")
            return True
        return False

    def counter(r, z):
        if not fits(z, 48):
            return False
        for side in rnd.sample("nswe", 4):
            f, L, D = side_frame(r, side)
            if L < 14 or D < 14:
                continue
            length = int(L * rnd.uniform(0.45, 0.65))
            a = rnd.randint(3, L - length - 3)
            cells = [f(a + u, v) for u in range(-2, length + 2) for v in range(8)]
            if not clear(cells, z):
                continue
            bar = Zone("counter", z.floorh + 48, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                       trim=town.wall_trim, barrier=True)
            for u in range(length):
                for v in (4, 5):
                    x, y = f(a + u, v)
                    p.g[y][x] = bar
            for x, y in cells:
                occ[y][x] = True
            features.append("counter")
            return True
        return False

    def benches(r, z, side):
        if not fits(z, 32):
            return
        f, L, D = side_frame(r, side or "n")
        plank = Zone("benches", z.floorh + 32, z.ceilh, town.bench_tex, z.ceil, z.wall, light,
                     trim=town.bench_tex, barrier=True)
        mid, n = L // 2, 0
        for v in range(D // 2, D - 4, 5):
            for u0, u1 in ((3, mid - 2), (mid + 2, L - 3)):
                if u1 - u0 < 4:
                    continue
                cells = [f(u, vv) for u in range(u0 - 1, u1 + 1) for vv in range(v - 1, v + 3)]
                if clear(cells, z):
                    for u in range(u0, u1):
                        for vv in (v, v + 1):
                            x, y = f(u, vv)
                            p.g[y][x] = plank
                    for x, y in cells:
                        occ[y][x] = True
                    n += 1
        if n:
            features.append("benches")

    def paint_where(z, cells, zone):
        for x, y in cells:
            if floor_is(x, y, z):
                p.g[y][x] = zone

    # ---- upper galleries first (they claim a whole end of a tall room)
    for r in order:
        if r in two_storey:
            upper_floor(r, info[r][1])

    # ---- stairs up to an upper-floor door, where a big room has the headroom
    for r in order:
        kind, z = info[r]
        if kind in ("great hall", "tavern") and r not in two_storey and rnd.random() < 0.6:
            stairs_up(r, z)

    # ---- wall niches (towns without banners get none)
    if town.banners:
        for r in order:
            z = info[r][1]
            for side, a0, a1 in outer_sides(r):
                a = a0 + 3
                while a + 6 <= a1 - 3:
                    rect = niche_rect(side, a, 6)
                    if rnd.random() < 0.55 and niche_free(rect) and \
                            all(floor_is(x, y, z) and not occ[y][x] for x, y in inside_of(side, rect)):
                        p.rect(*rect, Zone("banner", z.floorh + 32, z.floorh + 80, 0, 0, z.wall, light,
                                           barrier=True, banner=rnd.choice(town.banners)))
                        mark(*front_of(side, rect, 3))
                        a += 12
                    else:
                        a += 4

    # ---- furnishing by room type
    for r in order:
        kind, z = info[r]
        x0, y0, x1, y1 = r
        area = (x1 - x0 + 1) * (y1 - y0 + 1)
        table = Zone("table", z.floorh + 40, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                     trim=town.wall_trim, barrier=True)
        if kind in ("great hall", "tavern"):
            if kind == "tavern":
                counter(r, z)
            elif rnd.random() < 0.5:
                dais(r, z)
            if kind == "great hall" and min(x1 - x0, y1 - y0) >= 22:
                columns(r, z)
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            if clear([(x, y) for y in range(cy - 1, cy + 3) for x in range(cx - 1, cx + 3)], z):
                p.rect(cx, cy, cx + 1, cy + 1, Zone("candle light", z.floorh, z.ceilh, z.floor, z.ceil, z.wall,
                                                    min(127, light + 40), flags=SF_FLICKER))
                mark(cx - 2, cy - 2, cx + 3, cy + 3)
            for _ in range(max(1, area // 260)):
                place(r, z, *((3, 4) if kind == "tavern" else (4, 6)), table)
        elif kind == "court":
            side = dais(r, z)
            benches(r, z, side)
            if rnd.random() < 0.5:
                columns(r, z, spacing=9)
        elif kind == "chapel":
            side = dais(r, z) or "n"
            f, L, D = side_frame(r, side)
            mid = L // 2
            paint_where(z, [f(u, v) for v in range(D) for u in range(mid - 2, mid + 2)],
                        Zone("carpet aisle", z.floorh, z.ceilh, town.carpet, z.ceil, z.wall, light))
            for v in range(8, D - 4, 7):
                for u in (mid - 6, mid + 5):
                    cx, cy = f(u, v)
                    cells = [(x, y) for x in range(cx - 2, cx + 3) for y in range(cy - 2, cy + 3)]
                    if clear(cells, z):
                        p.octagon(cx + 0.5, cy + 0.5, 1.4, Solid(town.column_tex, round_=True))
                        mark(cx - 3, cy - 3, cx + 3, cy + 3)
        elif kind == "library":
            wall_shelves(r, z, ["n", "s", "w", "e"])
            place(r, z, 3, 5, table)
        elif kind == "parlor":
            if x1 - x0 >= 14 and y1 - y0 >= 14:
                inner = [(x, y) for y in range(y0 + 5, y1 - 4) for x in range(x0 + 5, x1 - 4)]
                if rnd.random() < 0.5 and clear(inner, z):
                    paint_where(z, inner, Zone("sunken rug", z.floorh - 16, z.ceilh, town.carpet, z.ceil, z.wall,
                                               light, trim=town.wall_trim))
                    features.append("sunken rug")
                else:
                    cx, cy = (x0 + x1 + 1) / 2.0, (y0 + y1 + 1) / 2.0
                    rad = min(x1 - x0, y1 - y0) / 2.0 - 4
                    paint_where(z, [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)
                                    if max(abs(x + 0.5 - cx), abs(y + 0.5 - cy)) <= rad
                                    and abs(x + 0.5 - cx) + abs(y + 0.5 - cy) <= rad * 1.35],
                                Zone("rug", z.floorh, z.ceilh, town.carpet, z.ceil, z.wall, light))
            place(r, z, 4, 4, table)
        elif kind in ("storeroom", "closet"):
            crate = Zone("crates", z.floorh + 48, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                         trim=town.wall_trim, barrier=True)
            for _ in range(rnd.randint(1, 3) if kind == "closet" else rnd.randint(3, 7)):
                place(r, z, 2 if kind == "closet" else 3, 3, crate, ring=2)
        elif kind == "bedroom":
            bed = Zone("bed", z.floorh + 32, z.ceilh, town.carpet, z.ceil, z.wall, light,
                       trim=town.floor_trim, barrier=True)
            chest = Zone("chest", z.floorh + 32, z.ceilh, town.floor_trim, z.ceil, z.wall, light,
                         trim=town.wall_trim, barrier=True)
            for _ in range(rnd.randint(1, 3)):
                place(r, z, 4, 6, bed)
            place(r, z, 2, 3, chest, ring=2)
        else:                                          # study
            place(r, z, 3, 5, table)
            wall_shelves(r, z, [rnd.choice(["n", "s", "w", "e"])])
        if town.beams and kind in ("great hall", "tavern") and y1 - y0 + 1 >= 18:
            beam = Zone("ceiling beam", z.floorh, z.ceilh - 16, z.floor, town.floor_trim, z.wall, light)
            for by in range(y0 + 6, y1 - 5, 8):
                for yy in (by, by + 1):
                    for xx in range(x0, x1 + 1):
                        if p.g[yy][xx] is z:
                            p.g[yy][xx] = beam

    room, _cinfo = compile_plan(p, verbose=False)
    recentre(room, width, height)
    extras = sorted(set(features))
    return room, "%d rooms (%s), %d walls%s" % (
        len(rooms), ", ".join(sorted(set(k for k, _z in info.values()))), len(room.linedefs),
        "; " + ", ".join(extras) if extras else "")
