"""
style_sewer.py -- map generator style: the sewers under Barloque and Jasper.

Measured from barlsew.roo, barlsew2.roo, barlsew3.roo, jassew1.roo, jassew2.roo
and jassew3.roo:

  solid walls  4606 x973, 2053 x271, 2031 x269, 2011 x266, 2002 x152, 2001 x149
  floors       8895 x445 -- that is the WATER; the dry ledges are 1602 x54,
               2011 and 4606
  ceilings     1602 x378, 2031 x76, 2011 x42
  below walls  8895 x1192, 4606 x168, 7201, 1602, 1802 -- the channel sides
  light        138 almost everywhere (barlsew runs 20-255)
  wall heights 64 x874, 112 x391, 104, 84, 168, 56
  shape        only 11-26% angled and median wall 64: straight, rectilinear
               tunnels, quite unlike the crypts' warren
  animated     8886/8887, the grates, and they hang as walk-through curtains

So: straight corridors between chambers, with a water channel down many of them.
The channel is a `barrier` zone -- you walk the ledge beside it, you do not wade
it, which is also how the engine is allowed to emit an impassable edge.
"""
from dungeon import Dungeon, generate as build

ATTEMPTS = 40

SEWER = Dungeon(
    "sewer",
    walls=[4606, 4606, 2053, 2031, 2011, 2002],
    floors=[1602, 1602, 2011, 4606],
    ceils=[1602, 1602, 2031, 2011],
    light=138,
    gaps=[104, 112, 112, 168],
    corridor_gaps=[84, 104, 112],
    room_cells=(5, 11),
    corridor_width=(3, 5),              # median wall 64 units = 4 cells
    per_room=520,
    trim=4606,                          # the stone lip above the water
    water=8895,
    water_floor=8895,
    water_flags=0xaa,                   # scroll + depth, as the shipped water uses
    water_drop=32,
    water_chance=0.65,
    round_chance=0.0,                   # 11-26% angled: keep it rectilinear
    chamfer_chance=0.1,
)


def generate(width, height, seed):
    return build(SEWER, width, height, seed)
