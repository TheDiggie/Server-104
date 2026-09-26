#!/usr/bin/env python3
"""
texcatalog.py -- classify room textures (grdNNNNN.bgf) by how the shipped rooms
actually use them: floor, ceiling, wall, see-through / passable walls, and
likely doors / switches.

Nothing in a texture file says what it is for, but every .roo records which
texture number is on each floor, ceiling and wall side.  Counting those uses
across all rooms gives a reliable answer for anything used more than a few
times.

Doors: a .roo has no notion of a door -- a door is an ordinary wall that the
room's KOD animates.  So doors come from scanning kod/ for room classes:
  * `room_x = x.roo` links the class to its room file
  * `NAME = 5` constants give wall / sector ids
  * AnimateWall(#wall=..., #passable=...) toggles a wall open  -> door wall
  * SetSector(#sector=<name containing DOOR>, ...) lifts a sector -> the walls
    around that sector are the door
Rooms that inherit door constants from a superclass are not followed.
(Switches and levers are game objects, not textures, so they are not here.)

Usage:  python roomedit/roogen/texcatalog.py        (run from the repo root)
Writes: roomedit/roogen/out/texture_catalog.csv and .json
"""
import csv
import glob
import json
import os
import re
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from roofile import Room  # noqa: E402

# sidedef flags (roomedit/include/bsp.h)
WF_TRANSPARENT = 0x02
WF_PASSABLE = 0x04

ROOM_GLOBS = ["resource/rooms/*.roo", "resource/rooms/*/*.roo"]
TEXTURE_GLOBS = ["run/localclient/resource/grd*.bgf", "resource/graphics/**/grd*.bgf"]

ROLES = ["floor", "ceiling", "wall", "wall_above", "wall_below"]


def bgf_info(path):
    """First frame's width/height and frame count from a BGF header:
    magic(4) version(4) name(32) num_bitmaps(4) num_groups(4) max_indices(4)
    shrink(4), then per bitmap width(4) height(4) ..."""
    with open(path, "rb") as fh:
        head = fh.read(64)
    if len(head) < 64 or head[:3] != b"BGF":
        return None
    num_bitmaps, = struct.unpack_from("<i", head, 40)
    shrink, = struct.unpack_from("<i", head, 52)
    w, h = struct.unpack_from("<ii", head, 56)
    return {"width": w, "height": h, "frames": num_bitmaps, "shrink": shrink}


def find_textures():
    found = {}
    for pattern in TEXTURE_GLOBS:
        for p in glob.glob(pattern, recursive=True):
            name = os.path.basename(p).lower()
            try:
                num = int(name[3:8])
            except ValueError:
                continue
            found.setdefault(num, p)   # first glob (client resource dir) wins
    return found


KOD_ROO_RE = re.compile(r"^\s*\w+\s*=\s*([\w.-]+\.roo)\b", re.M | re.I)
KOD_CONST_RE = re.compile(r"^\s*(\w+)\s*=\s*(\d+)\s*$", re.M)
KOD_CALL_RE = re.compile(r"@(AnimateWall|SetSector)\s*,(.*?)\)", re.I | re.S)


def scan_kod_doors(kod_root="kod"):
    """-> {roo filename (lower): {"walls": set(ids), "sectors": set(ids)}}"""
    doors = defaultdict(lambda: {"walls": set(), "sectors": set()})
    for path in glob.glob(os.path.join(kod_root, "**", "*.kod"), recursive=True):
        try:
            text = open(path, encoding="latin-1").read()
        except OSError:
            continue
        roos = KOD_ROO_RE.findall(text)
        if not roos:
            continue
        consts = {k: int(v) for k, v in KOD_CONST_RE.findall(text)}

        def resolve(val):
            val = val.strip()
            if val.isdigit():
                return int(val), ""
            return consts.get(val), val

        for method, args in KOD_CALL_RE.findall(text):
            argmap = dict((k.lower(), v) for k, v in re.findall(r"#(\w+)\s*=\s*([\w$]+)", args))
            for roo in roos:
                d = doors[roo.lower()]
                if method.lower() == "animatewall" and "wall" in argmap:
                    num, name = resolve(argmap["wall"])
                    if num and ("passable" in argmap or "DOOR" in name.upper()):
                        d["walls"].add(num)
                elif method.lower() == "setsector" and "sector" in argmap:
                    num, name = resolve(argmap["sector"])
                    if num and "DOOR" in name.upper():
                        d["sectors"].add(num)
    return doors


def classify(u):
    walls = u["wall"] + u["wall_above"] + u["wall_below"]
    flat = u["floor"] + u["ceiling"]
    total = walls + flat
    if total == 0:
        return "unused", 0.0

    # Doors are ordinary walls, and door textures are reused as plain walls
    # elsewhere, so door use is reported as its own column, not a category.
    if walls and u["passable"] / walls >= 0.5:
        return "passable (fence/grate/curtain)", u["passable"] / walls
    if walls and u["transparent"] / walls >= 0.5:
        return "see-through wall", u["transparent"] / walls

    # Above/below are not trim: most visible walls in M59 are drawn as the
    # above/below part where neighbouring sector heights differ (7.6k sidedefs
    # have above/below with no normal texture), so all three count as wall.
    shares = {"wall": walls / total, "floor": u["floor"] / total,
              "ceiling": u["ceiling"] / total}
    best = max(shares, key=shares.get)
    if shares[best] >= 0.6:
        return best, shares[best]
    if u["floor"] and u["ceiling"] and not walls:
        return "floor or ceiling", flat / total
    return "mixed (floor/ceiling + wall)", shares[best]


