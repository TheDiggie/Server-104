"""
style_marcrypt.py -- map generator style: the crypts under Marion.

Measured from the four rooms the KOD points at -- mardun01.roo ("The crypt in
Marion"), mardun02.roo ("Resting place of Marion's ancestors"), mardun03.roo and
marcrypt4.roo:

  solid walls  50077 x784, 9001 x513, 3403 x420, 2129 x390 (all 64 tall bar
               2129, which is 80)
  floors       2121 x421, 2129 x182, 2125 x48
  ceilings     2125 x449, 2129 x236, 2121 x57
  light        128-158, no room brighter
  wall heights 64 x522, then 74, 75, 63, 96, 84, 85, 80 -- low, cramped ceilings
  shape        198-471 sectors, 80-94 floor levels, median wall 24-32 units,
               only 11-42% angled: a warren of small chambers on short corridors
  and 51% of sides are impassable -- tombs and ledges you cannot cross.
"""
from dungeon import Dungeon, generate as build

ATTEMPTS = 40

CRYPT = Dungeon(
    "Marion crypt",
    walls=[50077, 50077, 9001, 3403, 2129],
    # 2125 is in `ceils` only: repo-wide it is a ceiling 852 times against 294
    # floors, and 2121 (x421 here) is what the crypts actually stand on
    floors=[2121, 2121, 2121, 2129],
    ceils=[2125, 2125, 2129, 2121],
    light=138,
    # the real crypts are 63-96 tall; 64 is the floor the engine allows with a
    # 16-unit step (64 - 16 = 48, exactly OBJECTHEIGHTROO)
    gaps=[64, 72, 80, 88, 96],
    corridor_gaps=[64, 72, 80],
    room_cells=(4, 10),                 # small chambers, median wall 24-32 units
    corridor_width=(2, 3),
    per_room=300,                       # many of them
    trim=2126,
    tomb=2126,
    tomb_chance=0.7,
    tomb_rise=32,
    round_chance=0.15,                  # mardun03 is 42% angled
    chamfer_chance=0.35,
)


def generate(width, height, seed):
    return build(CRYPT, width, height, seed)
