"""
style_cave.py -- map generator style: multi-level orc cave (cave2.py): chambers
on separate height tiers joined by sloped ramps, with ledges, raised and sunken
patches, ceiling changes and stalagmites, as measured from the shipped orc
caves.  The room is recentred so its box spans -width/2..width/2 by
-height/2..height/2.
"""
from cave2 import generate_cave, C
from generate import recentre, SizeError

ATTEMPTS = 40


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the cave generator works on a %d-unit grid and needs at least 3 cells each way, so X and Y "
                        "must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed)
    recentre(room, width, height)
    return room, summary
