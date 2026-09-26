"""
style_tos.py -- map generator style: a Tos building interior.

Palette measured from Tos's interiors (tosinn, toshall, tosbank, tosapoth,
tossmith, tosstorage, toscellar, tostavern, the Hall of the Forgotten Heroes)
and checked by rendering the textures: warm brown woods and cobbles with grey
brick and stone walls, base floor 100, dimmer rooms than Jasper (light ~75).
Tos hangs banners in 96x48 niches like Barloque.
"""
from town_building import Town, generate as build

TOS = Town(
    name="Tos",
    walls=[2011, 9552, 9558, 3102],        # grey brick and stone, wood panelling
    floors=[9570, 8893, 20121, 9576],      # cobbles, parquet, dark and medium planks
    ceils=[4601, 9514, 9577, 7302],
    wall_trim=3102,
    floor_trim=9576,
    shelf=7601,
    carpet=1018,
    dais_floors=[9576, 9570, 20121],
    door=2033,
    banners=[4802, 4803, 4804, 4805, 4806, 4807],
    lights=[75, 80],
    base_floor=100,
    column_tex=9552,
    bench_tex=9577,
)


def generate(width, height, seed):
    return build(TOS, width, height, seed)
