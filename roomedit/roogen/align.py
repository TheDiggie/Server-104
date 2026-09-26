#!/usr/bin/env python3
"""
align.py -- horizontal wall texture alignment for .roo rooms.

How the client maps a wall texture (clientd3d/d3drender.c, D3DRenderWall*):
    t = (xOffset + distance along the wall) * shrink / bitmap_height
  * offsets and wall `length` are both EDITOR units
  * wall bitmaps are stored rotated, so the horizontal repeat is the stored
    bitmap HEIGHT / shrink (grd03401 is stored 96x64 -> repeats every 64)
  * the positive side runs x0,y0 -> x1,y1; the negative side runs the other way
So a texture continues seamlessly from wall A into wall B when
    offset_B == (offset_A + length_A) mod repeat

Verified against the shipped rooms, not assumed: hand-aligned rooms satisfy
that rule on 92-97% of joined same-texture wall pairs (farolwest 971 pairs,
oc02 814), where chance would give a few percent.  And a linedef's xoff equals
its client walls' xoff on 208180 of 208483 sidedefs, i.e. the editor offsets
and the in-game offsets are the same numbers.

Offsets are computed on the linedefs (what the editor shows), by walking runs of
walls that join end-to-start with the same texture on that side.  Each client
wall -- a BSP fragment of some linedef -- then gets its linedef's offset plus how
far along that linedef it starts, so editor and game always agree.

Only horizontal (x) offsets.  Vertical offsets are left alone.

Usage:  python roomedit/roogen/align.py in.roo [out.roo]
"""
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from roofile import Room  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TEXTURE_DIRS = [os.path.join(REPO, "run", "localclient", "resource")]

_repeat = {}


def texture_repeat(tex):
    """Horizontal repeat of a wall texture in editor units, or None."""
    if tex not in _repeat:
        r = None
        for d in TEXTURE_DIRS:
            p = os.path.join(d, "grd%05d.bgf" % tex)
            if os.path.exists(p):
                with open(p, "rb") as fh:
                    h = fh.read(64)
                if len(h) == 64 and h[:3] == b"BGF":
                    shrink, = struct.unpack_from("<i", h, 52)
                    _w, height = struct.unpack_from("<ii", h, 56)
                    if shrink > 0 and height > 0:
                        r = height / shrink
                break
        if r is None:
            # Outside the repo (the packaged map generator) the .bgf files are not
            # there; fall back to the table texture_repeats.py was built from.
            try:
                from texture_repeats import REPEATS
                r = REPEATS.get(tex)
            except ImportError:
                pass
        _repeat[tex] = r
    return _repeat[tex]


def side_texture(room, ref):
    if not ref or ref > len(room.sidedefs):
        return 0
    s = room.sidedefs[ref - 1]
    return s.type_normal or s.type_below or s.type_above


def _key(pt):
    return (round(pt[0], 2), round(pt[1], 2))


