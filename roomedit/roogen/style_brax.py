"""
style_brax.py -- map generator style: the ruins of Brax.

Measured from the Brax rooms (necarea2 "Ancient Graveyard of Brax", necarea3
"Decaying City of Brax", necarea4 "Within the Walls of Castle Brax", necarea5
"Ruins of Castle Brax"): roofed ruins in a necrotic green palette -- floors
9739/9683/9681, ceilings 9738/9740, walls 9736 (green brick), 9678 (mossy
stone), 9679/9680 -- 47-76% angled walls, 25 sloped sectors across the four
rooms (so ramps are common), floors spanning 0-520, and bright light (188-227).
"""
from cave2 import CaveStyle, generate_cave, C
from generate import recentre, SizeError

ATTEMPTS = 40

BRAX = CaveStyle(
    "Brax ruins",
    floors=[9681, 9681, 9683, 9739],    # 9681 x70 is the commonest Brax floor
    ramp=9683,
    ceils=[9738, 9738, 9739, 9740],     # 9738 x83 dominates the ceilings
    # Solid walls, in the proportion necarea1-6 actually use them: 9736 x510,
    # 9735 x301, 9737 x197 (all 128 tall), then 9678 and 9698 (64).  9735 and 9737
    # were missing before, which is why the ruins were all one stone.  9679/9680
    # are 160 tall and the shipped rooms only hang them on 160-tall walls, so they
    # are left out rather than sliced.
    walls=[9736, 9736, 9735, 9737, 9678, 9698],
    light=188,                          # necarea median; the group runs 128-228
    # NO whole-stone snapping.  Measured across 1,333 solid Brax walls, only 2%
    # are a whole number of texture tiles tall (mountains 1%, desert 0%, orc caves
    # 0%) -- the shipped rooms simply let the tile cut at the top, because the
    # client anchors a normal wall at its BOTTOM (d3drender.c D3DRenderWallExtract,
    # !drawTopDown).  Snapping every height to 64 was my theory, the rooms
    # disprove it, and it forced heights Brax never uses.
    # Real wall heights instead: 100 x701, 160 x175, 320 x83, 141, 140, 109, 153.
    gaps=[100, 100, 100, 140, 160, 120, 320],
    tunnel_gaps=[100, 100, 140],
    patch_steps=[-16, 16, 24],
    patch_ceils=[-40, 40, 60, 100],
    tier_max=200,                       # necarea floors span 320-520
    grade=(0.25, 0.40),
    chamber_area=9.0e5,
    patch_rate=140,
)


def generate(width, height, seed):
    if width // C < 3 or height // C < 3:
        raise SizeError("the cave generator works on a %d-unit grid and needs at least 3 cells each way, so X and Y "
                        "must both be at least %d (you entered %d x %d)" % (C, 3 * C, width, height))
    room, summary = generate_cave(width, height, seed, BRAX)
    recentre(room, width, height)
    return room, summary
