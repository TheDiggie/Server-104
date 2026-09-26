"""
style_kocatan.py -- map generator style: a Ko'catan building interior
(Ko'catan, the Island Settlement).

Palette measured from Ko'catan's interiors (kocinn, koctav, kocbank, kocapoth,
kocblack, kocstore, koctail, the Hall of Heroes wings) and checked by rendering
the textures: white and tan plaster walls with light wood floors, its own plank
door (8928), a high base floor (372, the settlement sits above sea level), low
ceilings (80-96) and much dimmer rooms than the mainland towns -- Ko'catan's
sectors run light 5-50 where Jasper and Cor Noth run 192.

Its buildings do not hang mainland banners, so there are no wall niches.
"""
from town_building import Town, generate as build

KOCATAN = Town(
    name="Ko'catan",
    walls=[8916, 8974, 9309, 9320],        # white and pale plaster
    floors=[8961, 8964, 9310, 8903],       # light planks, dark red slats, sand
    ceils=[8974, 8915, 9320],
    wall_trim=8964,
    floor_trim=8961,
    shelf=7601,
    carpet=1018,
    dais_floors=[2402, 8961, 8903],
    door=8928,                             # Ko'catan's plank door
    banners=[],
    lights=[30, 40, 50],
    base_floor=372,
    big_gaps=[160, 176],
    small_gaps=[80, 88, 96],               # Ko'catan's rooms are low
    column_tex=8916,
    bench_tex=8961,
)


def generate(width, height, seed):
    return build(KOCATAN, width, height, seed)
