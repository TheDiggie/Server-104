"""
style_jungle.py -- map generator style: random Ko'catan jungle.

A random trail network (edge exits -> hub clearing, an optional loop, winding
branches to glades) laid out inside a width x height box and handed to
jungle.build_jungle(), which does the construction copied from the shipped
jungle rooms and all the checks.  The room is then recentred so its box spans
-width/2..width/2 by -height/2..height/2.
"""
import math
import random

import jungle
from generate import recentre


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def random_layout(w, h, rnd):
    s = min(w, h)
    scale = s / 3136.0
    margin = 280 * _clamp(scale, 0.5, 1.0)
    hub = (rnd.uniform(0.38, 0.62) * w, rnd.uniform(0.38, 0.62) * h)
    hub_r = s * rnd.uniform(0.09, 0.12)
    trails = []
    glades = [(hub, hub_r, "central clearing", True, rnd.random() < 0.75)]

    def meander(a, b, spacing=330):
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy) or 1
        nx, ny = -dy / L, dx / L
        k = max(3, int(L / spacing))
        pts = [a]
        for i in range(1, k):
            t = i / k
            off = rnd.uniform(-1, 1) * min(L * 0.18, s * 0.08)
            pts.append((_clamp(a[0] + dx * t + nx * off, margin, w - margin),
                        _clamp(a[1] + dy * t + ny * off, margin, h - margin)))
        pts.append(b)
        return pts

    # exits end ON the room edge (the painted trail is clipped to the box)
    edges = rnd.sample(["north", "south", "east", "west"], rnd.choice([2, 2, 3]))
    for e in edges:
        tx, ty = rnd.uniform(0.3, 0.7) * w, rnd.uniform(0.3, 0.7) * h
        a = {"north": (tx, h), "south": (tx, 0), "east": (w, ty), "west": (0, ty)}[e]
        trails.append((meander(a, hub), rnd.choice([190, 200, 220])))

    # a loop round an island of jungle, off the first trail
    if s >= 2400 and rnd.random() < 0.7:
        pts = trails[0][0]
        base = pts[len(pts) // 2]
        dx, dy = hub[0] - base[0], hub[1] - base[1]
        L = math.hypot(dx, dy) or 1
        side = rnd.choice((-1, 1)) * s * 0.2
        mid = (_clamp((base[0] + hub[0]) / 2 - dy / L * side, margin, w - margin),
               _clamp((base[1] + hub[1]) / 2 + dx / L * side, margin, h - margin))
        trails.append((meander(base, mid, 260) + meander(mid, hub, 260)[1:], 190))

    # branches to glades; how many follows the floor area (Medium 3136^2 -> ~4)
    branches = int(max(1, round(w * h / 2.5e6 * rnd.uniform(0.8, 1.2))))
    for i in range(branches):
        for _ in range(40):
            if rnd.random() < 0.5:
                start = hub
            else:
                pts = rnd.choice(trails)[0]
                start = pts[rnd.randint(1, len(pts) - 2)]
            ang = rnd.uniform(0, 2 * math.pi)
            length = s * rnd.uniform(0.22, 0.38)
            end = (start[0] + math.cos(ang) * length, start[1] + math.sin(ang) * length)
            R = rnd.uniform(170, 250) * _clamp(scale, 0.75, 1.3)
            edge = margin * max(0.6, min(1.0, scale))
            inside = edge + R <= end[0] <= w - edge - R and edge + R <= end[1] <= h - edge - R
            clear = all(math.hypot(end[0] - c[0], end[1] - c[1]) > R + r2 + 300 * min(1.0, scale)
                        for c, r2, _n, _s, _p in glades)
            if inside and clear:
                trails.append((meander(start, end, 300), rnd.choice([160, 170, 180])))
                glades.append((end, R, "glade %d" % (i + 1), rnd.random() < 0.5, False))
                break
    return trails, glades


def generate(width, height, seed):
    rnd = random.Random(seed)
    trails, glades = random_layout(width, height, rnd)
    room, info = jungle.build_jungle(trails, glades, width, height, seed,
                                     "Ko'catan jungle %dx%d" % (width, height), clip=True)
    recentre(room, width, height, local_box=(0, 0, width, height))
    return room, info["summary"]
