"""Shortest paths on the street graph (A* via NetworkX), cached.

A city has far fewer distinct corner-to-corner pairs than trips, so paths are cached
by (from, to) corner. The cache is cleared whenever streets change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import networkx as nx

from .citygen import Building, City

WALK_M_PER_MIN = 80.0
CAR_M_PER_MIN = 420.0  # ~25 km/h average in town; traffic arrives in a later stage
CAR_MIN_DISTANCE_M = 1200.0


@dataclass(slots=True)
class Trip:
    depart: int
    arrive: int
    points: list[tuple[float, float]]
    cumulative: list[float]  # metres along the route at each point
    mode: str  # "walk" | "car"

    def position(self, t: int) -> tuple[float, float]:
        if t <= self.depart:
            return self.points[0]
        if t >= self.arrive:
            return self.points[-1]
        total = self.cumulative[-1]
        d = total * (t - self.depart) / (self.arrive - self.depart)
        # binary search the segment
        lo, hi = 0, len(self.cumulative) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cumulative[mid] <= d:
                lo = mid
            else:
                hi = mid
        seg = self.cumulative[hi] - self.cumulative[lo]
        f = 0.0 if seg <= 0 else (d - self.cumulative[lo]) / seg
        (x0, y0), (x1, y1) = self.points[lo], self.points[hi]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f


class Router:
    def __init__(self, city: City) -> None:
        self.city = city
        self._path = lru_cache(maxsize=50_000)(self._compute)

    def invalidate(self) -> None:
        self._path.cache_clear()

    def _compute(self, a: int, b: int) -> tuple[tuple[int, ...], float]:
        g = self.city.graph
        if a == b:
            return (a,), 0.0

        def h(u: int, v: int) -> float:
            du, dv = g.nodes[u], g.nodes[v]
            return math.hypot(du["x"] - dv["x"], du["y"] - dv["y"])

        path = nx.astar_path(g, a, b, heuristic=h, weight="length")
        length = sum(g.edges[u, v]["length"] for u, v in zip(path, path[1:]))
        return tuple(path), length

    def distance(self, src: Building, dst: Building) -> float:
        if src.id == dst.id:
            return 0.0
        _, length = self._path(src.node, dst.node)
        return length + _access(self.city, src) + _access(self.city, dst)

    def trip(self, src: Building, dst: Building, depart: int, has_car: bool) -> Trip:
        nodes, _ = self._path(src.node, dst.node)
        pts = [(src.x + src.w / 2, src.y + src.h / 2)]
        pts += [self.city.node_xy(n) for n in nodes]
        pts.append((dst.x + dst.w / 2, dst.y + dst.h / 2))
        cum = [0.0]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
        dist = cum[-1]
        mode = "car" if has_car and dist >= CAR_MIN_DISTANCE_M else "walk"
        speed = CAR_M_PER_MIN if mode == "car" else WALK_M_PER_MIN
        minutes = max(1, math.ceil(dist / speed) + (4 if mode == "car" else 0))  # parking
        return Trip(depart=depart, arrive=depart + minutes, points=pts, cumulative=cum, mode=mode)


def _access(city: City, b: Building) -> float:
    x, y = city.node_xy(b.node)
    return math.hypot(b.x + b.w / 2 - x, b.y + b.h / 2 - y)
