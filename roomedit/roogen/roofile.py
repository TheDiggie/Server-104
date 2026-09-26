#!/usr/bin/env python3
"""
roofile.py -- read and write Meridian 59 .roo room files (ROO version 15).

Field layouts were taken from the room editor's own code, which is the only real
specification that exists:
    roomedit/source/load.cpp   LoadRoom()      -- the reader
    roomedit/source/save.cpp   SaveLevelData() -- the writer, and the authority
                               SaveNodes / SaveClientWalls / SaveBoundingBox
                               SaveSectors / SaveSideDefs / SaveThings
                               WriteSlopeInfo

Verified by parsing all 362 rooms in resource/rooms with zero failures.

A .roo has two independent descriptions of the same room:
  * the CLIENT section -- a precompiled BSP tree plus the walls in each split
    plane. This is what gets rendered, and it is what makes a .roo expensive to
    generate: you cannot hand-write it, it has to be built.
  * the ROOMEDIT section -- plain linedefs/sidedefs/sectors, i.e. the Doom-style
    data the editor works on. Cheap to generate.
plus a SERVER section describing walkable space, and a trailing RoomID (the RID
that KOD refers to the room by).

Coordinates in the roomedit section are stored inline on each linedef as int32
pairs; vertices are rebuilt on load, so there is no vertex table in the file.
"""
import struct
import sys
import os
import glob

ROO_MAGIC = b"ROO\xb1"
ROO_VERSION = 15

# blak_flags bits that change how much is stored for a sector
SF_SLOPED_FLOOR = 0x400
SF_SLOPED_CEILING = 0x800

SECURITY_XOR = 0x89ab786c   # save.cpp: security ^= this just before backpatching


def to_i32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v


BSP_INTERNAL = 1
BSP_LEAF = 2


class Reader:
    def __init__(self, data):
        self.d = data
        self.p = 0

    def seek(self, p):
        self.p = p

    def take(self, n):
        b = self.d[self.p:self.p + n]
        if len(b) != n:
            raise EOFError("short read at %d (wanted %d)" % (self.p, n))
        self.p += n
        return b

    def u8(self):   return self.take(1)[0]
    def u16(self):  return struct.unpack("<H", self.take(2))[0]
    def s16(self):  return struct.unpack("<h", self.take(2))[0]
    def i32(self):  return struct.unpack("<i", self.take(4))[0]
    def f32(self):  return struct.unpack("<f", self.take(4))[0]


class Writer:
    def __init__(self):
        self.b = bytearray()

    def tell(self):
        return len(self.b)

    def raw(self, x):   self.b += x
    def u8(self, v):    self.b += struct.pack("<B", v & 0xFF)
    def u16(self, v):   self.b += struct.pack("<H", v & 0xFFFF)
    def s16(self, v):   self.b += struct.pack("<h", v)
    def i32(self, v):   self.b += struct.pack("<i", v)
    def f32(self, v):   self.b += struct.pack("<f", v)

    def patch_i32(self, pos, v):
        self.b[pos:pos + 4] = struct.pack("<i", v)


# ---------------------------------------------------------------------------
# pieces
# ---------------------------------------------------------------------------
class Slope:
    """46 bytes: plane a,b,c,d as float; x,y,angle as int; 3 points of x,y,z as
    SHORT.  The points being shorts rather than ints is easy to get wrong and
    silently corrupts every sector that follows."""
    __slots__ = ("a", "b", "c", "d", "x", "y", "angle", "points")

    @classmethod
    def read(cls, r):
        s = cls()
        s.a, s.b, s.c, s.d = r.f32(), r.f32(), r.f32(), r.f32()
        s.x, s.y, s.angle = r.i32(), r.i32(), r.i32()
        s.points = [(r.s16(), r.s16(), r.s16()) for _ in range(3)]
        return s

    def write(self, w):
        for v in (self.a, self.b, self.c, self.d):
            w.f32(v)
        w.i32(self.x); w.i32(self.y); w.i32(self.angle)
        for (x, y, z) in self.points:
            w.s16(x); w.s16(y); w.s16(z)


