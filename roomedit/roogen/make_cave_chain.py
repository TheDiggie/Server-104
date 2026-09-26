#!/usr/bin/env python3
"""
make_cave_chain.py -- generate a run of connected cave rooms and the KOD to go
with them.

Produces N caves in a west-to-east chain:

    cave 1  <-->  cave 2  <-->  cave 3  <-->  cave 4  <-->  cave 5

Each room gets:
  * a generated .roo with corridors reaching the room's things-box edge, which
    is what makes an edge exit fire (room.kod SomethingMoved -> StandardLeaveDir)
  * a `MonsterRoom` subclass with plEdge_Exits linking to its neighbours
  * orc generators, modelled on orccave2.kod

Only W/E exits are used.  The cell grid's row axis is inverted relative to the
room's Y (ey() grows with the row while RoomBuilder.cy() flips), so a north/south
chain would need that unpicked; east/west sidesteps it.

    python roomedit/roogen/make_cave_chain.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

from cave import build_cave, MAX_STEP, HEADROOM   # noqa: E402
from roofile import Room                          # noqa: E402

COUNT = 5
FIRST_RID = 10101
SEEDS = [11, 12, 13, 14, 15]
ROO_DIRS = ["resource/rooms", "run/server/rooms", "run/localclient/resource"]
KOD_DIR = "kod/object/active/holder/room/monsroom"

NAMES = ["The Mouth of the Warren", "A Dripping Gallery", "The Deep Warren",
         "A Chamber of Bones", "The Last Hollow"]

KOD_TEMPLATE = '''// Meridian 59, Copyright 1994-2012 Andrew Kirmse and Chris Kirmse.
// All rights reserved.
//
// This software is distributed under a license that is described in
// the LICENSE file that accompanies it.
//
// Meridian is a registered trademark.


////////////////////////////////////////////////////////////////////////////////
// %(cls)s:  cave %(idx)d of %(count)d in a generated warren.
//
// The geometry was produced by roomedit/roogen (cellular-automata layout, an
// independent ceiling field, BSP built by roogen's port of bspmake.cpp).  It is
// not hand-drawn and there is no .roo in the editor for it.
//
// Rooms are joined by plEdge_Exits: walking past the room's things bounding box
// hands the player to the neighbour at the row/col below.  The generator carved
// a corridor to that boundary and reported these arrival squares.
////////////////////////////////////////////////////////////////////////////////
%(cls)s is MonsterRoom

constants:

   include blakston.khd

resources:

   room_%(low)s = %(roo)s
   room_name_%(low)s = "%(name)s"

classvars:

   vrName = room_name_%(low)s

   viTerrain_type = TERRAIN_CAVES

   viTeleport_row = %(trow)d
   viTeleport_col = %(tcol)d

properties:

   prRoom = room_%(low)s
   piRoom_num = %(rid_name)s

   piBaseLight = LIGHT_NICE
   piOutside_factor = 0

   piGen_time = 25000
   piGen_percent = 80

   piInit_count_min = 4
   piInit_count_max = 7

   piMonster_count_max = 18

messages:

   Constructed()
   {
      plMonsters = [ [&CaveOrc, 55],
                     [&Orc, 30],
                     [&OrcWizard, 15] ];
      plGenerators = %(gens)s;

      propagate;
   }

   CreateStandardExits()
   {
      plEdge_exits = $;
%(exits)s
      propagate;
   }

end
////////////////////////////////////////////////////////////////////////////////
'''


def main():
    os.chdir(ROOT)
    rooms = []

    for i in range(COUNT):
        sides = []
        if i > 0:
            sides.append("W")
        if i < COUNT - 1:
            sides.append("E")
        room, nsec, nwall, open_area, entries = build_cave(
            room_id=FIRST_RID + i, seed=SEEDS[i], exits=tuple(sides))

        # validate before writing anything: seal, and blakserv's movement rules
        def poly_area(poly):
            a = 0.0
            for k in range(len(poly)):
                x0, y0 = poly[k]
                x1, y1 = poly[(k + 1) % len(poly)]
                a += x0 * y1 - x1 * y0
            return abs(a) / 2

        sec = sum(poly_area(nd.points) for nd in room.bsp.walk()
                  if nd.type == 2 and nd.sector > 0)
        blockers = 0
        for w in room.client_walls:
            if not (w.pos_sector and w.neg_sector):
                continue
            A = room.sectors[w.pos_sector - 1]
            B = room.sectors[w.neg_sector - 1]
            sd = room.sidedefs[w.pos_sidedef - 1]
            for S, E in ((A, B), (B, A)):
                if sd.type_below > 0 and (E.floorh - S.floorh) > MAX_STEP:
                    blockers += 1
                if sd.type_above > 0 and (E.ceilh - S.floorh) < HEADROOM:
                    blockers += 1
                if (E.ceilh - E.floorh) < HEADROOM:
                    blockers += 1
        seal = sec / open_area
        # A room with an open exit mouth has slightly MORE floor than it has
        # cells: the leaf at the mouth runs out into the BSP's padding, because
        # the room genuinely is open there.  What must never happen is LESS floor
        # than cells -- that means a hole where a wall should be, or geometry
        # clipped away.  So the two directions are checked differently.
        assert seal >= 1 - 1e-9,             "cave %d has missing floor (seal %.6f)" % (i + 1, seal)
        assert seal <= 1.002,             "cave %d leaks well past its exit mouths (seal %.6f)" % (i + 1, seal)
        assert blockers == 0, "cave %d has %d impassable walls" % (i + 1, blockers)

        # spawn/teleport point: middle of the biggest open leaf
        best = None
        for nd in room.bsp.walk():
            if nd.type == 2 and nd.sector > 0:
                xs = [q[0] for q in nd.points]
                ys = [q[1] for q in nd.points]
                a = (max(xs) - min(xs)) * (max(ys) - min(ys))
                if best is None or a > best[0]:
                    best = (a, sum(xs) / len(xs), sum(ys) / len(ys))
        trow, tcol = int(best[2] // 1024), int(best[1] // 1024)

        # monster generators: spread over the larger open leaves
        leaves = []
        for nd in room.bsp.walk():
            if nd.type == 2 and nd.sector > 0:
                xs = [q[0] for q in nd.points]
                ys = [q[1] for q in nd.points]
                a = (max(xs) - min(xs)) * (max(ys) - min(ys))
                leaves.append((a, int(sum(ys) / len(ys) // 1024),
                               int(sum(xs) / len(xs) // 1024)))
        leaves.sort(reverse=True)
        gens = [(r, c) for _, r, c in leaves[:12]]

        rooms.append(dict(idx=i + 1, room=room, entries=entries, trow=trow,
                          tcol=tcol, gens=gens, nsec=nsec, nwall=nwall,
                          rows=room.height // 1024, cols=room.width // 1024))
        print("cave %d: %3d sectors %4d walls  %2dx%-2d squares  seal=%.6f "
              "blockers=%d  entries=%s"
              % (i + 1, nsec, nwall, room.width // 1024, room.height // 1024,
                 seal, blockers, entries))

    # ---- write .roo files
    for i, r in enumerate(rooms):
        name = "roogen%d.roo" % (i + 1)
        data = r["room"].to_bytes()
        for d in ROO_DIRS:
            with open(os.path.join(d, name), "wb") as fh:
                fh.write(data)
        r["roo"] = name

    # ---- write room classes
    for i, r in enumerate(rooms):
        cls = "RooGenCave%d" % (i + 1)
        low = "roogencave%d" % (i + 1)
        rid_name = "RID_ROOGEN_CAVE%d" % (i + 1)
        exits = []
        if i > 0:
            prev = rooms[i - 1]
            er, ec = prev["entries"]["E"]
            exits.append("      plEdge_exits = Cons([LEAVE_WEST, RID_ROOGEN_CAVE%d, "
                         "%d, %d, ROTATE_NONE], plEdge_exits);" % (i, er, ec))
        if i < COUNT - 1:
            nxt = rooms[i + 1]
            er, ec = nxt["entries"]["W"]
            exits.append("      plEdge_exits = Cons([LEAVE_EAST, RID_ROOGEN_CAVE%d, "
                         "%d, %d, ROTATE_NONE], plEdge_exits);" % (i + 2, er, ec))

        body = KOD_TEMPLATE % dict(
            cls=cls, low=low, idx=i + 1, count=COUNT, roo=r["roo"],
            name=NAMES[i], rid_name=rid_name, trow=r["trow"], tcol=r["tcol"],
            gens="[ " + ", ".join("[%d,%d]" % (a, b) for a, b in r["gens"]) + " ]",
            exits="\n".join(exits) + "\n" if exits else "")
        with open(os.path.join(KOD_DIR, low + ".kod"), "w",
                  encoding="latin-1", newline="") as fh:
            fh.write(body)
        r["cls"] = cls
        r["low"] = low
        r["rid_name"] = rid_name

    print()
    print("wrote %d .roo files and %d room classes" % (len(rooms), len(rooms)))
    for i, r in enumerate(rooms):
        w = "  W<-cave%d" % i if i > 0 else ""
        e = "  E->cave%d" % (i + 2) if i < COUNT - 1 else ""
        print("   %-16s rid=%d teleport=(%d,%d)%s%s"
              % (r["cls"], FIRST_RID + i, r["trow"], r["tcol"], w, e))
    return rooms


if __name__ == "__main__":
    main()
