"""Procedural city generator.

The city is a street grid with a few streets removed so it does not look like graph
paper. Blocks are zoned by distance from the centre and by direction: a downtown of
offices and shops, a civic quarter, an industrial edge, residential neighbourhoods,
parks, and a ring of empty land the city can grow into later. Every building hangs
off its nearest street corner, which is where routing starts and ends.

Everything is drawn from one seed, so the same seed always builds the same city.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import networkx as nx
import numpy as np

from .clock import MINUTES_PER_HOUR as H

DISTRICTS = ("North Hill", "Lakeside", "East Market", "Mill Quarter", "South Gardens", "Riverside", "West End", "Old Town")


@dataclass(frozen=True, slots=True)
class Shift:
    start: int  # minute of day
    end: int  # minute of day, may be < start for night shifts
    weekdays_only: bool

    @property
    def length(self) -> int:
        return (self.end - self.start) % (24 * H) or 24 * H


@dataclass(frozen=True, slots=True)
class BuildingType:
    kind: str
    label: str
    jobs: int
    shifts: tuple[Shift, ...]
    wage: float  # per worked day
    open_from: int = 0
    open_to: int = 24 * H
    weekdays_only: bool = False


OFFICE_HOURS = (Shift(9 * H, 17 * H, True),)
TYPES: dict[str, BuildingType] = {
    t.kind: t
    for t in (
        BuildingType("home", "Homes", 0, (), 0.0),
        BuildingType("office", "Office", 30, OFFICE_HOURS, 160.0, 8 * H, 19 * H, True),
        BuildingType("shop", "Shop", 8, (Shift(9 * H + 30, 20 * H, False),), 95.0, 10 * H, 20 * H),
        BuildingType("restaurant", "Restaurant", 8, (Shift(11 * H, 23 * H, False),), 90.0, 11 * H, 23 * H),
        BuildingType("factory", "Factory", 30, (Shift(6 * H, 14 * H, False), Shift(14 * H, 22 * H, False)), 120.0),
        BuildingType("school", "School", 25, (Shift(7 * H + 30, 15 * H + 30, True),), 130.0, 8 * H, 15 * H, True),
        BuildingType(
            "hospital", "Hospital", 60, (Shift(7 * H, 15 * H, False), Shift(15 * H, 23 * H, False), Shift(23 * H, 7 * H, False)), 170.0
        ),
        BuildingType(
            "police", "Police station", 30, (Shift(6 * H, 14 * H, False), Shift(14 * H, 22 * H, False), Shift(22 * H, 6 * H, False)), 140.0
        ),
        BuildingType("city_hall", "City Hall", 40, OFFICE_HOURS, 150.0, 9 * H, 17 * H, True),
        BuildingType("bank", "Bank", 20, OFFICE_HOURS, 165.0, 9 * H, 17 * H, True),
        BuildingType("park", "Park", 2, (Shift(7 * H, 15 * H, False),), 80.0, 6 * H, 22 * H),
        BuildingType("bus_depot", "Bus depot", 20, (Shift(5 * H, 13 * H, False), Shift(13 * H, 21 * H, False)), 110.0),
    )
}


@dataclass(slots=True)
class Building:
    id: int
    kind: str
    name: str
    x: float
    y: float
    w: float
    h: float
    node: int  # nearest street corner
    district: str
    households: int = 0  # capacity, homes only
    students: int = 0  # capacity, schools only
    jobs: list[Shift] = field(default_factory=list)  # one entry per job slot

    @property
    def type(self) -> BuildingType:
        return TYPES[self.kind]

    def is_open(self, minute_of_day: int, weekend: bool) -> bool:
        t = self.type
        if t.weekdays_only and weekend:
            return False
        if t.open_from <= t.open_to:
            return t.open_from <= minute_of_day < t.open_to
        return minute_of_day >= t.open_from or minute_of_day < t.open_to

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "x": round(self.x, 1),
            "y": round(self.y, 1),
            "w": round(self.w, 1),
            "h": round(self.h, 1),
            "district": self.district,
            "households": self.households,
            "jobs": len(self.jobs),
        }


@dataclass
class City:
    size: float  # metres, the map is size x size
    spacing: float
    graph: nx.Graph  # street graph, node attrs x, y; edge attr length
    buildings: list[Building]
    developed: np.ndarray  # bool per block (n-1 x n-1)
    n: int  # corners per side

    def node_xy(self, node: int) -> tuple[float, float]:
        d = self.graph.nodes[node]
        return d["x"], d["y"]

    def of_kind(self, kind: str) -> list[Building]:
        return [b for b in self.buildings if b.kind == kind]

    def to_dict(self) -> dict:
        return {
            "size": self.size,
            "spacing": self.spacing,
            "nodes": [{"id": int(n), "x": d["x"], "y": d["y"]} for n, d in self.graph.nodes(data=True)],
            "edges": [[int(a), int(b)] for a, b in self.graph.edges()],
            "buildings": [b.to_dict() for b in self.buildings],
            "districts": list(DISTRICTS) + ["Downtown"],
        }


def generate_city(seed: int, n: int = 16, spacing: float = 260.0, developed_radius: float = 5.6) -> City:
    """Build a city on an ``n`` x ``n`` grid of street corners."""
    rng = np.random.default_rng(seed)
    blocks = n - 1
    c = (blocks - 1) / 2.0

    def block_info(i: int, j: int) -> tuple[float, float]:
        dx, dy = i - c, j - c
        return math.hypot(dx, dy), math.atan2(dy, dx)

    developed = np.zeros((blocks, blocks), dtype=bool)
    for i in range(blocks):
        for j in range(blocks):
            r, _ = block_info(i, j)
            developed[i, j] = r + rng.normal(0, 0.35) <= developed_radius

    g = nx.Graph()
    node_id = lambda i, j: i * n + j  # noqa: E731
    for i in range(n):
        for j in range(n):
            g.add_node(node_id(i, j), x=i * spacing, y=j * spacing)

    def touches_developed(i0: int, j0: int, i1: int, j1: int) -> bool:
        cells = []
        if i0 == i1:  # vertical street between columns i0-1 and i0
            cells = [(i0 - 1, min(j0, j1)), (i0, min(j0, j1))]
        else:
            cells = [(min(i0, i1), j0 - 1), (min(i0, i1), j0)]
        return any(0 <= a < blocks and 0 <= b < blocks and developed[a, b] for a, b in cells)

    for i in range(n):
        for j in range(n):
            for di, dj in ((1, 0), (0, 1)):
                i1, j1 = i + di, j + dj
                if i1 < n and j1 < n and touches_developed(i, j, i1, j1):
                    g.add_edge(node_id(i, j), node_id(i1, j1), length=spacing)
    g.remove_nodes_from([v for v in list(g.nodes) if g.degree(v) == 0])

    # thin the grid a little, never disconnecting it and never leaving a dead corner
    for a, b in sorted(g.edges(), key=lambda e: rng.random()):
        if rng.random() < 0.09 and g.degree(a) > 2 and g.degree(b) > 2:
            g.remove_edge(a, b)
            if not nx.is_connected(g):
                g.add_edge(a, b, length=spacing)

    zones = _zone_blocks(rng, developed, c)
    buildings: list[Building] = []
    counters: dict[str, int] = {}
    for (i, j), zone in zones.items():
        r, ang = block_info(i, j)
        district = "Downtown" if r < 1.8 else DISTRICTS[int(((ang + math.pi) / (2 * math.pi)) * 8) % 8]
        for kind, (qx, qy, qw, qh), extra in _block_layout(rng, zone, r):
            x = i * spacing + 18 + qx * (spacing - 36)
            y = j * spacing + 18 + qy * (spacing - 36)
            w, h = qw * (spacing - 36) - 8, qh * (spacing - 36) - 8
            node = _nearest_node(g, x + w / 2, y + h / 2)
            counters[kind] = counters.get(kind, 0) + 1
            b = Building(
                id=len(buildings), kind=kind, name=_name(kind, district, counters[kind]),
                x=x, y=y, w=w, h=h, node=node, district=district,
            )
            t = TYPES[kind]
            if kind == "home":
                b.households = extra
            if kind == "school":
                b.students = 320
            for k in range(t.jobs):
                b.jobs.append(t.shifts[k % len(t.shifts)])
            buildings.append(b)
    return City(size=(n - 1) * spacing, spacing=spacing, graph=g, buildings=buildings, developed=developed, n=n)


def _zone_blocks(rng: np.random.Generator, developed: np.ndarray, c: float) -> dict[tuple[int, int], str]:
    zones: dict[tuple[int, int], str] = {}
    cells = [(i, j) for i in range(developed.shape[0]) for j in range(developed.shape[1]) if developed[i, j]]
    for i, j in cells:
        r = math.hypot(i - c, j - c)
        ang = math.degrees(math.atan2(j - c, i - c))
        if r < 2.3:
            zones[(i, j)] = "downtown"
        elif r > 3.6 and -40 < ang < 20:
            zones[(i, j)] = "industrial"
        elif rng.random() < 0.08:
            zones[(i, j)] = "park"
        elif rng.random() < 0.12:
            zones[(i, j)] = "local"  # neighbourhood shops
        else:
            zones[(i, j)] = "residential"
    # one civic block at the centre, the central park (LotusLab's pond lives here) beside it
    central = sorted((k for k, v in zones.items() if v == "downtown"), key=lambda k: ((k[0] - c) ** 2 + (k[1] - c) ** 2, k))
    if len(central) >= 2:
        zones[central[0]] = "civic"
        zones[central[1]] = "central_park"
    # schools: one per ~10 residential blocks, spread out
    res = [k for k, v in zones.items() if v == "residential"]
    for k in [res[i] for i in rng.permutation(len(res))[: max(2, len(res) // 10)]]:
        zones[k] = "school"
    return zones


Layout = list[tuple[str, tuple[float, float, float, float], int]]
QUADS = ((0.0, 0.0, 0.5, 0.5), (0.5, 0.0, 0.5, 0.5), (0.0, 0.5, 0.5, 0.5), (0.5, 0.5, 0.5, 0.5))


def _block_layout(rng: np.random.Generator, zone: str, r: float) -> Layout:
    full = (0.0, 0.0, 1.0, 1.0)
    if zone == "civic":
        kinds = ["city_hall", "police", "bank", "hospital"]
        return [(k, q, 0) for k, q in zip(kinds, QUADS)]
    if zone == "central_park":
        return [("park", full, 0)]
    if zone == "park":
        return [("park", full, 0)]
    if zone == "school":
        return [("school", (0, 0, 1.0, 0.5), 0), ("home", QUADS[2], 6), ("home", QUADS[3], 6)]
    if zone == "industrial":
        out: Layout = [("factory", (0, 0, 1.0, 0.5), 0)]
        out.append(("bus_depot" if rng.random() < 0.15 else "factory", (0, 0.5, 1.0, 0.5), 0))
        return out
    if zone == "downtown":
        out = []
        for q in QUADS:
            u = rng.random()
            out.append(("office" if u < 0.45 else "shop" if u < 0.7 else "restaurant" if u < 0.85 else "home", q, 12))
        return out
    if zone == "local":
        return [("shop", QUADS[0], 0), ("restaurant", QUADS[1], 0), ("home", QUADS[2], 4), ("home", QUADS[3], 4)]
    # residential: apartments nearer the centre, houses further out
    per = 8 if r < 3.5 else 3
    return [("home", q, per) for q in QUADS]


def _nearest_node(g: nx.Graph, x: float, y: float) -> int:
    best, best_d = -1, math.inf
    for v, d in g.nodes(data=True):
        dd = (d["x"] - x) ** 2 + (d["y"] - y) ** 2
        if dd < best_d:
            best, best_d = v, dd
    return int(best)


def _name(kind: str, district: str, k: int) -> str:
    if kind in ("city_hall", "bank", "bus_depot"):
        return TYPES[kind].label
    if kind == "hospital":
        return "City Hospital"
    if kind == "police":
        return "Central Police Station"
    return f"{district} {TYPES[kind].label} {k}"