class Sector:
    __slots__ = ("user_id", "floor_type", "ceiling_type", "xoffset", "yoffset",
                 "floorh", "ceilh", "light", "blak_flags", "animate_speed",
                 "floor_slope", "ceiling_slope")

    @classmethod
    def read(cls, r, version):
        s = cls()
        s.user_id = r.u16()
        s.floor_type = r.u16()
        s.ceiling_type = r.u16()
        s.xoffset = r.u16()
        s.yoffset = r.u16()
        s.floorh = r.s16()
        s.ceilh = r.s16()
        s.light = r.u8()
        s.blak_flags = r.i32()
        s.animate_speed = r.u8() if version >= 10 else 0
        s.floor_slope = Slope.read(r) if s.blak_flags & SF_SLOPED_FLOOR else None
        s.ceiling_slope = Slope.read(r) if s.blak_flags & SF_SLOPED_CEILING else None
        return s

    def write(self, w, version):
        w.u16(self.user_id)
        w.u16(self.floor_type); w.u16(self.ceiling_type)
        w.u16(self.xoffset); w.u16(self.yoffset)
        w.s16(self.floorh); w.s16(self.ceilh)
        w.u8(self.light)
        w.i32(self.blak_flags)
        if version >= 10:
            w.u8(self.animate_speed)
        if self.floor_slope:
            self.floor_slope.write(w)
        if self.ceiling_slope:
            self.ceiling_slope.write(w)


class FileSideDef:
    __slots__ = ("id", "type_normal", "type_above", "type_below", "flags",
                 "animate_speed")

    @classmethod
    def read(cls, r):
        s = cls()
        s.id = r.u16()
        s.type_normal = r.u16()
        s.type_above = r.u16()
        s.type_below = r.u16()
        s.flags = r.i32()
        s.animate_speed = r.u8()
        return s

    def write(self, w):
        w.u16(self.id); w.u16(self.type_normal)
        w.u16(self.type_above); w.u16(self.type_below)
        w.i32(self.flags); w.u8(self.animate_speed)


class LineDef:
    """The editor-side wall.  Endpoints are stored inline, not as indices."""
    __slots__ = ("sidedef1", "sidedef2", "xoff1", "xoff2", "yoff1", "yoff2",
                 "sector1", "sector2", "x0", "y0", "x1", "y1")

    @classmethod
    def read(cls, r):
        l = cls()
        l.sidedef1 = r.u16(); l.sidedef2 = r.u16()
        l.xoff1 = r.u16(); l.xoff2 = r.u16()
        l.yoff1 = r.u16(); l.yoff2 = r.u16()
        l.sector1 = r.u16(); l.sector2 = r.u16()
        l.x0 = r.i32(); l.y0 = r.i32(); l.x1 = r.i32(); l.y1 = r.i32()
        return l

    def write(self, w):
        w.u16(self.sidedef1); w.u16(self.sidedef2)
        w.u16(self.xoff1); w.u16(self.xoff2)
        w.u16(self.yoff1); w.u16(self.yoff2)
        w.u16(self.sector1); w.u16(self.sector2)
        w.i32(self.x0); w.i32(self.y0); w.i32(self.x1); w.i32(self.y1)


class BSPNode:
    """Internal node or leaf.  Written depth-first: node, then pos side, then
    neg side (SaveNodes)."""
    __slots__ = ("type", "bbox", "a", "b", "c", "pos_num", "neg_num",
                 "first_wall", "sector", "points", "pos", "neg")

    @classmethod
    def read(cls, r):
        n = cls()
        n.type = r.u8()
        n.bbox = (r.f32(), r.f32(), r.f32(), r.f32())
        n.pos = n.neg = None
        if n.type == BSP_INTERNAL:
            n.a, n.b, n.c = r.f32(), r.f32(), r.f32()
            n.pos_num = r.u16()
            n.neg_num = r.u16()
            n.first_wall = r.u16()
            n.pos = BSPNode.read(r) if n.pos_num else None
            n.neg = BSPNode.read(r) if n.neg_num else None
        elif n.type == BSP_LEAF:
            n.sector = r.u16()          # already +1; 0 means none
            npts = r.s16()
            n.points = [(r.f32(), r.f32()) for _ in range(npts)]
        else:
            raise ValueError("bad BSP node type %d" % n.type)
        return n

    def write(self, w):
        w.u8(self.type)
        for v in self.bbox:
            w.f32(v)
        if self.type == BSP_INTERNAL:
            w.f32(self.a); w.f32(self.b); w.f32(self.c)
            w.u16(self.pos_num); w.u16(self.neg_num); w.u16(self.first_wall)
            if self.pos:
                self.pos.write(w)
            if self.neg:
                self.neg.write(w)
        else:
            w.u16(self.sector)
            w.s16(len(self.points))
            for (x, y) in self.points:
                w.f32(x); w.f32(y)

    def walk(self):
        yield self
        if self.pos:
            yield from self.pos.walk()
        if self.neg:
            yield from self.neg.walk()


