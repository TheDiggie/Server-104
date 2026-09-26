"""
style_mountains.py -- map generator style: the Cragged Mountains.

Measured from g8, g9, i8 and i9 (the rooms the user named): open sky over 548
sectors, NO sloped sectors anywhere, light 192, and a great many floor levels --
23 in g8, 125 in g9, 72 in i8, 87 in i9.  So the mountains are stepped rock
terraces rather than ramped galleries.

The wall texture is ONE stone: 2103 is 1,343 of the 1,360 solid walls in the
four rooms.  2104 and 2123 are FLOORS (321 and 210 sectors) -- hanging them on
walls, as this style did, is the same class of mistake as the spider web.  The
cliff faces below a drop are 2103 (x1451) and 2104 (x1352).  Walls are tall:
400 x252, then 500, 370, 350, 242, 232, 210.
"""
from cave2 import CaveStyle, generate_cave, C
from generate import recentre, SizeError

ATTEMPTS = 40

MOUNTAINS = CaveStyle(
    "Cragged Mountains",
    floors=[2104, 2104, 2123, 2123, 2122],
    ramp=2104,
    ceils=[0],
    walls=[2103],                   # 2103 is 1343 of 1360 solid walls in g8/g9/i8/i9
    light=192,
    sky=True,
    sky_gap=400,                    # measured walls: 400 x252, 500, 370, 350
    gaps=[400],
    terrain=True,                   # broad open ground, not chambers on strings
    # 23-125 floor levels per room over a 290-424 span: more, smaller shelves than
    # the 6-10 this style had, but still terraces (the real rooms have NO slopes)
    terrace_step=24,
    terraces=(10, 20),
    plateau=0.6,
    island_chance=0.004,            # rock outcrops
)


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the terrain generator works on a %d-unit grid and needs at least 3 cells each way, so X and "
                        "Y must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed, MOUNTAINS)
    recentre(room, width, height)
    return room, summary
