"""
style_victoria.py -- map generator style: a Castle Victoria interior.

Palette measured from the castle's own rooms (castle1, castle1b "Upstairs in
Castle Victoria", castle1c, castle1d and greeny, the Underbasement of Victoria)
and checked by rendering the textures: grey brick 2011 and block wall 4407 over
rock and dirt floors (2104, 2122) and dark wood (3101, 4610), mossy stone 2031
ceilings, floor 128 and the castle's dimmer light (its rooms run 128, with the
underbasement at 10).

Being a castle, its rooms are larger and taller than a town house: it keeps the
big halls, daises, columns and galleries of the shared building generator.
"""
from town_building import Town, generate as build

VICTORIA = Town(
    name="Castle Victoria",
    walls=[2011, 4407, 2031, 2012],
    floors=[2104, 2122, 3101, 2011],
    ceils=[2031, 2011, 4610, 2016],
    wall_trim=4407,
    floor_trim=4610,
    shelf=7601,
    carpet=1018,
    dais_floors=[4410, 2104, 2122],
    door=2033,
    banners=[4802, 4803, 4804, 4805, 4806, 4807],
    lights=[96, 128, 128],
    base_floor=128,
    big_gaps=[192, 224],            # castle halls are taller than a town's
    small_gaps=[128, 144, 160],
    column_tex=4407,
    bench_tex=3101,
)


def generate(width, height, seed):
    return build(VICTORIA, width, height, seed)
