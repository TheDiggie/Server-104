"""
style_cornoth.py -- map generator style: a Cor Noth building interior.

Palette measured from Cor Noth's interiors (corhall, corinn, corgroc, cortail,
cormuseum, coruniv, corgenhall, the Weapon Master's abode) and checked by
rendering the textures: dark woods and red carpet over mossy green stone and
grey brick, base floor 128.  Its buildings do hang banners (4802-4807 in 96x48
niches, floor 32 up) and use the studded door 55028.
"""
from town_building import Town, generate as build

CORNOTH = Town(
    name="Cor Noth",
    walls=[2011, 2001, 6502, 3102],        # grey brick, mossy stone, dark brick
    floors=[4601, 3101, 7301, 1025],       # dark woods and a red patterned floor
    ceils=[9592, 4607, 7302, 2402],
    wall_trim=3102,
    floor_trim=7302,
    shelf=7601,
    carpet=1018,
    dais_floors=[2402, 7301, 1807],
    door=55028,                            # studded door
    banners=[4802, 4803, 4804, 4805, 4806, 4807],
    lights=[55, 60, 67],
    base_floor=128,
    column_tex=55013,
    bench_tex=4607,
)


def generate(width, height, seed):
    return build(CORNOTH, width, height, seed)
