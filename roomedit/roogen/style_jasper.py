"""
style_jasper.py -- map generator style: a Jasper building interior.

Palette measured from Jasper's own interiors (jasbank, jaselder, jashall,
jasinn, jassmith, jasstore, jastavrn, jasvault and the abandoned buildings) and
checked by rendering the textures: pale plank and parquet floors over grey
stone and brick walls, base floor 0, and no wall niches -- unlike Barloque, no
Jasper interior hangs banners.
"""
from town_building import Town, generate as build

JASPER = Town(
    name="Jasper",
    walls=[2011, 4501, 10013, 3403],       # grey brick and rough stone
    floors=[8893, 2903, 3101, 4713],       # parquet, weathered planks, dark wood, flagstone
    ceils=[1603, 4610, 3101],
    wall_trim=3102,
    floor_trim=4610,
    shelf=7601,
    carpet=1018,
    dais_floors=[2903, 4713, 4610],
    door=2033,
    banners=[],                            # Jasper's interiors have no niches
    lights=[55, 60, 70],
    base_floor=0,
    column_tex=2011,
    bench_tex=2903,
)


def generate(width, height, seed):
    return build(JASPER, width, height, seed)
