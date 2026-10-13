"""Life, once a day: ageing, school, jobs, love, births, deaths, moving in and out.

Runs at every simulated midnight. Each rule is a small, plain probability so the
population grows (or shrinks) naturally from its own structure rather than from a
scripted curve:

* **Deaths** follow the Gompertz law: the yearly risk roughly doubles every 7.7 years.
* **Couples** form between single adults who are already close in the social graph,
  more likely the more alike their personalities are. They move in together.
* **Births** come from couples, with a fertility curve that peaks near 29 and falls
  with each child they already have and when the home is crowded.
* **Jobs**: unemployed adults look for the nearest open job every day.
* **Leaving home**: grown children move out when a home is free.
* **Migration**: when the city has more open jobs than job-seekers and free homes,
  newcomers arrive, often following a friend already here (preferential attachment
  again). Long-term unemployed households may leave.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

import numpy as np

from .clock import DAYS_PER_YEAR, MINUTES_PER_DAY, MINUTES_PER_YEAR, SimTime
from .people import Person, gompertz_annual

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
    rng = w.streams("life")
    t = w.t
    alive = w.alive()

    # social graph: today's meetings, friends of friends, fading
    sociability = {p.id: p.extraversion for p in alive}
    w.today.new_friendships += w.social.mix_day(w.streams("social"), w.visits, sociability)
    w.today.new_friendships += w.social.close_triads(w.streams("social"), [p.id for p in alive], {p.id: 0.04 * p.extraversion for p in alive})
    w.social.fade()
    w.visits = {}
    money = w.economy.end_of_day()

    for p in alive:
        _birthday(w, p, t)
        age = p.age(t)
        # health drifts down with age and recovers a little when young
        p.health = float(np.clip(p.health - max(0.0, age - 40) * 0.00002 + (0.0004 if age < 40 else 0.0), 0.05, 1.0))
        if rng.random() < gompertz_annual(age, p.health) / DAYS_PER_YEAR:
            _die(w, p)

    alive = w.alive()
    _jobs(w, rng, alive)
    _romance(w, rng, alive)
    _births(w, rng, alive)
    _leave_home(w, rng, alive)
    if SimTime(t).day % 7 == 0:
        _migration(w, rng)

    row = w.summary()
    row.update(asdict(w.today))
    row.update({k: v for k, v in money.items() if k != "flows"})
    row["day"] = SimTime(t).day
    row["clustering"] = w.social.clustering() if SimTime(t).day % 7 == 0 else (w.daily[-1]["clustering"] if w.daily else 0.0)
    w.daily.append(row)
    w.emit(
        "day_summary",
        f"Day {row['day']} ended with {row['population']} people: {w.today.births} born, {w.today.deaths} died, "
        f"{w.today.arrived} arrived, {w.today.left} left, {w.today.couples} new couples, {w.today.hired} hired.",
        data=row,
    )
    w.today = DayCounts()


def _birthday(w: World, p: Person, t: int) -> None:
    if (t - p.born) % MINUTES_PER_YEAR >= MINUTES_PER_DAY:
        return
    age = int(round((t - p.born) / MINUTES_PER_YEAR))
    if age == 6 and p.school is None:
        if w.enrol(p):
            w.emit("school_start", f"{p.name} started at {w.city.buildings[p.school].name}.", (p.id,), p.school)
    elif age == 18 and p.school is not None:
        school = w.city.buildings[p.school].name
        w.unenrol(p)
        p.skill = min(1.0, p.skill + 0.15)
        p.unemployed_since = t
        w.emit("graduated", f"{p.name} finished school at {school} and is looking for work.", (p.id,))
    elif age == 65 and not p.retired:
        p.retired = True
        place = w.city.buildings[p.job.building].name if p.job else None
        w.fire(p)
        p.unemployed_since = None
        w.emit("retired", f"{p.name} retired" + (f" from {place}." if place else "."), (p.id,))
    if p.job is not None:
        p.skill = min(1.0, p.skill + 0.01)  # a year of experience


def _die(w: World, p: Person) -> None:
    t = w.t
    p.alive = False
    p.died = t
    age = int(p.age(t))
    w.fire(p)
    w.unenrol(p)
    w.economy.close(p, "died")
    if p.partner is not None and p.partner in w.people:
        w.people[p.partner].partner = None
    _leave_household(w, p)
    w.social.remove_person(p.id)
    w.today.deaths += 1
    w.emit("death", f"{p.name} died at the age of {age}.", (p.id,), data={"age": age})


def _leave_household(w: World, p: Person) -> None:
    hh = w.households[p.household]
    if p.id in hh.members:
        hh.members.remove(p.id)
    if not hh.members and hh.id in w.occupancy.get(hh.home, []):
        w.occupancy[hh.home].remove(hh.id)


def _jobs(w: World, rng: np.random.Generator, alive: list[Person]) -> None:
    seekers = [p for p in alive if p.job is None and not p.retired and p.school is None and 18 <= p.age(w.t) < 65]
    if not seekers:
        return
    vac = w.vacancies()
    for p in seekers:
        if p.unemployed_since is None:
            p.unemployed_since = w.t
        if not vac or rng.random() > 0.25:  # a job search takes a few days
            continue
        home = w.city.buildings[w.households[p.household].home]
        near = sorted(set(b for b, _ in vac), key=lambda b: (math.hypot(w.city.buildings[b].x - home.x, w.city.buildings[b].y - home.y), b))[:5]
        b = near[int(rng.integers(len(near)))]
        w.hire(p, b)
        vac.remove(next(v for v in vac if v[0] == b))
        w.today.hired += 1
        w.emit("hired", f"{p.name} started work at {w.city.buildings[b].name}.", (p.id,), b)


def _romance(w: World, rng: np.random.Generator, alive: list[Person]) -> None:
    t = w.t
    for p in alive:
        if p.partner is not None or not 20 <= p.age(t) < 60 or rng.random() > 0.02:
            continue
        for q, strength in w.social.friends(p.id, 0.2):
            o = w.people[q]
            if o.partner is not None or not 20 <= o.age(t) < 60 or abs(o.age(t) - p.age(t)) > 10 or q in p.parents:
                continue
            if o.sex == p.sex and rng.random() > 0.05:
                continue
            diff = abs(p.openness - o.openness) + abs(p.conscientiousness - o.conscientiousness) + abs(p.agreeableness - o.agreeableness)
            if rng.random() < strength * (1.0 - diff / 3.0):
                make_couple(w, p, o)
                _move_in(w, rng, p, o)
                break


def _move_in(w: World, rng: np.random.Generator, a: Person, b: Person) -> None:
    """The partner with the smaller household joins the other, bringing their children."""
    ha, hb = w.households[a.household], w.households[b.household]
    if ha.id == hb.id:
        return
    mover, stay = (b, a) if len(hb.members) <= len(ha.members) else (a, b)
    src, dst = w.households[mover.household], w.households[stay.household]
    if len(dst.members) + len(src.members) > 7:
        return  # too crowded; they stay apart for now
    movers = [mover.id] + [c for c in mover.children if c in src.members and w.people[c].age(w.t) < 18]
    for pid in movers:
        p = w.people[pid]
        src.members.remove(pid)
        dst.members.append(pid)
        p.household = dst.id
    if not src.members and src.id in w.occupancy[src.home]:
        w.occupancy[src.home].remove(src.id)
    dst.has_car = dst.has_car or src.has_car
    w.emit("moved", f"{mover.name} moved in with {stay.name} at {w.city.buildings[dst.home].name}.", (mover.id, stay.id), dst.home)


def _births(w: World, rng: np.random.Generator, alive: list[Person]) -> None:
    t = w.t
    for mother in alive:
        if mother.sex != "F" or mother.partner is None:
            continue
        age = mother.age(t)
        if not 18 <= age < 45:
            continue
        father = w.people[mother.partner]
        hh = w.households[mother.household]
        crowding = 1.0 if len(hh.members) <= 4 else 0.4
        annual = 0.35 * math.exp(-(((age - 29.0) / 7.0) ** 2)) / (1.0 + 0.8 * len(mother.children)) * crowding
        if rng.random() < annual / DAYS_PER_YEAR:
            sex = "F" if rng.random() < 0.49 else "M"
            baby = w.new_person(sex=sex, born=t, household=hh.id, last=father.last if rng.random() < 0.8 else mother.last,
                                parents=(mother.id, father.id))
            baby.energy = 1.0
            w.today.births += 1
            w.emit("birth", f"{baby.name} was born to {mother.name} and {father.name}.", (baby.id, mother.id, father.id), hh.home)


def _leave_home(w: World, rng: np.random.Generator, alive: list[Person]) -> None:
    t = w.t
    for p in alive:
        if p.partner is not None or p.age(t) < 22 or not p.parents or p.job is None:
            continue
        hh = w.households[p.household]
        if not any(q in hh.members for q in p.parents) or rng.random() > 0.35 / DAYS_PER_YEAR * 4:
            continue
        home = w.free_home(rng, near=p.job.building)
        if home is None:
            return
        hh.members.remove(p.id)
        new = w.new_household(home, has_car=bool(rng.random() < 0.3))
        new.members.append(p.id)
        p.household = new.id
        w.emit("moved_out", f"{p.name} left the family home and moved to {w.city.buildings[home].name}.", (p.id,), home)


def _migration(w: World, rng: np.random.Generator) -> None:
    t = w.t
    alive = w.alive()
    seekers = sum(1 for p in alive if p.job is None and not p.retired and p.school is None and 18 <= p.age(t) < 65)
    open_jobs = len(w.vacancies())
    free_homes = sum(w.city.buildings[b].households - len(o) for b, o in w.occupancy.items())
    pull = max(0, open_jobs - seekers)
    n_households = min(int(free_homes * 0.25), int(rng.poisson(pull * 0.003)))
    residents = [p.id for p in alive if p.age(t) >= 18]
    for _ in range(n_households):
        anchor = w.social.pick_by_degree(rng, residents) if residents and rng.random() < 0.6 else None
        near = w.households[w.people[anchor].household].home if anchor is not None else None
        home = w.free_home(rng, near=near)
        if home is None:
            break
        hh = w.new_household(home, has_car=bool(rng.random() < 0.4))
        last = None
        a = 22 + int(rng.integers(0, 22))
        first = w.new_person(sex="F" if rng.random() < 0.5 else "M", born=t - a * MINUTES_PER_YEAR - int(rng.integers(MINUTES_PER_YEAR)), household=hh.id, last=last)
        members = [first]
        if rng.random() < 0.45:
            partner = w.new_person(sex="M" if first.sex == "F" else "F", born=first.born - int(rng.integers(-3, 4)) * MINUTES_PER_YEAR,
                                   household=hh.id, last=first.last)
            make_couple(w, first, partner, announce=False)
            members.append(partner)
            for _ in range(int(rng.integers(0, 3))):
                mother = first if first.sex == "F" else partner
                ca = float(rng.uniform(0, max(0.5, min(16.0, mother.age(t) - 20))))
                kid = w.new_person(sex="F" if rng.random() < 0.49 else "M", born=t - int(ca * MINUTES_PER_YEAR), household=hh.id,
                                   last=first.last, parents=(first.id, partner.id))
                members.append(kid)
        for m in members:
            m.skill = float(np.clip(rng.normal(0.45, 0.15), 0.05, 0.95))
            if 6 <= m.age(t) < 18:
                w.enrol(m)
            elif m.age(t) >= 18:
                m.unemployed_since = t
        if anchor is not None:
            w.social.tie(first.id, anchor, "friend", 0.5)
        w.today.arrived += len(members)
        names = ", ".join(m.name for m in members)
        why = f", following their friend {w.people[anchor].name}" if anchor is not None else ""
        w.emit("arrived", f"{names} moved to the city{why}.", tuple(m.id for m in members), home)

    # long-term unemployed households may give up and leave
    for hh in list(w.households.values()):
        adults = [w.people[q] for q in hh.members if w.people[q].age(t) >= 18 and not w.people[q].retired]
        if not adults or any(a.job for a in adults):
            continue
        if all(a.unemployed_since is not None and t - a.unemployed_since > 120 * MINUTES_PER_DAY for a in adults) and rng.random() < 0.3:
            leaving = list(hh.members)
            for q in leaving:
                p = w.people[q]
                p.alive = False  # gone from the city (not dead): the registry keeps them
                p.died = None
                w.unenrol(p)
                w.economy.close(p, "left")
                if p.partner is not None and p.partner not in leaving and p.partner in w.people:
                    w.people[p.partner].partner = None
                w.social.remove_person(q)
            hh.members.clear()
            if hh.id in w.occupancy[hh.home]:
                w.occupancy[hh.home].remove(hh.id)
            w.today.left += len(leaving)
            w.emit("left", f"The {w.people[leaving[0]].last} household ({len(leaving)} people) left the city to find work.", tuple(leaving))
