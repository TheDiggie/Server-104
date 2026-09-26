#!/usr/bin/env python3
"""
styles.py -- the map generator's style registry.

Each style is a module with generate(width, height, seed) -> (room, summary).
The room's things box spans -width/2..width/2 by -height/2..height/2; the map
does not have to fill it.

Sizes are NOT capped for taste -- only where something really cannot cope:
  * the server (blakserv/roofile.c) converts the room box to 32-bit floats,
    which hold whole client units exactly only up to 2^24; client units are
    editor units x 16, so a side may be at most 1,048,576 editor units
  * the .roo format stores wall / sidedef / sector / BSP node counts and the
    references between them as 16-bit numbers: at most 65,535 of each
  * a style raises generate.SizeError when its own construction cannot fit
    (e.g. a Barloque front door needs a 160-unit wall)
A layout that merely fails its checks raises ValueError and is retried with
another seed; a SizeError is not retried.

Generation runs on a thread with a large stack: the BSP builder and the .roo
node walk recurse as deep as the tree, which huge maps would otherwise overflow.

To add a style: write style_<name>.py, add a line to STYLES, and add a
--hidden-import for it in build_mapgen.ps1.

Usage (testing):  python roomedit/roogen/styles.py "Orc Cave" 3000 2000 out.roo [seed]
"""
import os
import random
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import style_barloque  # noqa: E402
import style_beach  # noqa: E402
import style_brax  # noqa: E402
import style_cave  # noqa: E402
import style_cornoth  # noqa: E402
import style_desert  # noqa: E402
import style_feyforest  # noqa: E402
import style_forest  # noqa: E402
import style_jasper  # noqa: E402
import style_jungle  # noqa: E402
import style_kocatan  # noqa: E402
import style_marcrypt  # noqa: E402
import style_marion  # noqa: E402
import style_mountains  # noqa: E402
import style_sewer  # noqa: E402
import style_spider  # noqa: E402
import style_tos  # noqa: E402
import style_victoria  # noqa: E402
from generate import SizeError  # noqa: E402

# Grouped by the engine behind them; the menu is sorted by name below, so a new
# style can be added to whichever group it belongs to.
_STYLES = [
    # town and castle interiors (town_building)
    ("Barloque Building", style_barloque),
    ("Jasper Building", style_jasper),
    ("Cor Noth Building", style_cornoth),
    ("Marion Building", style_marion),
    ("Tos Building", style_tos),
    ("Ko'catan Building", style_kocatan),
    ("Castle Victoria", style_victoria),
    # woods (jungle)
    ("Ko'catan Jungle", style_jungle),
    ("Mainland Forest", style_forest),
    ("Fey Forest", style_feyforest),
    # open terrain and caves (cave2)
    ("Cragged Mountains", style_mountains),
    ("Beach", style_beach),
    ("Desert", style_desert),
    ("Orc Cave", style_cave),
    ("Spider Nest", style_spider),
    ("Brax Ruins", style_brax),
    # chambers on corridors (dungeon)
    ("Marion Crypt", style_marcrypt),
    ("Sewer", style_sewer),
]

STYLES = sorted(_STYLES, key=lambda item: item[0].lower())

MAX_SPAN = (1 << 24) // 16         # server float precision, in editor units
U16_MAX = 0xFFFF                   # .roo count / reference width


def names():
    return [name for name, _ in STYLES]


def check_format(room):
    """Raise SizeError if the room exceeds what a .roo can store (the writer
    would otherwise wrap the 16-bit counts silently and produce a broken file)."""
    nodes = sum(1 for _ in room.bsp.walk()) if room.bsp else 0
    for what, count in (("walls", len(room.linedefs)), ("sidedefs", len(room.sidedefs)),
                        ("sectors", len(room.sectors)), ("client walls", len(room.client_walls)),
                        ("BSP nodes", nodes)):
        if count > U16_MAX:
            raise SizeError("this map needs %d %s, but a .roo file can hold at most %d; use a smaller size"
                            % (count, what, U16_MAX))


def generate(style, width, height, seed=None, attempts=15):
    """-> (room, summary, seed actually used)"""
    module = dict(STYLES)[style]
    if not (1 <= width <= MAX_SPAN and 1 <= height <= MAX_SPAN):
        raise SizeError("X and Y must be between 1 and %d editor units (you entered %d x %d); beyond that the "
                        "server's floating-point room coordinates stop being exact" % (MAX_SPAN, width, height))
    seed = random.randrange(1, 10 ** 9) if seed is None else seed
    # Offset the seed per style: the layout code is shared, so without this the
    # same seed gives the Fey Forest and the Mainland Forest (or two towns) the
    # very same floor plan, differing only in palette.
    seed += sum(ord(ch) * (i + 7) for i, ch in enumerate(style)) * 104729
    attempts = getattr(module, "ATTEMPTS", attempts)
    problems = []
    for i in range(attempts):
        s = seed + i * 7919
        try:
            room, summary = module.generate(width, height, s)
        except SizeError:
            raise
        except (ValueError, AssertionError) as e:
            problems.append(str(e))
            continue
        check_format(room)
        return room, summary, s
    raise RuntimeError("no valid %s map at %d x %d after %d tries (last problem: %s)"
                       % (style, width, height, attempts, problems[-1]))


def run_with_big_stack(fn, *args, stack_mb=200):     # CPython on Windows refuses stacks over 256 MB
    """Run fn(*args) on a thread with a large stack and a high recursion limit;
    returns its result or re-raises its exception."""
    result = {}

    def target():
        try:
            result["value"] = fn(*args)
        except BaseException as e:  # handed back to the caller below
            result["error"] = e
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, 200000))
    threading.stack_size(stack_mb * 1024 * 1024)
    try:
        t = threading.Thread(target=target)
        t.start()
    finally:
        threading.stack_size(0)
    t.join()
    if "error" in result:
        raise result["error"]
    return result["value"]


def main():
    from roofile import Room
    style, width, height, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    seed = int(sys.argv[5]) if len(sys.argv) > 5 else None
    room, summary, used = run_with_big_stack(generate, style, width, height, seed)
    room.save(out)
    again = Room.load(out)
    with open(out, "rb") as fh:
        assert again.to_bytes() == fh.read(), "round-trip mismatch"
    print("%s %dx%d seed %d: %s -> %s" % (style, width, height, used, summary, out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
