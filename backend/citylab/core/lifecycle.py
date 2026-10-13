"""End of each simulated day.

Stage 2: the day's meetings feed the social graph and a row of statistics is
recorded. Ageing, births, deaths and migration arrive in Stage 3.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from .clock import SimTime
from .people import Person

if TYPE_CHECKING:
    from .world import World


@dataclass
class DayCounts:
    births: int = 0
    deaths: int = 0
    couples: int = 0
    hired: int = 0
    arrived: int = 0
    left: int = 0
    new_friendships: int = 0


def make_couple(w: World, a: Person, b: Person, announce: bool = True) -> None:
    a.partner, b.partner = b.id, a.id
    w.social.tie(a.id, b.id, "partner")
    if announce:
        w.today.couples += 1
        w.emit("couple", f"{a.name} and {b.name} became a couple.", (a.id, b.id))


def end_of_day(w: World) -> None:
    t = w.t
    alive = w.alive()
    sociability = {p.id: p.extraversion for p in alive}
    w.today.new_friendships += w.social.mix_day(w.streams("social"), w.visits, sociability)
    w.today.new_friendships += w.social.close_triads(w.streams("social"), [p.id for p in alive], {p.id: 0.04 * p.extraversion for p in alive})
    w.social.fade()
    w.visits = {}

    row = w.summary()
    row.update(asdict(w.today))
    row["day"] = SimTime(t).day
    row["clustering"] = w.social.clustering() if SimTime(t).day % 7 == 0 else (w.daily[-1]["clustering"] if w.daily else 0.0)
    w.daily.append(row)
    w.emit(
        "day_summary",
        f"Day {row['day']} ended with {row['population']} people and {w.today.new_friendships} new acquaintances.",
        data=row,
    )
    w.today = DayCounts()
