#!/usr/bin/env python3
"""
bsp.py -- build the BSP tree a Meridian .roo needs, for arbitrary geometry.

This is a faithful port of roomedit/source/bspmake.cpp.  Faithful matters: the
client renders straight off this tree, so the goal is to reproduce what the room
editor produces, not to write a nicer BSP builder.

Two places where that means copying behaviour that looks wrong:

  * GCD() is not Euclid's algorithm -- it divides where it should take a
    remainder, so reduce() does NOT return coprime values.  It is deterministic,
    and the plane coefficients written into every shipped room come out of it,
    so it is ported exactly as-is.
  * almost_equal() uses a fixed 1e-4 tolerance rather than anything scaled, and
    the geometry decisions hinge on it.

The algorithm:

    build(walls, poly, sector):
        no poly            -> nothing here
        no walls           -> LEAF with this poly and sector
        otherwise          -> pick a splitter, partition the walls into
                              in-plane / positive / negative, split the region
                              polygon by the same plane, recurse

A leaf's sector is inherited from the splitting wall's pos_sector/neg_sector,
which is how sectors reach the leaves without any separate lookup.
"""

EPS = 0.0001


def almost_equal(a, b=0.0):
    return -EPS <= (a - b) <= EPS


def sgn(v):
    """Which side of a plane a value falls on, using the SAME tolerance as
    wall_intersection().

    bspmake.cpp uses an exact test here (SGNDOUBLE) while wall_intersection
    uses almost_equal, and the two disagree for a point sitting a hair off the
    plane: the caller decides the wall crosses, the intersection routine says an
    endpoint lies on the line, so neither the split path nor the same-side path
    runs and THE WALL IS SILENTLY DROPPED.  The C code logs "something wrong in
    BSPSplitWalls" and carries on without it, leaving a hole that merges an
    interior leaf with the outside.

    Hand-drawn rooms rarely hit it (coarse integer coordinates, mostly
    axis-aligned).  Generated geometry hits it constantly, so the tolerance is
    made consistent here rather than reproducing the bug."""
    if almost_equal(v):
        return 0.0
    return 1.0 if v > 0.0 else -1.0


def _gcd(a, b):
    """bspmake.cpp GCD() -- ported verbatim, including the division that makes
    it not a gcd.  Do not 'fix' this: it decides the plane coefficients."""
    if -1.0 < a < 1.0:
        return abs(b)
    a = abs(a)
    b = abs(b)
    while b > 1.0:
        a, b = b, a / b
    return a


def reduce_vec(dx, dy):
    d = _gcd(dx, dy)
    if -0.001 <= d <= 0.001:
        return dx, dy
    return dx / d, dy / d


def line_equation(x0, y0, x1, y1):
    """a, b, c for the line through the points; normal is the direction rotated
    90 degrees (BSPGetLineEquationFromPoints)."""
    dx, dy = reduce_vec(x1 - x0, y1 - y0)
    a = -dy
    b = dx
    c = -(a * x0 + b * y0)
    return a, b, c


# intersection classes
NO_INTERSECTION, COINCIDE, FIRST_ENDPOINT, SECOND_ENDPOINT, MIDDLE = range(5)


def wall_intersection(w1, w2):
    """How the line of w1 meets the segment w2. Returns (kind, x, y)."""
    a, b, c = line_equation(w1.x0, w1.y0, w1.x1, w1.y1)
    x0, y0, x1, y1 = w2.x0, w2.y0, w2.x1, w2.y1
    s0 = a * x0 + b * y0 + c
    s1 = a * x1 + b * y1 + c

    if almost_equal(s0) and almost_equal(s1):
        return COINCIDE, 0.0, 0.0
    if almost_equal(s0):
        return FIRST_ENDPOINT, x0, y0
    if almost_equal(s1):
        return SECOND_ENDPOINT, x1, y1
    if (s0 > 0.0 and s1 > 0.0) or (s0 < 0.0 and s1 < 0.0):
        return NO_INTERSECTION, 0.0, 0.0

    if s0 > 0.0:
        num, denom = s0, s0 - s1
    else:
        num, denom = -s0, s1 - s0
    dx, dy = x1 - x0, y1 - y0
    return MIDDLE, x0 + num * (dx / denom), y0 + num * (dy / denom)


