"""
style_spider.py -- map generator style: a spider nest.

Measured from nest1 ("The Spider Nest"): 92 small chambers over 21 floor
levels in a 1696x2400 room, every sector floored AND ceilinged with the same
dark mottled 1605, walls 3301 (with 3302, a web, used sparingly), light 72 and
no slopes.  So the nest is a warren of small dim chambers rather than the orc
caves' long ramped galleries: small chambers, low ceilings, gentle tiers.
"""
from cave2 import CaveStyle, generate_cave
from generate import recentre, SizeError
from cave2 import C

ATTEMPTS = 40

SPIDER = CaveStyle(
    "spider nest",
    floors=[1605],
    ramp=1605,
    ceils=[1605],
    # 3301 (dark rock) is the ONLY solid wall here.  3302 is a web: across the
    # shipped rooms it is a transparent two-sided wall 122 times and passable 102
    # times against 2 solid uses, and in nest1 it is only ever the normal texture
    # of a two-sided wall with WF_TRANSPARENT.  Hung on a solid wall it reads as
    # a hole in the rock.  Webs are strung across openings below instead.
    walls=[3301],
    light=72,
    gaps=[80, 96, 112, 128, 160],
    # nest1 has 21 floor levels and NO sloped sectors, so the nest changes height
    # in single steps between chambers: keep every tier change walkable and no
    # ramp is ever built
    tier_max=24,
    tier_step=8,
    chamber_area=3.2e5,             # many small chambers (nest1: 92 in 1696x2400)
    patch_rate=90,
    patch_steps=[-16, -8, 8, 16, 24],
    tunnel_gaps=[80, 96, 112],
    tunnel_width=(64, 120),
    web=3302,                       # hung across openings, transparent and passable
    web_chance=0.30,                # nest1: 4 of its 11 sidedefs carry the web
)


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the cave generator works on a %d-unit grid and needs at least 3 cells each way, so X and Y "
                        "must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed, SPIDER)
    recentre(room, width, height)
    return room, summary
