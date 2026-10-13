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
CAR_M_PER_MIN = 420.0  # ~25 km/h in town with no traffic (see transport.py for jams)
CAR_MIN_DISTANCE_M = 1200.0

# how someone moves along each piece of a trip
WALK, CAR, BUS, AUTO, WAIT = 1, 2, 3, 4, 5
LEG_NAMES = {0: "", WALK: "walking", CAR: "driving", BUS: "on a bus", AUTO: "in an auto", WAIT: "waiting"}


@dataclass(slots=True)
class Trip:
    """A planned journey: a polyline with the minute the traveller reaches each point."""

    depart: int
    arrive: int
    points: list[tuple[float, float]]
    times: list[float]  # absolute minute at each point, never decreasing
    legs: list[int]  # how they move along each segment (WALK, CAR, BUS, AUTO, WAIT)
    mode: str  # "walk" | "car" | "bus" | "auto"
    line: str | None = None  # bus route number
    run: object | None = None  # the bus they ride
    stop: str | None = None  # the stop they get on at
    fare: float = 0.0

    @property
    def cumulative(self) -> list[float]:
        out = [0.0]
        for (x0, y0), (x1, y1) in zip(self.points, self.points[1:]):
            out.append(out[-1] + math.hypot(x1 - x0, y1 - y0))
        return out

    def _seg(self, t: float) -> int:
        lo, hi = 0, len(self.times) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.times[mid] <= t:
                lo = mid
            else:
                hi = mid
        return lo

    def position(self, t: float) -> tuple[float, float]:
        if t <= self.times[0]:
            return self.points[0]
        if t >= self.times[-1]:
            return self.points[-1]
        lo = self._seg(t)
        span = self.times[lo + 1] - self.times[lo]
        f = 1.0 if span <= 0 else (t - self.times[lo]) / span
        (x0, y0), (x1, y1) = self.points[lo], self.points[lo + 1]
        return x0 + (x1 - x0) * f, y0 + (y1 - y0) * f

    def leg(self, t: float) -> int:
        if not self.legs:
            return WALK
        if t >= self.times[-1]:
            return self.legs[-1]
        return self.legs[min(len(self.legs) - 1, self._seg(t))]


def timed(points: list[tuple[float, float]], depart: float, speed: float) -> list[float]:
    """Times at each point when moving at a steady speed (metres per minute)."""
    out = [float(depart)]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        out.append(out[-1] + math.hypot(x1 - x0, y1 - y0) / speed)
    return out


class Router:
    def __init__(self, city: City) -> None:
        self.city = city
        self._path = lru_cache(maxsize=50_000)(self._compute)

    def invalidate(self) -> None:
        self._path.cache_clear()

    # snapshots keep the city, not the route cache: it refills itself on the first trips
    def __getstate__(self) -> dict:
        return {"city": self.city}

    def __setstate__(self, state: dict) -> None:
        self.__init__(state["city"])

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

    def points(self, src: Building, dst: Building) -> tuple[list[tuple[float, float]], tuple[int, ...]]:
        nodes, _ = self._path(src.node, dst.node)
        pts = [(src.x + src.w / 2, src.y + src.h / 2)]
        pts += [self.city.node_xy(n) for n in nodes]
        pts.append((dst.x + dst.w / 2, dst.y + dst.h / 2))
        return pts, nodes

    def trip(self, src: Building, dst: Building, depart: int, has_car: bool) -> Trip:
        """A trip on empty streets: on foot, or by car when it is far enough to bother."""
        pts, _ = self.points(src, dst)
        times = timed(pts, depart, WALK_M_PER_MIN)
        mode = "car" if has_car and times[-1] - depart >= CAR_MIN_DISTANCE_M / WALK_M_PER_MIN else "walk"
        if mode == "car":
            times = timed(pts, depart, CAR_M_PER_MIN)
            times.append(times[-1] + 4)  # parking
            pts = pts + [pts[-1]]
        legs = [CAR if mode == "car" else WALK] * (len(pts) - 1)
        return Trip(depart=depart, arrive=max(depart + 1, math.ceil(times[-1])), points=pts, times=times, legs=legs, mode=mode)


def _access(city: City, b: Building) -> float:
    x, y = city.node_xy(b.node)
    return math.hypot(b.x + b.w / 2 - x, b.y + b.h / 2 - y)
