"""
style_barloque.py -- map generator style: a random Barloque building interior.

The layout and features live in town_building.py; this is Barloque's palette,
measured from its ten interiors and checked by rendering the textures: floor
128, dim own light 64-80, walls 2001/2021/2031/3102, floors 2005/4601/3101/2011,
banners 4802-4807 in 96x48 niches with the floor 32 up, doors built like
paintings (2033 is 64 wide x 96 tall), 7601 bookshelves exactly one texture
(128) tall, 4610 ceiling beams 16 lower, court columns in sandstone 2021 and
benches in 3701 planks.
"""
from town_building import Town, generate as build

BARLOQUE = Town(
    name="Barloque",
    walls=[2001, 2021, 2031, 3102],
    floors=[2005, 4601, 3101, 2011],
    ceils=[4610, 2005, 4607, 4608, 2001],
    wall_trim=3102,            # wood panelling / risers
    floor_trim=4610,           # table and counter tops
    shelf=7601,
    carpet=1018,
    dais_floors=[2402, 7301, 4610],
    door=2033,
    banners=[4802, 4803, 4804, 4805, 4806, 4807],
    lights=[64, 72, 80],
    base_floor=128,
    column_tex=2021,           # barcourt's sandstone columns
    bench_tex=3701,            # barcourt's plank benches
)


def generate(width, height, seed):
    return build(BARLOQUE, width, height, seed)