class Wall:
    """One wall segment in client coordinates.  Split walls share everything
    but their endpoints."""
    __slots__ = ("x0", "y0", "x1", "y1", "pos_sector", "neg_sector",
                 "pos_sidedef", "neg_sidedef", "pos_xoff", "neg_xoff",
                 "pos_yoff", "neg_yoff", "length", "linedef", "num")

    def __init__(self, x0, y0, x1, y1, pos_sector=-1, neg_sector=-1,
                 pos_sidedef=0, neg_sidedef=0, linedef=0):
        self.x0, self.y0, self.x1, self.y1 = (float(x0), float(y0),
                                              float(x1), float(y1))
        self.pos_sector = pos_sector
        self.neg_sector = neg_sector
        self.pos_sidedef = pos_sidedef
        self.neg_sidedef = neg_sidedef
        self.pos_xoff = self.neg_xoff = self.pos_yoff = self.neg_yoff = 0
        self.linedef = linedef
        self.num = 0
        self.length = self.compute_length()

    def compute_length(self):
        return ((self.x1 - self.x0) ** 2 + (self.y1 - self.y0) ** 2) ** 0.5

    def copy(self):
        w = Wall.__new__(Wall)
        for f in Wall.__slots__:
            setattr(w, f, getattr(self, f))
        return w

    def flip(self):
        self.x0, self.x1 = self.x1, self.x0
        self.y0, self.y1 = self.y1, self.y0
        self.pos_sector, self.neg_sector = self.neg_sector, self.pos_sector
        self.pos_sidedef, self.neg_sidedef = self.neg_sidedef, self.pos_sidedef
        self.pos_xoff, self.neg_xoff = self.neg_xoff, self.pos_xoff
        self.pos_yoff, self.neg_yoff = self.neg_yoff, self.pos_yoff

    def __repr__(self):
        return "Wall((%.0f,%.0f)-(%.0f,%.0f) sec=%d/%d)" % (
            self.x0, self.y0, self.x1, self.y1, self.pos_sector, self.neg_sector)


class Node:
    """Internal node or leaf; mirrors BSPnode."""
    __slots__ = ("is_leaf", "a", "b", "c", "walls_in_plane", "pos", "neg",
                 "poly", "sector", "bbox")

    def __init__(self):
        self.is_leaf = False
        self.a = self.b = self.c = 0.0
        self.walls_in_plane = []
        self.pos = self.neg = None
        self.poly = []
        self.sector = -1
        self.bbox = (0.0, 0.0, 0.0, 0.0)

    def walk(self):
        yield self
        if self.pos:
            yield from self.pos.walk()
        if self.neg:
            yield from self.neg.walk()

    def leaves(self):
        for n in self.walk():
            if n.is_leaf:
                yield n


def choose_root(walls):
    """BSPChooseRoot: minimise max(pos, neg); ties go to fewer splits; first
    candidate wins."""
    best = None
    best_count = -1
    best_splits = 999999
    for root in walls:
        a, b, c = line_equation(root.x0, root.y0, root.x1, root.y1)
        pos = neg = splits = 0
        for w in walls:
            s0 = sgn(a * w.x0 + b * w.y0 + c)
            s1 = sgn(a * w.x1 + b * w.y1 + c)
            if s0 * s1 >= 0:
                if almost_equal(s0) and almost_equal(s1):
                    continue
                if s0 > 0.0 or s1 > 0.0:
                    pos += 1
                else:
                    neg += 1
                continue
            pos += 1
            neg += 1
            splits += 1
        m = max(pos, neg)
        if best_count == -1 or m < best_count or (m == best_count and splits < best_splits):
            best_count, best, best_splits = m, root, splits
    return best


def split_walls(walls, root):
    """Partition into (in-plane, positive, negative), splitting crossers.

    The editor builds these lists by prepending, so each comes out reversed
    relative to the input order; that is reproduced here because it decides the
    order walls are written to the file."""
    plane, pos, neg = [], [], []
    a, b, c = line_equation(root.x0, root.y0, root.x1, root.y1)

    for w in walls:
        if w is root:
            plane.insert(0, w)
            continue

        s0 = sgn(a * w.x0 + b * w.y0 + c)
        s1 = sgn(a * w.x1 + b * w.y1 + c)

        if s0 * s1 >= 0:
            if almost_equal(s0) and almost_equal(s1):
                # collinear with the splitter: face it the same way
                a2, b2, _ = line_equation(w.x0, w.y0, w.x1, w.y1)
                if not (almost_equal(a, a2) and almost_equal(b, b2)):
                    if almost_equal(a, -a2) or almost_equal(b, -b2):
                        w.flip()
                plane.insert(0, w)
            elif s0 > 0.0 or s1 > 0.0:
                pos.insert(0, w)
            else:
                neg.insert(0, w)
            continue

        kind, x, y = wall_intersection(root, w)
        if kind != MIDDLE:
            continue                      # already handled above

        neg_wall = w.copy()
        if s0 > 0.0:                      # start is on the positive side
            w.x1, w.y1 = x, y
            neg_wall.x0, neg_wall.y0 = x, y
        else:
            w.x0, w.y0 = x, y
            neg_wall.x1, neg_wall.y1 = x, y
        w.length = w.compute_length()
        neg_wall.length = neg_wall.compute_length()

        if not (almost_equal(w.x0, w.x1) and almost_equal(w.y0, w.y1)):
            pos.insert(0, w)
        if not (almost_equal(neg_wall.x0, neg_wall.x1) and
                almost_equal(neg_wall.y0, neg_wall.y1)):
            neg.insert(0, neg_wall)

    return plane, pos, neg


