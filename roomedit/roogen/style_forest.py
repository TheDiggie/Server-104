"""
style_forest.py -- map generator style: the mainland forest (the Forests of
Meridian and the Forest of Farol).

Measured from forest1-5, c6, d6, d6e6, d7, e6, farolwest and razaforest: open
sky over every sector (364 of 383), grass floors 2301/2305/2303, tree walls
1501 and 1502 (both see-through), light 192 with some shaded rooms at 128, and
nearly flat ground.  So it is built like the Ko'catan jungle -- winding trails
between walls of trees, with clearings and the odd pool -- but with no canopy
overhead and a mainland palette.
"""
import random

import jungle
from generate import recentre
from style_jungle import random_layout

FOREST = jungle.Wood(
    name="mainland forest",
    ground=2301,
    canopy=0,                  # no canopy sectors: the forest is open to the sky
    wall=1501,                 # trees
    bush=1502,                 # undergrowth
    water=8911,
    mud=2305,
    light=192,
    ground_h=128,
    sky_h=560,
)


def generate(width, height, seed):
    rnd = random.Random(seed)
    trails, glades = random_layout(width, height, rnd)
    room, info = jungle.build_jungle(trails, glades, width, height, seed,
                                     "Mainland forest %dx%d" % (width, height), clip=True, wood=FOREST)
    recentre(room, width, height, local_box=(0, 0, width, height))
    return room, info["summary"]