def main():
    rooms = sorted({p for g in ROOM_GLOBS for p in glob.glob(g)})
    if not rooms:
        print("no rooms found -- run from the repo root")
        return 1

    usage = defaultdict(lambda: defaultdict(int))
    room_sets = defaultdict(set)
    failed = []
    bad_sidedef_refs = 0
    kod_doors = scan_kod_doors()
    door_rooms = 0
    unmatched_door_ids = 0

    for path in rooms:
        rname = os.path.basename(path)
        try:
            room = Room.load(path)
        except Exception as e:
            failed.append((rname, repr(e)))
            continue

        kd = kod_doors.get(rname.lower(), {"walls": set(), "sectors": set()})
        # sector ids (user_id) -> sector indices, for lift doors
        door_sector_idx = {i for i, s in enumerate(room.sectors) if s.user_id in kd["sectors"]}
        # sidedef indices that are part of a door
        door_sides = {i for i, sd in enumerate(room.sidedefs) if sd.id in kd["walls"]}
        found_ids = {room.sidedefs[i].id for i in door_sides} | \
                    {room.sectors[i].user_id for i in door_sector_idx}
        unmatched_door_ids += len((kd["walls"] | kd["sectors"]) - found_ids)
        nsec = len(room.sectors)
        for l in room.linedefs:
            secs = {s - 1 for s in (l.sector1, l.sector2) if 1 <= s <= nsec}
            if secs & door_sector_idx:
                door_sides.update(s - 1 for s in (l.sidedef1, l.sidedef2)
                                  if 1 <= s <= len(room.sidedefs))
        if door_sides:
            door_rooms += 1

        for sec in room.sectors:
            for role, tex in (("floor", sec.floor_type), ("ceiling", sec.ceiling_type)):
                if tex:
                    usage[tex][role] += 1
                    room_sets[tex].add(rname)

        # only count sidedefs that are actually attached to a wall
        used = set()
        n = len(room.sidedefs)
        for l in room.linedefs:
            for s in (l.sidedef1, l.sidedef2):
                if s == 0 or s == 0xFFFF:
                    continue
                if 1 <= s <= n:
                    used.add(s - 1)
                else:
                    bad_sidedef_refs += 1
        for i in used:
            sd = room.sidedefs[i]
            for role, tex in (("wall", sd.type_normal), ("wall_above", sd.type_above),
                              ("wall_below", sd.type_below)):
                if not tex:
                    continue
                u = usage[tex]
                u[role] += 1
                room_sets[tex].add(rname)
                if i in door_sides:
                    u["door"] += 1
                if role == "wall":
                    if sd.flags & WF_PASSABLE:
                        u["passable"] += 1
                    if sd.flags & WF_TRANSPARENT:
                        u["transparent"] += 1

    textures = find_textures()
    num_used = len(usage)   # before the loop below reads (and so creates) empty entries
    rows = []
    for num in sorted(set(usage) | set(textures)):
        u = usage[num]
        category, confidence = classify(u)
        info = bgf_info(textures[num]) if num in textures else None
        rows.append({
            "texture": num,
            "file": textures.get(num, "").replace("\\", "/"),
            "category": category,
            "confidence": round(confidence, 2),
            "rooms": len(room_sets[num]),
            **{r: u[r] for r in ROLES},
            "used_as_door": u["door"] > 0,
            "door": u["door"],
            "passable": u["passable"],
            "transparent": u["transparent"],
            "width": info["width"] if info else "",
            "height": info["height"] if info else "",
            "frames": info["frames"] if info else "",
            "missing_file": num not in textures,
        })

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
    os.makedirs(out_dir, exist_ok=True)
    csv_path = os.path.join(out_dir, "texture_catalog.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out_dir, "texture_catalog.json"), "w") as fh:
        json.dump(rows, fh, indent=1)

    counts = defaultdict(int)
    for r in rows:
        counts[r["category"]] += 1
    print("rooms parsed: %d, failed: %d, bad sidedef refs: %d"
          % (len(rooms) - len(failed), len(failed), bad_sidedef_refs))
    for name, err in failed[:10]:
        print("  FAILED %s: %s" % (name, err))
    print("kod: %d room classes with door calls, %d rooms with door walls found, "
          "%d door ids not present in their .roo"
          % (sum(1 for d in kod_doors.values() if d["walls"] or d["sectors"]),
             door_rooms, unmatched_door_ids))
    print("textures: %d (%d used in rooms, %d files on disk, %d used but missing a file)"
          % (len(rows), num_used, len(textures),
             sum(1 for r in rows if r["missing_file"] and r["rooms"])))
    for cat, c in sorted(counts.items(), key=lambda kv: -kv[1]):
        print("  %-32s %d" % (cat, c))
    print("wrote", csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