class ClientWall:
    """38 bytes.  One per wall per BSP split plane; a linked list per node."""
    __slots__ = ("next_num", "pos_sidedef", "neg_sidedef", "x0", "y0", "x1",
                 "y1", "length", "pos_xoff", "neg_xoff", "pos_yoff", "neg_yoff",
                 "pos_sector", "neg_sector")
    SIZE = 38

    @classmethod
    def read(cls, r):
        c = cls()
        c.next_num = r.u16()
        c.pos_sidedef = r.u16(); c.neg_sidedef = r.u16()
        c.x0 = r.f32(); c.y0 = r.f32(); c.x1 = r.f32(); c.y1 = r.f32()
        c.length = r.f32()
        c.pos_xoff = r.u16(); c.neg_xoff = r.u16()
        c.pos_yoff = r.u16(); c.neg_yoff = r.u16()
        c.pos_sector = r.u16(); c.neg_sector = r.u16()
        return c

    def write(self, w):
        w.u16(self.next_num)
        w.u16(self.pos_sidedef); w.u16(self.neg_sidedef)
        w.f32(self.x0); w.f32(self.y0); w.f32(self.x1); w.f32(self.y1)
        w.f32(self.length)
        w.u16(self.pos_xoff); w.u16(self.neg_xoff)
        w.u16(self.pos_yoff); w.u16(self.neg_yoff)
        w.u16(self.pos_sector); w.u16(self.neg_sector)