def _direction(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1.0
    return dx / n, dy / n


def _chain_offsets(segs):
    """segs: dicts with start, end, length, tex.  Sets seg['off'].

    Runs start at segments nothing leads into; loops are then started anywhere.
    At a junction the straightest continuation wins, so a run follows the wall
    rather than turning into a side passage."""
    by_start = {}
    for s in segs:
        by_start.setdefault((_key(s["start"]), s["tex"]), []).append(s)
    has_pred = set()
    for s in segs:
        for n in by_start.get((_key(s["end"]), s["tex"]), ()):
            if n is not s:
                has_pred.add(id(n))

    done = set()

    def walk(first):
        cur, acc = first, 0.0
        while cur is not None and id(cur) not in done:
            done.add(id(cur))
            rep = texture_repeat(cur["tex"])
            cur["off"] = int(round(acc)) % int(round(rep))
            acc += cur["length"]
            d = _direction(cur["start"], cur["end"])
            best, best_dot = None, -2.0
            for n in by_start.get((_key(cur["end"]), cur["tex"]), ()):
                if id(n) in done:
                    continue
                nd = _direction(n["start"], n["end"])
                dot = d[0] * nd[0] + d[1] * nd[1]
                if dot > best_dot:
                    best, best_dot = n, dot
            cur = best

    for s in segs:
        if id(s) not in has_pred and id(s) not in done:
            walk(s)
    for s in segs:
        if id(s) not in done:
            walk(s)


def continuity(room):
    """(pairs joined with the same texture, pairs that continue seamlessly),
    measured on the client walls -- what the game draws."""
    segs = []
    for c in room.client_walls:
        for ref, off, a, b in ((c.pos_sidedef, c.pos_xoff, (c.x0, c.y0), (c.x1, c.y1)),
                               (c.neg_sidedef, c.neg_xoff, (c.x1, c.y1), (c.x0, c.y0))):
            t = side_texture(room, ref)
            if t and texture_repeat(t):
                segs.append((_key(a), _key(b), c.length, off - 65536 if off > 32767 else off, t))
    by_start = {}
    for s in segs:
        by_start.setdefault((s[0], s[4]), []).append(s)
    pairs = good = 0
    for s in segs:
        for n in by_start.get((s[1], s[4]), ()):
            if n is s:
                continue
            rep = texture_repeat(s[4])
            pairs += 1
            d = (s[3] + s[2] - n[3]) % rep
            if min(d, rep - d) <= 1.5:
                good += 1
    return pairs, good


def align_room(room):
    """Set horizontal offsets on linedefs and client walls in place."""
    # --- linedefs, in editor units
    segs = []
    for l in room.linedefs:
        length = math.hypot(l.x1 - l.x0, l.y1 - l.y0)
        for side, ref, a, b in ((1, l.sidedef1, (l.x0, l.y0), (l.x1, l.y1)),
                                (2, l.sidedef2, (l.x1, l.y1), (l.x0, l.y0))):
            t = side_texture(room, ref)
            if t and texture_repeat(t):
                segs.append({"line": l, "side": side, "ref": ref, "start": a, "end": b,
                             "length": length, "tex": t})
    _chain_offsets(segs)
    for s in segs:
        if s["side"] == 1:
            s["line"].xoff1 = s["off"]
        else:
            s["line"].xoff2 = s["off"]

    # --- client walls: offset of the owning linedef + distance along it
    xs = [t["xpos"] for t in room.things[:2]]
    ys = [t["ypos"] for t in room.things[:2]]
    left, top = min(xs), max(ys)

    def to_editor(x, y):
        return x / 16.0 + left, top - y / 16.0

    owners = {}
    for s in segs:
        owners.setdefault(s["ref"], []).append(s)

    unmatched = []
    for c in room.client_walls:
        e0, e1 = to_editor(c.x0, c.y0), to_editor(c.x1, c.y1)
        for ref, attr, frag_start in ((c.pos_sidedef, "pos_xoff", e0), (c.neg_sidedef, "neg_xoff", e1)):
            t = side_texture(room, ref)
            if not t or not texture_repeat(t):
                continue
            owner = None
            for s in owners.get(ref, ()):
                ax, ay = s["start"]
                bx, by = s["end"]
                # fragment start must lie on this linedef side
                cross = (bx - ax) * (frag_start[1] - ay) - (by - ay) * (frag_start[0] - ax)
                along = ((frag_start[0] - ax) * (bx - ax) + (frag_start[1] - ay) * (by - ay)) / (s["length"] or 1)
                if abs(cross) / (s["length"] or 1) < 0.6 and -0.6 <= along <= s["length"] + 0.6:
                    owner = (s, along)
                    break
            if owner is None:
                unmatched.append((c, attr))
                continue
            s, along = owner
            rep = int(round(texture_repeat(t)))
            setattr(c, attr, int(round(s["off"] + along)) % rep)
    return len(unmatched)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + "_aligned.roo"
    room = Room.load(src)
    before = continuity(room)
    unmatched = align_room(room)
    after = continuity(room)
    room.save(dst)
    again = Room.load(dst)
    with open(dst, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"
    print("seamless joins: before %d/%d, after %d/%d; client wall sides not matched to a linedef: %d"
          % (before[1], before[0], after[1], after[0], unmatched))
    print("wrote", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
