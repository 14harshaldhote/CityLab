"""The social graph: who knows whom, and how well.

People are nodes; edges carry a strength 0..1 and a kind (family, partner, friend).
Friendships grow the way real social networks do:

* **Co-presence.** People who spend the day in the same place (an office, a school,
  a park, a restaurant) meet. Each visitor meets a few others there, and the person
  they meet is picked with probability proportional to (friends + 1): popular people
  gain friends faster (*preferential attachment*, Barabasi-Albert).
* **Triadic closure.** A friend of a friend is introduced now and then, which is why
  real networks are full of triangles.
* **Fading.** Friendships that are not maintained weaken a little every day and
  vanish once they are faint. Family ties never fade.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable

import networkx as nx
import numpy as np

FAMILY_KINDS = ("partner", "parent", "child", "sibling")
NEW_EDGE = 0.06
MEET_GAIN = 0.035
DAILY_FADE = 0.99
WEAK_FADE = 0.96
FORGET_BELOW = 0.02
MAX_TIES = 40


class SocialGraph:
    def __init__(self) -> None:
        self.g = nx.Graph()
        self._top: dict[tuple[int, int, float], list[tuple[int, float]]] = {}  # top_friends answers until a tie changes

    def add_person(self, pid: int) -> None:
        self.g.add_node(pid)

    def remove_person(self, pid: int) -> None:
        if pid in self.g:
            self.g.remove_node(pid)
            self._top.clear()

    def tie(self, a: int, b: int, kind: str, strength: float = 1.0) -> None:
        if a == b:
            return
        self._forget(a, b)
        if self.g.has_edge(a, b):
            e = self.g.edges[a, b]
            if kind in FAMILY_KINDS:
                e["kind"] = kind
            e["w"] = max(e["w"], strength)
        else:
            self.g.add_edge(a, b, w=strength, kind=kind)

    def strengthen(self, a: int, b: int, gain: float) -> bool:
        """Returns True when this created a new acquaintance."""
        if a == b:
            return False
        self._forget(a, b)
        if self.g.has_edge(a, b):
            e = self.g.edges[a, b]
            e["w"] = min(1.0, e["w"] + gain)
            return False
        self.g.add_edge(a, b, w=NEW_EDGE, kind="friend")
        return True

    def strength(self, a: int, b: int) -> float:
        return self.g.edges[a, b]["w"] if self.g.has_edge(a, b) else 0.0

    def friends(self, pid: int, min_strength: float = 0.0) -> list[tuple[int, float]]:
        if pid not in self.g:
            return []
        out = [(int(v), d["w"]) for v, d in self.g[pid].items() if d["kind"] == "friend" and d["w"] >= min_strength]
        out.sort(key=lambda x: (-x[1], x[0]))
        return out

    def _forget(self, a: int, b: int) -> None:
        if self._top:
            for key in [key for key in self._top if key[0] == a or key[0] == b]:
                del self._top[key]

    def top_friends(self, pid: int, k: int, min_strength: float = 0.0) -> list[tuple[int, float]]:
        """The ``k`` strongest friendships, without sorting everyone (remembered until one of their ties changes)."""
        key = (pid, k, min_strength)
        hit = self._top.get(key)
        if hit is not None:
            return hit
        if pid not in self.g:
            return []
        items = ((d["w"], -v, v) for v, d in self.g[pid].items() if d["kind"] == "friend" and d["w"] >= min_strength)
        out = self._top[key] = [(int(v), w) for w, _, v in heapq.nlargest(k, items)]
        return out

    def degree(self, pid: int) -> int:
        return self.g.degree(pid) if pid in self.g else 0

    def mix_day(self, rng: np.random.Generator, visits: dict[int, list[int]], sociability: dict[int, float]) -> int:
        """Apply one day of co-presence meetings. Returns the number of new acquaintances."""
        self._top.clear()
        made = 0
        for place in sorted(visits):
            group = sorted(set(visits[place]))
            if len(group) < 2:
                continue
            weights = np.array([self.degree(p) + 1.0 for p in group])
            weights /= weights.sum()
            for p in group:
                s = sociability.get(p, 0.5)
                k = 1 + int(rng.random() < s)
                for q in rng.choice(len(group), size=min(k, len(group) - 1), replace=False, p=weights):
                    other = group[int(q)]
                    if other == p:
                        continue
                    if self.g.has_edge(p, other):
                        self.strengthen(p, other, MEET_GAIN * (0.5 + s))
                    elif self.degree(p) < MAX_TIES and self.degree(other) < MAX_TIES and rng.random() < 0.05 * (0.5 + s):
                        # most chance meetings stay strangers, and nobody keeps up with more than MAX_TIES people
                        made += self.strengthen(p, other, 0.0)
        return made

    def close_triads(self, rng: np.random.Generator, people: Iterable[int], chance: dict[int, float]) -> int:
        self._top.clear()
        made = 0
        for p in people:
            if rng.random() >= chance.get(p, 0.0):
                continue
            fr = self.friends(p, 0.25)
            if not fr:
                continue
            f = fr[int(rng.integers(len(fr)))][0]
            fof = [v for v, _ in self.friends(f, 0.25) if v != p and not self.g.has_edge(p, v)]
            if fof:
                made += self.strengthen(p, fof[int(rng.integers(len(fof)))], 0.0)
        return made

    def fade(self) -> None:
        self._top.clear()
        drop = []
        for a, b, d in self.g.edges(data=True):
            if d["kind"] == "friend":
                d["w"] *= DAILY_FADE if d["w"] >= 0.15 else WEAK_FADE  # acquaintances fade faster than friends
                if d["w"] < FORGET_BELOW:
                    drop.append((a, b))
        self.g.remove_edges_from(drop)

    def pick_by_degree(self, rng: np.random.Generator, candidates: list[int]) -> int:
        w = np.array([self.degree(p) + 1.0 for p in candidates])
        return candidates[int(rng.choice(len(candidates), p=w / w.sum()))]

    def summary(self) -> dict:
        g = self.g
        n = g.number_of_nodes()
        friend_edges = sum(1 for _, _, d in g.edges(data=True) if d["kind"] == "friend")
        return {
            "people": n,
            "ties": g.number_of_edges(),
            "friendships": friend_edges,
            "avg_ties": round(2 * g.number_of_edges() / n, 2) if n else 0.0,
        }

    def clustering(self) -> float:
        return round(nx.average_clustering(self.g), 3) if self.g.number_of_nodes() else 0.0
