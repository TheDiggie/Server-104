"""
style_beach.py -- map generator style: a shoreline.

Measured from desertshore1-4 ("Solitary Shoreline") and f2 ("The sandy shores
of the Great Ocean"): open sky over every sector, sand 9081 with pale water
8968 at depth flags 0xad/0xae, light 192, gentle floors (0-400) and a great deal
of sloped ground -- 113 sloped sectors per shoreline room.  Here that becomes
sand flats at gentle tiers, ramped dunes and flooded hollows.
"""
from cave2 import CaveStyle, generate_cave, C
from generate import recentre, SizeError

ATTEMPTS = 40

BEACH = CaveStyle(
    "shoreline",
    floors=[9081, 9081, 9080, 2122],
    ramp=9081,
    ceils=[0],
    walls=[2122, 7401, 1501, 2903],   # dune faces, rock, palms
    light=192,
    sky=True,
    sky_gap=800,
    water=8968,
    water_flags=0xad,
    water_drop=16,
    gaps=[250],
    terrain=True,                     # sand flats running down to the water
    # desertshore2 is 311 flat joins and a handful of steps: a beach is flat sand
    # meeting the sea, with the odd low rise
    terrace_step=16,
    terraces=(3, 6),
    plateau=0.85,
    water_level=0.42,                 # a good part of the map is sea
    island_chance=0.003,              # rocks in the sand
)


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the terrain generator works on a %d-unit grid and needs at least 3 cells each way, so X and "
                        "Y must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed, BEACH)
    recentre(room, width, height)
    return room, summary
