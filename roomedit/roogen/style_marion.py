"""
style_marion.py -- map generator style: a Marion building interior.

Palette measured from Marion's interiors (marhall, marinn, marelder, marheal,
marsmith, marrent, the plantation workers' quarters) and checked by rendering
the textures: grey stone, cobbles and mossy blocks with wood floors, base floor
200.  Marion hangs banners like Barloque, and also uses 4606 in its niches.
"""
from town_building import Town, generate as build

MARION = Town(
    name="Marion",
    walls=[2011, 2031, 2051, 4713],        # grey brick, mossy stone, cobbles, flagstone
    floors=[3101, 3801, 4101, 2011],
    ceils=[2031, 4607, 4610],
    wall_trim=3102,
    floor_trim=4610,
    shelf=7601,
    carpet=1018,
    dais_floors=[4713, 2051, 4607],
    door=2033,
    banners=[4802, 4803, 4804, 4805, 4806, 4807, 4606],
    lights=[70, 80],
    base_floor=200,
    column_tex=2051,
    bench_tex=4607,
)


def generate(width, height, seed):
    return build(MARION, width, height, seed)
