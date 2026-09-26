"""
preview.py -- draw a small top-down picture of a generated room, for the map
generator window.

Floors are shaded by height (low ground pale blue, high ground warm), water in
blue, and the outside walls in dark grey, which reads for a building's rooms and
for open terrain alike.  Writes a PNG with the standard library only -- no
imaging library is bundled into the exe.
"""
import struct
import zlib

from roofile import BSP_LEAF

BACKDROP = (244, 244, 246)
PAPER = (255, 255, 255)
WALL = (45, 45, 48)
WATER = (86, 152, 205)
LOW = (206, 224, 240)          # lowest floor
HIGH = (226, 197, 164)         # highest floor


def _blend(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def render(room, path, size=420, pad=10):
    """Draw `room` into a PNG at `path`; returns (width, height) in pixels."""
    leaves = [n for n in room.bsp.walk() if n.type == BSP_LEAF and n.sector] if room.bsp else []
    if not leaves:
        return None
    xs = [p[0] for n in leaves for p in n.points]
    ys = [p[1] for n in leaves for p in n.points]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    span = max(x1 - x0, y1 - y0) or 1
    scale = (size - 2 * pad) / span
    w = int((x1 - x0) * scale) + 2 * pad
    h = int((y1 - y0) * scale) + 2 * pad
    px = [[BACKDROP] * w for _ in range(h)]

    floors = [s.floorh for s in room.sectors] or [0]
    lo, hi = min(floors), max(floors)
    water = {i for i, s in enumerate(room.sectors) if s.blak_flags & 3}

    for n in leaves:
        sec = room.sectors[n.sector - 1]
        if (n.sector - 1) in water:
            col = WATER
        else:
            t = (sec.floorh - lo) / ((hi - lo) or 1)
            col = _blend(LOW, HIGH, t) if hi > lo else PAPER
        pts = [((x - x0) * scale + pad, (y1 - y) * scale + pad) for x, y in n.points]
        top = max(0, int(min(p[1] for p in pts)))
        bottom = min(h - 1, int(max(p[1] for p in pts)) + 1)
        for yy in range(top, bottom + 1):
            hits = []
            for i in range(len(pts)):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % len(pts)]
                if (ay <= yy + 0.5 < by) or (by <= yy + 0.5 < ay):
                    hits.append(ax + (yy + 0.5 - ay) * (bx - ax) / (by - ay))
            hits.sort()
            for k in range(0, len(hits) - 1, 2):
                for xx in range(max(0, int(hits[k])), min(w - 1, int(hits[k + 1]) + 1)):
                    px[yy][xx] = col

    def line(ax, ay, bx, by, col, thick=1):
        ax, bx = (ax - x0) * scale + pad, (bx - x0) * scale + pad
        ay, by = (y1 - ay) * scale + pad, (y1 - by) * scale + pad
        steps = int(max(abs(bx - ax), abs(by - ay))) + 1
        for i in range(steps + 1):
            x = int(ax + (bx - ax) * i / steps)
            y = int(ay + (by - ay) * i / steps)
            for dx in range(thick):
                for dy in range(thick):
                    if 0 <= x + dx < w and 0 <= y + dy < h:
                        px[y + dy][x + dx] = col

    for l in room.linedefs:                       # the outside of the map
        if not (l.sidedef1 and l.sidedef2):
            line(l.x0, l.y0, l.x1, l.y1, WALL, 2)

    raw = b"".join(b"\x00" + b"".join(bytes(c) for c in row) for row in px)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff))
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 6))
                 + chunk(b"IEND", b""))
    return w, h
