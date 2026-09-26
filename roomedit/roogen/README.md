# roogen — a random room generator for Meridian `.roo` files

Generates complete, valid `.roo` room files without the room editor: geometry,
sectors, sidedefs, **and the precompiled BSP tree the client renders from**.

```
python roomedit/roogen/roofile.py                 # parse every room, sanity check
python roomedit/roogen/generate.py out/myroom.roo # generate a room
```

## Files

| File | Purpose |
|---|---|
| `roofile.py` | Read and write ROO v15. The format layer. |
| `generate.py` | Build rooms from parameters. The generation layer. |
| `out/` | Generated rooms. |

## Why this is harder than a WAD

A `.roo` is *not* a Doom WAD. It holds two descriptions of the same room:

* the **roomedit section** — linedefs, sidedefs, sectors: the Doom-style data,
  easy to write;
* the **client section** — a precompiled **BSP tree** plus a wall list per split
  plane. This is what actually gets rendered, and it cannot be hand-authored.
  Generating it is the real work, and it's why "just convert a WAD" doesn't get
  you a room.

There is also a **server section** in the format — and it is always empty.
`SaveServerInfo` is commented out in `save.cpp` ("This is currently unused") and
no room in the game has one, so `server_pos` simply points at end-of-file. That
removes `move.cpp` and all the movement-grid computation from the job.

## How it was verified

Nothing here was taken on trust from reading `save.cpp`:

1. **Parse** — all 362 rooms in `resource/rooms` parse with zero failures.
2. **Round-trip** — every one of those 362 rooms, loaded and written back out,
   is **byte-for-byte identical** to the original. That covers the header,
   section offsets, BSP tree, client walls, slopes, sectors, things, RoomID and
   the security checksum.
3. **Regenerate** — `outgrace.roo` (the simplest shipped room: 4 linedefs, 1
   sector) rebuilt *from parameters* matches the shipped file byte-for-byte in
   **every section except linedef ordering**, which is arbitrary editor
   bookkeeping. The BSP tree and client walls match exactly.
4. **In the game** — a generated room loads on the server and reports the
   correct dimensions.

Step 2 is what caught the one real bug: the reader was missing the 2-byte thing
count and had been reading the wrong bytes as thing coordinates while reporting
success on all 362 rooms. Writing the data back produced files 2 bytes short,
which pointed straight at it.

## Format notes worth keeping

Learned from the shipped rooms, not assumed:

* Sidedef references are **1-based**; 0 means "none".
* Sector references in linedefs are **0-based**; 65535 means "none". In client
  walls and BSP leaves a sector is stored as **index + 1**, 0 = none.
* Client coordinates: `x' = (x - left) * 16`, **`y' = (top - y) * 16`** — Y is
  flipped.
* `width`/`height` come from the **two Things**, which mark opposite corners of
  the room rectangle (`GetRoomSubRect`) — *not* from the geometry extent. The
  things rectangle is normally larger than the geometry, leaving a margin.
* A wall's `length` is in **editor** units, not client units.
* BSP nodes are numbered **1-based, depth-first** (node, pos side, neg side).
* Slope blocks are 46 bytes and the three points are **SHORT**, not int — get
  this wrong and every sector after a sloped one is silently corrupt.
* The security checksum is a running sum of selected fields, finally
  `^ 0x89ab786c`. `Room.computed_security()` implements it; it reproduces the
  stored value on all 362 rooms.

## Current state

Generates **convex single-sector rooms**. For a convex room every wall is a
splitter with the interior on the positive side, so the BSP is a simple chain
ending in one leaf — no general BSP builder needed.

**Not yet done:** arbitrary (concave, multi-sector) layouts need a real BSP
builder that splits walls across planes — the algorithm in
`roomedit/source/bspmake.cpp`. That is the next substantial piece, and it is
what stands between this and interesting generated rooms.

## Trying a generated room in the game

`roogen1.roo` is installed as a worked example:

* `kod/object/active/holder/room/roogen1.kod` — the room class
* `RID_ROOGEN1 = 10100` in `blakston.khd`
* registered in the room makefile and in `CreateAllRoomsIfNew` (system.kod)
* the `.roo` copied to `resource/rooms`, `run/server/rooms`, and
  `run/localclient/resource`

The client reads rooms from `run/localclient/resource`, so a generated room has
to be copied there too or it will not render for the player.