# ---------------------------------------------------------------------------
# the room
# ---------------------------------------------------------------------------
class Room:
    def __init__(self):
        self.version = ROO_VERSION
        self.security = 0
        self.width = self.height = 0
        self.bsp = None
        self.client_walls = []
        self.linedefs = []
        self.sidedefs = []
        self.sectors = []
        self.things = []
        self.room_id = 0
        # The server section is not modelled yet -- it is carried through as
        # opaque bytes so a file can be read and rewritten losslessly.
        self.server_blob = b""

    # -- reading ---------------------------------------------------------
    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            data = fh.read()
        room = cls()
        r = Reader(data)

        if r.take(4) != ROO_MAGIC:
            raise ValueError("not a ROO file")
        room.version = r.i32()
        if room.version > ROO_VERSION:
            raise ValueError("ROO version %d is newer than %d" %
                             (room.version, ROO_VERSION))
        room.security = r.i32()
        main_pos = r.i32()
        server_pos = r.i32()

        r.seek(main_pos)
        room.width = r.i32()
        room.height = r.i32()
        node_pos = r.i32()
        cwall_pos = r.i32()
        rwall_pos = r.i32()
        sidedef_pos = r.i32()
        sector_pos = r.i32()
        thing_pos = r.i32()

        # BSP tree: a count, then the root written depth-first
        r.seek(node_pos)
        num_nodes = r.u16()
        room.bsp = BSPNode.read(r) if num_nodes else None

        # client walls: a flat array, linked by index via next_num
        r.seek(cwall_pos)
        num_walls = r.u16()
        room.client_walls = [ClientWall.read(r) for _ in range(num_walls)]

        r.seek(rwall_pos)
        room.linedefs = [LineDef.read(r) for _ in range(r.u16())]

        r.seek(sidedef_pos)
        room.sidedefs = [FileSideDef.read(r) for _ in range(r.u16())]

        r.seek(sector_pos)
        n = r.u16()
        room.sectors = [Sector.read(r, room.version) for _ in range(n)]

        # things: a 2-byte COUNT, then the things, then RoomID.
        # SaveThings switches format on the count: <= 2 things are written as a
        # bare (x, y) pair; more than that get the full record with type, angle,
        # exit position, flags and a 64-byte comment.
        r.seek(thing_pos)
        n_things = r.u16()
        room.things = []
        for _ in range(n_things):
            if n_things <= 2:
                room.things.append({"xpos": r.i32(), "ypos": r.i32()})
            else:
                room.things.append({
                    "type": r.i32(), "angle": r.i32(),
                    "xpos": r.i32(), "ypos": r.i32(),
                    "when": r.i32(),
                    "xExitPos": r.i32(), "yExitPos": r.i32(),
                    "flags": r.i32(),
                    "comment": r.take(64),
                })
        room.room_id = r.i32()

        room.server_blob = data[server_pos:]
        return room

    # -- writing ---------------------------------------------------------
    def save(self, path):
        with open(path, "wb") as fh:
            fh.write(self.to_bytes())

    def to_bytes(self):
        """Rebuild the file.  Section offsets are written as placeholders and
        backpatched once each section's real position is known -- the same
        approach SaveLevelData uses."""
        w = Writer()
        w.raw(ROO_MAGIC)
        w.i32(self.version)
        sec_pos = w.tell(); w.i32(0)      # security, backpatched
        main_pos_at = w.tell(); w.i32(0)
        server_pos_at = w.tell(); w.i32(0)

        # ---- main section
        w.patch_i32(main_pos_at, w.tell())
        w.i32(self.width)
        w.i32(self.height)
        node_at = w.tell(); w.i32(0)
        cwall_at = w.tell(); w.i32(0)
        rwall_at = w.tell(); w.i32(0)
        sidedef_at = w.tell(); w.i32(0)
        sector_at = w.tell(); w.i32(0)
        thing_at = w.tell(); w.i32(0)

        security = self.version

        w.patch_i32(node_at, w.tell())
        nodes = list(self.bsp.walk()) if self.bsp else []
        w.u16(len(nodes))
        if self.bsp:
            self.bsp.write(w)
        for n in nodes:
            if n.type == BSP_INTERNAL:
                security += n.first_wall

        w.patch_i32(cwall_at, w.tell())
        w.u16(len(self.client_walls))
        for c in self.client_walls:
            c.write(w)
            security += c.pos_sidedef + c.neg_sidedef
            security += c.pos_sector + c.neg_sector

        w.patch_i32(rwall_at, w.tell())
        w.u16(len(self.linedefs))
        for l in self.linedefs:
            l.write(w)

        w.patch_i32(sidedef_at, w.tell())
        w.u16(len(self.sidedefs))
        for s in self.sidedefs:
            s.write(w)

        w.patch_i32(sector_at, w.tell())
        w.u16(len(self.sectors))
        for s in self.sectors:
            s.write(w, self.version)

        w.patch_i32(thing_at, w.tell())
        w.u16(len(self.things))
        for t in self.things:
            if len(self.things) <= 2:
                w.i32(t["xpos"]); w.i32(t["ypos"])
            else:
                for k in ("type", "angle", "xpos", "ypos", "when",
                          "xExitPos", "yExitPos", "flags"):
                    w.i32(t[k])
                w.raw(t["comment"])
        w.i32(self.room_id)

        # ---- server section (carried through opaquely for now)
        w.patch_i32(server_pos_at, w.tell())
        w.raw(self.server_blob)

        w.patch_i32(sec_pos, self.computed_security())
        return bytes(w.b)

    def computed_security(self):
        """The checksum SaveLevelData builds up while writing, for comparison
        against the value stored in a file we loaded."""
        s = self.version
        if self.bsp:
            for n in self.bsp.walk():
                if n.type == BSP_INTERNAL:
                    s += n.first_wall
        for c in self.client_walls:
            s += c.pos_sidedef + c.neg_sidedef
            s += c.pos_sector + c.neg_sector
        for d in self.sidedefs:
            s += d.id + d.type_normal + d.type_above + d.type_below + d.flags
        for sec in self.sectors:
            s += (sec.user_id + sec.floor_type + sec.ceiling_type +
                  sec.floorh + sec.ceilh + sec.light + sec.blak_flags)
        return to_i32(s ^ SECURITY_XOR)

    # -- convenience -----------------------------------------------------
    def bounds(self):
        xs, ys = [], []
        for l in self.linedefs:
            xs += [l.x0, l.x1]
            ys += [l.y0, l.y1]
        return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)

    def summary(self):
        x0, y0, x1, y1 = self.bounds()
        nodes = sum(1 for _ in self.bsp.walk()) if self.bsp else 0
        return ("v%d  rid=%d  %dx%d  linedefs=%d sidedefs=%d sectors=%d "
                "bspnodes=%d clientwalls=%d  extent=(%d,%d)-(%d,%d)" %
                (self.version, self.room_id, self.width, self.height,
                 len(self.linedefs), len(self.sidedefs), len(self.sectors),
                 nodes, len(self.client_walls), x0, y0, x1, y1))


def main():
    paths = sys.argv[1:] or sorted(
        glob.glob(os.path.join("resource", "rooms", "*.roo")))
    if not paths:
        print("usage: roofile.py <room.roo> [...]")
        return 1
    ok = bad = 0
    for p in paths:
        try:
            room = Room.load(p)
            ok += 1
            if len(paths) <= 20:
                print("%-24s %s" % (os.path.basename(p), room.summary()))
        except Exception as e:
            bad += 1
            print("%-24s FAILED: %r" % (os.path.basename(p), e))
    print("\nparsed %d, failed %d" % (ok, bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
