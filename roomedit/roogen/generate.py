#!/usr/bin/env python3
"""
generate.py -- build Meridian 59 .roo rooms from scratch.

The room editor normally does this from hand-drawn geometry.  Here the geometry
is generated, and everything the client needs is computed:

  * the roomedit section (linedefs / sidedefs / sectors) -- straightforward
  * the CLIENT section: a BSP tree plus the wall list per split plane.  This is
    the part you cannot hand-write, and it is why a .roo is not just a WAD.

The server section is deliberately absent: SaveServerInfo is commented out in
save.cpp ("This is currently unused") and no room in the game has one, so
server_pos simply points at end-of-file.

Conventions, all verified against the shipped rooms rather than assumed:
  * sidedef references are 1-BASED, 0 means "no sidedef"
  * sector references in linedefs are 0-BASED, 65535 means "no sector"
  * in client walls and BSP leaves a sector is stored as index+1, 0 = none
  * client coords: x' = (x - left) * 16,  y' = (top - y) * 16   -- Y IS FLIPPED
  * width/height come from the TWO THINGS, which mark opposite corners of the
    room rectangle (GetRoomSubRect), not from the geometry extent
  * a wall's `length` is in EDITOR units, not client units
  * BSP nodes are numbered 1-based in depth-first (node, pos, neg) order
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bsp
from roofile import (Room, Sector, FileSideDef, LineDef, BSPNode, ClientWall,
                     BSP_INTERNAL, BSP_LEAF)

BLAK_FACTOR = 16
NO_SECTOR = 65535

# Wall texture repeat, in editor units.  Derived from a1.roo, whose offsets are
# almost entirely in 0..64.
TEXTURE_REPEAT = 64


def _reduce(dx, dy):
    """Shrink the direction vector the way bspmake's reduce() does, so the
    plane coefficients come out as the same small integers the editor writes."""
    g = math.gcd(int(abs(dx)), int(abs(dy)))
    return (dx / g, dy / g) if g else (dx, dy)


def plane_from_points(x0, y0, x1, y1):
    """a,b,c for the line through the two points, matching
    BSPGetLineEquationFromPoints: normal is the direction rotated 90 degrees."""
    dx, dy = _reduce(x1 - x0, y1 - y0)
    a = -dy
    b = dx
    c = -(a * x0 + b * y0)
    return a, b, c


def _set_texture_offsets(walls):
    """Give each wall a texture x-offset that continues the run it belongs to.

    With every offset left at 0 each wall restarts its texture, so a treeline or
    a rock face visibly resets at every seam -- walls look unaligned even when the
    geometry is perfect.  73% of a1.roo's walls carry an offset, and the values
    stay small, which means they accumulate along a RUN modulo the texture's
    repeat rather than being projected from the world origin (that gives
    five-figure numbers).  a1's distinct offsets are almost entirely 0..64, so the
    repeat is 64 EDITOR units -- measured, not guessed.  (Its apparent mean of 193
    is an artefact: one wall has offset -3, stored in a u16 as 65533.)
    """
    by_start = {}
    for w in walls:
        by_start.setdefault((round(w.x0, 3), round(w.y0, 3)), []).append(w)

    placed = set()
    for w in walls:
        if id(w) in placed:
            continue
        # walk forward from here for as long as walls join end-to-start
        run, cur, guard = [], w, 0
        while cur is not None and id(cur) not in placed and guard < 100000:
            guard += 1
            placed.add(id(cur))
            run.append(cur)
            nxt = None
            for cand in by_start.get((round(cur.x1, 3), round(cur.y1, 3)), ()):
                if id(cand) not in placed:
                    nxt = cand
                    break
            cur = nxt
        acc = 0.0
        for seg in run:
            seg.pos_xoff = seg.neg_xoff = int(round(acc)) % TEXTURE_REPEAT
            acc += seg.length            # length is already in editor units


class RoomBuilder:
    """Accumulates walls and sectors, then emits a Room.

    Coordinates given to add_wall are EDITOR units; the client-side conversion
    happens in build().
    """

    def __init__(self, things_rect, room_id=0):
        # things_rect = (left, bottom, right, top) in editor units
        self.left, self.bottom, self.right, self.top = things_rect
        self.room_id = room_id
        self.sectors = []
        self.sidedefs = []
        self.walls = []          # (x0, y0, x1, y1, sidedef_1based, sector_0based)

    # -- content ---------------------------------------------------------
    def add_sector(self, floor_type, ceiling_type, floorh, ceilh, light=50,
                   flags=0, animate_speed=0, xoffset=0, yoffset=0, user_id=0):
        s = Sector()
        s.user_id = user_id
        s.floor_type = floor_type
        s.ceiling_type = ceiling_type
        s.xoffset = xoffset
        s.yoffset = yoffset
        s.floorh = floorh
        s.ceilh = ceilh
        s.light = light
        s.blak_flags = flags
        s.animate_speed = animate_speed
        s.floor_slope = s.ceiling_slope = None
        self.sectors.append(s)
        return len(self.sectors) - 1          # 0-based

    def add_sidedef(self, normal, above=0, below=0, flags=0, animate_speed=0,
                    sid=0):
        d = FileSideDef()
        d.id = sid
        d.type_normal = normal
        d.type_above = above
        d.type_below = below
        d.flags = flags
        d.animate_speed = animate_speed
        self.sidedefs.append(d)
        return len(self.sidedefs)             # 1-based on purpose

    def add_wall(self, x0, y0, x1, y1, sidedef, sector,
                 neg_sidedef=0, neg_sector=-1):
        """A wall with a sector on the positive side and, optionally, one on the
        negative side too.  Two-sided walls are what make a cave a cave: the
        boundary between two sectors at different floor heights."""
        self.walls.append((x0, y0, x1, y1, sidedef, sector,
                           neg_sidedef, neg_sector))

    def add_wall_facing(self, x0, y0, x1, y1, inside, sidedef, sector,
                        neg_sidedef=0, neg_sector=-1):
        """Same, but flip the wall if needed so `inside` (an editor-space point
        that must end up on the POSITIVE side) really does.  Reasoning about
        winding by hand is a good way to build rooms that are inside out --
        especially as cy() flips Y, so editor-space intuition is backwards."""
        a, b, c = plane_from_points(self.cx(x0), self.cy(y0),
                                    self.cx(x1), self.cy(y1))
        if a * self.cx(inside[0]) + b * self.cy(inside[1]) + c < 0:
            # Reverse the wall so `inside` lands on the positive side.  Do NOT
            # swap sidedef/sector with their neg_ counterparts: the caller names
            # them for the side `inside` is on, and that side is the positive one
            # either way.  Swapping put the rock texture and the sector on the
            # OUTSIDE of every flipped wall -- which drew nothing and let players
            # walk straight out of the room.
            x0, y0, x1, y1 = x1, y1, x0, y0
        self.add_wall(x0, y0, x1, y1, sidedef, sector, neg_sidedef, neg_sector)

    def add_polygon(self, points, sidedef, sector):
        """Walls around an arbitrary closed loop.  The interior has to end up on
        the POSITIVE side of every wall, which means a specific winding; work it
        out from the signed area rather than making the caller get it right."""
        pts = list(points)
        area = 0.0
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            area += x0 * y1 - x1 * y0
        # cy() flips Y, so the sign that survives into client space is inverted
        if area > 0:
            pts.reverse()
        for i in range(len(pts)):
            x0, y0 = pts[i]
            x1, y1 = pts[(i + 1) % len(pts)]
            self.add_wall(x0, y0, x1, y1, sidedef, sector)

    def add_rect(self, x0, y0, x1, y1, sidedef, sector):
        """Four walls around a rectangle, wound so the interior ends up on the
        positive side of every plane (which is what makes the simple BSP chain
        below valid)."""
        self.add_wall(x0, y0, x0, y1, sidedef, sector)   # left
        self.add_wall(x1, y0, x0, y0, sidedef, sector)   # bottom
        self.add_wall(x0, y1, x1, y1, sidedef, sector)   # top
        self.add_wall(x1, y1, x1, y0, sidedef, sector)   # right

    # -- coordinate transform -------------------------------------------
    def cx(self, x):
        return (x - self.left) * BLAK_FACTOR

    def cy(self, y):
        return (self.top - y) * BLAK_FACTOR

    # -- emit ------------------------------------------------------------
    def build(self):
        room = Room()
        room.room_id = self.room_id
        room.width = (self.right - self.left) * BLAK_FACTOR
        room.height = (self.top - self.bottom) * BLAK_FACTOR
        room.sectors = self.sectors
        room.sidedefs = self.sidedefs
        room.things = [{"xpos": self.left, "ypos": self.top},
                       {"xpos": self.right, "ypos": self.bottom}]

        # -- roomedit walls
        for (x0, y0, x1, y1, sd, sec, nsd, nsec) in self.walls:
            l = LineDef()
            l.sidedef1, l.sidedef2 = sd, nsd
            l.xoff1 = l.xoff2 = l.yoff1 = l.yoff2 = 0
            l.sector1 = sec if sec >= 0 else NO_SECTOR
            l.sector2 = nsec if nsec >= 0 else NO_SECTOR
            l.x0, l.y0, l.x1, l.y1 = x0, y0, x1, y1
            room.linedefs.append(l)

        # -- the BSP tree and the client walls, built for arbitrary geometry
        bwalls = [bsp.Wall(self.cx(x0), self.cy(y0), self.cx(x1), self.cy(y1),
                           pos_sector=sec, neg_sector=nsec, pos_sidedef=sd,
                           neg_sidedef=nsd, linedef=i)
                  for i, (x0, y0, x1, y1, sd, sec, nsd, nsec)
                  in enumerate(self.walls)]

        # The BSP root region must cover all the GEOMETRY, which is not the same
        # as the things box: a room with an edge exit deliberately has floor
        # extending past that box (the player crosses it to trigger the exit), and
        # every shipped orc cave is built that way.  Using the things box here
        # clipped those corridors away and left the room unsealed.
        gx0 = min(min(w.x0, w.x1) for w in bwalls) - 64
        gx1 = max(max(w.x0, w.x1) for w in bwalls) + 64
        gy0 = min(min(w.y0, w.y1) for w in bwalls) - 64
        gy1 = max(max(w.y0, w.y1) for w in bwalls) + 64
        tree = bsp.build_tree(bwalls, gx0, gy0, gx1, gy1)
        if tree is None:
            raise ValueError("BSP came out empty -- is the geometry closed?")
        nodes, plane_walls = bsp.number_tree(tree)

        # client walls, in tree order, linked per split plane
        room.client_walls = []
        for w in plane_walls:
            c = ClientWall()
            c.next_num = 0
            c.pos_sidedef, c.neg_sidedef = w.pos_sidedef, w.neg_sidedef
            c.x0, c.y0, c.x1, c.y1 = w.x0, w.y0, w.x1, w.y1
            c.length = w.length / BLAK_FACTOR        # stored in EDITOR units
            # Offsets left at 0.  Accumulating them along runs (mod the 64-unit
            # repeat measured from a1) made the treeline look WORSE in-game, not
            # better -- bigger gaps, texture visibly cut.  Reverted rather than
            # kept on the strength of the theory.
            c.pos_xoff = c.neg_xoff = c.pos_yoff = c.neg_yoff = 0
            c.pos_sector = w.pos_sector + 1 if w.pos_sector >= 0 else 0
            c.neg_sector = w.neg_sector + 1 if w.neg_sector >= 0 else 0
            room.client_walls.append(c)
        # several walls can share one plane; they form a linked list
        for n in nodes:
            if not n.is_leaf:
                ws = n.walls_in_plane
                for i, w in enumerate(ws):
                    nxt = ws[i + 1].num if i + 1 < len(ws) else 0
                    room.client_walls[w.num - 1].next_num = nxt

        # convert to the file's node objects, keeping depth-first order
        idx = {id(n): i + 1 for i, n in enumerate(nodes)}
        conv = {}
        for n in nodes:
            f = BSPNode()
            f.bbox = tuple(float(v) for v in n.bbox)
            if n.is_leaf:
                f.type = BSP_LEAF
                f.sector = n.sector + 1 if n.sector >= 0 else 0
                f.points = [(float(x), float(y)) for (x, y) in n.poly]
                f.pos = f.neg = None
            else:
                f.type = BSP_INTERNAL
                f.a, f.b, f.c = float(n.a), float(n.b), float(n.c)
                f.first_wall = n.walls_in_plane[0].num if n.walls_in_plane else 0
            conv[id(n)] = f
        for n in nodes:
            if not n.is_leaf:
                f = conv[id(n)]
                f.pos = conv[id(n.pos)] if n.pos else None
                f.neg = conv[id(n.neg)] if n.neg else None
                f.pos_num = idx[id(n.pos)] if n.pos else 0
                f.neg_num = idx[id(n.neg)] if n.neg else 0
        room.bsp = conv[id(nodes[0])]

        room.security = 0
        room.server_blob = b""
        return room


class SizeError(ValueError):
    """A requested size that something genuinely cannot handle -- the generator,
    the .roo format or the server.  Unlike other ValueErrors from a random
    layout, trying another seed will not help, so callers must not retry it."""


def recentre(room, span_w, span_h, local_box=None):
    """Move a BUILT room so its things box is exactly
    (-span_w/2, -span_h/2) .. (span_w/2, span_h/2) in editor units.

    The content is centred on the origin; pass local_box=(x0, y0, x1, y1) to
    centre that box instead (the jungle keeps its layout box, so trails that
    reach an edge stay on that edge).  Raises ValueError if the content does
    not fit the span.

    Moving a finished room is exact without rebuilding the BSP: editor
    coordinates shift by (dx, dy), and because client coordinates are measured
    from the things box ((x - left) * 16, (top - y) * 16) every client
    coordinate shifts by one constant too -- client walls, node bounding boxes
    and leaf polygons move, and each split plane a*x + b*y + c keeps its a, b
    with c' = c - a*cx - b*cy."""
    xs = [v for l in room.linedefs for v in (l.x0, l.x1)]
    ys = [v for l in room.linedefs for v in (l.y0, l.y1)]
    if local_box is None:
        mid_x, mid_y = (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0
    else:
        mid_x, mid_y = (local_box[0] + local_box[2]) / 2.0, (local_box[1] + local_box[3]) / 2.0
    dx, dy = -int(round(mid_x)), -int(round(mid_y))
    new_l, new_b = -(span_w // 2), -(span_h // 2)
    new_r, new_t = new_l + span_w, new_b + span_h
    if min(xs) + dx < new_l or max(xs) + dx > new_r or min(ys) + dy < new_b or max(ys) + dy > new_t:
        raise ValueError("map content is %d x %d, larger than the requested %d x %d"
                         % (max(xs) - min(xs), max(ys) - min(ys), span_w, span_h))
    old_l = min(t["xpos"] for t in room.things[:2])
    old_t = max(t["ypos"] for t in room.things[:2])
    cx = BLAK_FACTOR * (old_l + dx - new_l)
    cy = BLAK_FACTOR * (new_t - old_t - dy)

    for l in room.linedefs:
        l.x0 += dx; l.x1 += dx
        l.y0 += dy; l.y1 += dy
    # Slopes live in client space too: the plane's d moves like a split plane's
    # c, the texture origin (x, y) is a client point, and the three stored
    # points are editor vertices kept as 16-bit numbers.
    for s in room.sectors:
        for sl in (s.floor_slope, s.ceiling_slope):
            if sl is None:
                continue
            sl.d = sl.d - sl.a * cx - sl.b * cy
            sl.x += cx
            sl.y += cy
            sl.points = [(px + dx, py + dy, pz) for (px, py, pz) in sl.points]
            if any(not (-32768 <= v <= 32767) for (px, py, _pz) in sl.points for v in (px, py)):
                raise SizeError("a sloped floor ends up at editor coordinates beyond +/-32767, which the .roo "
                                "slope record stores as 16-bit numbers; use a smaller size")
    for c in room.client_walls:
        c.x0 += cx; c.x1 += cx
        c.y0 += cy; c.y1 += cy
    if room.bsp:
        for n in room.bsp.walk():
            bx0, by0, bx1, by1 = n.bbox
            n.bbox = (bx0 + cx, by0 + cy, bx1 + cx, by1 + cy)
            if n.type == BSP_INTERNAL:
                n.c = n.c - n.a * cx - n.b * cy
            else:
                n.points = [(x + cx, y + cy) for (x, y) in n.points]
    room.things = [{"xpos": new_l, "ypos": new_t}, {"xpos": new_r, "ypos": new_b}]
    room.width = span_w * BLAK_FACTOR
    room.height = span_h * BLAK_FACTOR
    return room


def simple_room(room_id, size=384, margin=64, floor_type=3204, ceiling_type=0,
                floorh=0, ceilh=450, light=50, wall_texture=3204):
    """A single square chamber, `size` editor units across, with `margin`
    units of padding out to the room rectangle."""
    x0, y0 = 0, 0
    x1, y1 = size, size
    b = RoomBuilder((x0 - margin, y0 - margin, x1 + margin, y1 + margin),
                    room_id=room_id)
    sec = b.add_sector(floor_type, ceiling_type, floorh, ceilh, light)
    sd = b.add_sidedef(wall_texture)
    b.add_rect(x0, y0, x1, y1, sd, sec)
    return b.build()


def cave_room(room_id, seed=1, verts=20, rmin=1200, rmax=3000, wobble=0.35,
              grid=8, margin=256, floor_type=3204, ceiling_type=3204,
              floorh=0, ceilh=384, light=140, wall_texture=3204):
    """A single irregular cavern.

    The outline is a radial loop with a random radius per vertex, snapped to a
    grid.  Snapping matters: near-degenerate geometry is what makes BSP building
    fragile, and integer coordinates on a coarse grid keep the splits clean.
    One radius per vertex (not one per axis) keeps the loop simple -- a
    self-intersecting outline is not a room and no BSP builder will save it.
    """
    rnd = random.Random(seed)
    pts = []
    for i in range(verts):
        ang = 2.0 * math.pi * i / verts
        r = rnd.uniform(rmin, rmax) * (1.0 + rnd.uniform(-wobble, wobble))
        x = int(round(r * math.cos(ang) / grid)) * grid
        y = int(round(r * math.sin(ang) / grid)) * grid
        pts.append((x, y))

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    b = RoomBuilder((min(xs) - margin, min(ys) - margin,
                     max(xs) + margin, max(ys) + margin), room_id=room_id)
    sec = b.add_sector(floor_type, ceiling_type, floorh, ceilh, light)
    sd = b.add_sidedef(wall_texture)
    b.add_polygon(pts, sd, sec)
    return b.build()


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "generated.roo"
    room = simple_room(room_id=0)
    room.save(out)
    print("wrote %s (%d bytes)" % (out, os.path.getsize(out)))
    print(Room.load(out).summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
