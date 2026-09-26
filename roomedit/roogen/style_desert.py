"""
style_desert.py -- map generator style: the Black Desert.

Measured from the sixteen DesertRoom rooms (desertdunes, desertoasis,
desertcliffs, desertbridge, desertriver, waylayoasis and the shorelines): open
sky over nearly every sector, sand 9081/9080/1030 with sandstone cliff walls
10300/10303, water 8968 in the oases at depth flags, light 192, floors spanning
0-1600 and very heavy slopes (179 sloped sectors in a cliff room).  Here that
becomes sand flats on widely separated tiers, long ramps between them, cliff
drops, and the occasional oasis pool.
"""
from cave2 import CaveStyle, generate_cave, C
from generate import recentre, SizeError

ATTEMPTS = 40

DESERT = CaveStyle(
    "Black Desert",
    floors=[9081, 9081, 9081, 9080],  # 9081 is 1996 of the desert's floor sectors
    ramp=9081,
    ceils=[0],
    # The desert has almost NO solid walls -- 182 across all sixteen rooms -- and
    # they are 10300 (x166) and 3101 (x16).  9080/9081 are FLOORS and 8974 is a
    # CEILING: this style hung all three on walls, which is why it read wrong.
    # 10300 is 300 tall and the real walls it hangs on are 1000 (x121) and 4000,
    # so the cliffs here are full-height, not terrace risers.
    # 3101 was dropped after the role audit: across all 362 rooms it is a floor
    # (265 sectors) and a ceiling (275) far more than a solid wall (67).
    walls=[10300],
    light=192,
    sky=True,
    sky_gap=1000,
    water=8968,                       # the oasis water, 238 floor sectors
    water_flags=0xad,
    water_drop=16,
    gaps=[1000],
    terrain=True,                     # dunes and basins, not chambers on strings
    # desertdunes and desertshore1 have ONE floor level each; the rest have 2-15.
    # The real dunes are SLOPES (97-215 sloped sectors per room), which this
    # engine cannot make, so the nearest honest thing is near-flat sand with a
    # couple of steps -- not a contour map.
    terrace_step=16,
    terraces=(3, 6),
    plateau=0.9,
    water_level=0.20,                 # the odd oasis in the low ground
    island_chance=0.002,
)


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the terrain generator works on a %d-unit grid and needs at least 3 cells each way, so X and "
                        "Y must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed, DESERT)
    recentre(room, width, height)
    return room, summary
