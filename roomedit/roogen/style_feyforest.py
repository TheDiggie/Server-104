"""
style_feyforest.py -- map generator style: the Quilicia Wood (the fey forest).

Measured from the eight FeyForest rooms (a1-d2): open sky over every sector
(247 of 255), grass floors 2303/2304, the wood's bramble walls 8869/8870/8871,
water 8911/8912 in its pools, light 192, and flat ground -- five of the eight
rooms have a single floor level.  The wood's walls are transparent and not
vertically tiled (0x222 in the shipped rooms), which is what gives the gaps of
sky between the trees.
"""
import random

import jungle
from generate import recentre
from style_jungle import random_layout

FEY = jungle.Wood(
    name="Quilicia Wood",
    ground=2303,
    canopy=0,                  # the wood is open to the sky
    wall=8869,                 # the fey treeline
    bush=8870,
    water=8912,
    mud=2304,
    light=192,
    ground_h=128,
    sky_h=512,
    wall_flags=0x222,          # transparent, no look-through, no vertical tiling
    bush_flags=(0x222, 0x227),
)


def generate(width, height, seed):
    rnd = random.Random(seed)
    trails, glades = random_layout(width, height, rnd)
    room, info = jungle.build_jungle(trails, glades, width, height, seed,
                                     "Quilicia Wood %dx%d" % (width, height), clip=True, wood=FEY)
    recentre(room, width, height, local_box=(0, 0, width, height))
    return room, info["summary"]