def split_poly(poly, wall):
    """BSPSplitPoly: cut the closed polygon by the wall's line.
    Returns (pos_poly, neg_poly); either may be empty."""
    a, b, c = line_equation(wall.x0, wall.y0, wall.x1, wall.y1)
    n = len(poly)

    tmp = [poly[0]]
    intr = []

    class _Seg:
        __slots__ = ("x0", "y0", "x1", "y1")
    seg = _Seg()

    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        seg.x0, seg.y0, seg.x1, seg.y1 = p[0], p[1], q[0], q[1]
        kind, x, y = wall_intersection(wall, seg)

        if kind == COINCIDE:
            # the whole polygon lies on one side
            for (px, py) in poly:
                side = a * px + b * py + c
                if side > 0.0:
                    return list(poly), []
                if side < 0.0:
                    return [], list(poly)
            return [], []

        if kind == FIRST_ENDPOINT:
            if len(intr) >= 2:
                return [], []
            intr.append(len(tmp) - 1)
            tmp.append(q)
        elif kind == MIDDLE:
            tmp.append((x, y))
            if len(intr) >= 2:
                return [], []
            intr.append(len(tmp) - 1)
            tmp.append(q)
        else:                              # NO_INTERSECTION or SECOND_ENDPOINT
            tmp.append(q)

    tmp.pop()                              # last point repeats the first
    m = len(tmp)
    if len(intr) < 2 or m == 0:
        return [], []

    pos_poly = []
    i = 0
    while True:
        k = (i + intr[0]) % m
        pos_poly.append(tmp[k])
        i += 1
        if k == intr[1]:
            break

    neg_poly = []
    i = 0
    while True:
        k = (i + intr[1]) % m
        neg_poly.append(tmp[k])
        i += 1
        if k == intr[0]:
            break

    side = sum(a * px + b * py + c for (px, py) in pos_poly)
    if side < 0.0:
        pos_poly, neg_poly = neg_poly, pos_poly
    return pos_poly, neg_poly


def build_node(walls, poly, sector):
    if not poly or (not walls and sector == -1):
        return None

    node = Node()
    if not walls:
        node.is_leaf = True
        node.poly = poly
        node.sector = sector
        return node

    root = choose_root(walls)
    plane, pos_walls, neg_walls = split_walls(walls, root)

    node.a, node.b, node.c = line_equation(root.x0, root.y0, root.x1, root.y1)
    node.walls_in_plane = plane

    pos_poly, neg_poly = split_poly(poly, root)
    node.pos = build_node(pos_walls, pos_poly, root.pos_sector)
    node.neg = build_node(neg_walls, neg_poly, root.neg_sector)
    return node


def find_bounding_boxes(node):
    """Leaf boxes come from their polygon; internal boxes are the union of the
    children's, plus any walls sitting in the plane."""
    if node is None:
        return None
    if node.is_leaf:
        xs = [p[0] for p in node.poly]
        ys = [p[1] for p in node.poly]
        node.bbox = (min(xs), min(ys), max(xs), max(ys))
        return node.bbox

    boxes = [bb for bb in (find_bounding_boxes(node.pos),
                           find_bounding_boxes(node.neg)) if bb]
    for w in node.walls_in_plane:
        boxes.append((min(w.x0, w.x1), min(w.y0, w.y1),
                      max(w.x0, w.x1), max(w.y0, w.y1)))
    if not boxes:
        node.bbox = (0.0, 0.0, 0.0, 0.0)
    else:
        node.bbox = (min(b[0] for b in boxes), min(b[1] for b in boxes),
                     max(b[2] for b in boxes), max(b[3] for b in boxes))
    return node.bbox


def build_tree(walls, min_x, min_y, max_x, max_y):
    """Entry point.  The initial region is the room's bounding rectangle."""
    poly = [(float(min_x), float(min_y)), (float(max_x), float(min_y)),
            (float(max_x), float(max_y)), (float(min_x), float(max_y))]
    tree = build_node(list(walls), poly, -1)
    find_bounding_boxes(tree)
    return tree


def number_tree(tree):
    """Assign 1-based depth-first numbers to nodes and walls, the way
    NumberNodes does, and return (nodes, walls) in that order."""
    nodes = list(tree.walk()) if tree else []
    walls = []
    for n in nodes:
        if not n.is_leaf:
            for w in n.walls_in_plane:
                walls.append(w)
                w.num = len(walls)
    return nodes, walls
