"""The world: one object that owns the whole city and moves it forward in time.

``World.advance(minutes)`` is the tick loop. Instead of asking every person every
minute what they are doing, each person sits in a priority queue keyed by the minute
their current activity ends. A tick pops only the people whose activity just ended
and lets them decide again. A city of thousands therefore costs a few thousand
decisions per simulated day, not millions, and positions between decisions are
interpolated along the planned route, never stepped.
"""

from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np

from . import lifecycle
from .brain import Brain
from .citygen import City, generate_city
from .clock import MINUTES_PER_DAY, MINUTES_PER_HOUR, MINUTES_PER_YEAR, SimTime
from .economy import Economy
from .events import Event, EventBus
from .names import FEMALE, MALE, SURNAMES
from .people import ACTIVITY_NAMES, SLEEP, TRAVEL, Household, Job, Person
from .rng import Streams, stable_hash
from .routing import Router
from .social import SocialGraph
from .weather import Weather


class World:
    def __init__(self, seed: int = 1, population: int = 2000, *, city: City | None = None) -> None:
        self.seed = seed
        self.streams = Streams(seed)
        self.city = city or generate_city(seed)
        self.router = Router(self.city)
        self.weather = Weather(seed)
        self.bus = EventBus()
        self.social = SocialGraph()
        self.people: dict[int, Person] = {}
        self.households: dict[int, Household] = {}
        self.occupancy: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.kind == "home"}
        self.job_holders: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.jobs}
        self.pupils: dict[int, list[int]] = {b.id: [] for b in self.city.buildings if b.kind == "school"}
        self.visits: dict[int, list[int]] = {}
        self.t = 0
        self._queue: list[tuple[int, int]] = []
        self._next_pid = 0
        self._next_hh = 0
        self.daily: list[dict[str, Any]] = []  # one row of statistics per simulated day
        self.today = lifecycle.DayCounts()
        self._by_kind = {k: [b for b in self.city.buildings if b.kind == k] for k in ("restaurant", "shop", "park", "school")}
        self._near_cache: dict[tuple[int, str], list] = {}
        self.brain = Brain(self)
        self.economy = Economy(self)
        self._founded = False
        self._populate(population)
        self.economy.found()
        self._founded = True

    # ---- time -------------------------------------------------------------------------

    @property
    def now(self) -> SimTime:
        return SimTime(self.t)

    def schedule(self, p: Person) -> None:
        heapq.heappush(self._queue, (p.until, p.id))

    def advance(self, minutes: int) -> None:
        end = self.t + int(minutes)
        q = self._queue
        while self.t < end:
            self.t += 1
            t = self.t
            if t % MINUTES_PER_DAY == 0:
                lifecycle.end_of_day(self)
            while q and q[0][0] <= t:
                until, pid = heapq.heappop(q)
                p = self.people.get(pid)
                if p is None or not p.alive or p.until != until:
                    continue  # stale entry: they died, left, or were rescheduled
                self.brain.decide(p, t)

    # ---- events ---------------------------------------------------------------------

    def emit(self, kind: str, text: str, people: tuple[int, ...] = (), place: int | None = None, **data: Any) -> Event:
        return self.bus.publish(Event(t=self.t, kind=kind, text=text, people=people, place=place, data=data))

    # ---- people -----------------------------------------------------------------------

    def new_person(
        self, *, sex: str, born: int, household: int, last: str | None = None, parents: tuple[int, ...] = (), first: str | None = None
    ) -> Person:
        rng = self.streams("people")
        pid = self._next_pid
        self._next_pid += 1
        if first is None:
            first = str(rng.choice(FEMALE if sex == "F" else MALE))
        traits = np.clip(rng.normal(0.5, 0.18, 5), 0.02, 0.98)
        # children take after their parents a little
        if parents:
            mean = np.mean([[self.people[q].openness, self.people[q].conscientiousness, self.people[q].extraversion,
                             self.people[q].agreeableness, self.people[q].neuroticism] for q in parents], axis=0)
            traits = np.clip(0.5 * traits + 0.5 * mean + rng.normal(0, 0.05, 5), 0.02, 0.98)
        p = Person(
            id=pid, first=first, last=last or str(rng.choice(SURNAMES)), sex=sex, born=born, household=household,
            openness=float(traits[0]), conscientiousness=float(traits[1]), extraversion=float(traits[2]),
            agreeableness=float(traits[3]), neuroticism=float(traits[4]), parents=parents, arrived=self.t,
        )
        p.hunger, p.energy, p.social, p.fun = (float(v) for v in rng.uniform(0.5, 0.95, 4))
        p.needs_t = self.t
        p.place = self.households[household].home
        p.until = self.t + int(rng.integers(1, 60))
        self.people[pid] = p
        self.households[household].members.append(pid)
        self.social.add_person(pid)
        for q in parents:
            self.people[q].children.append(pid)
            self.social.tie(pid, q, "parent")
            for sib in self.people[q].children:
                if sib != pid:
                    self.social.tie(pid, sib, "sibling")
        self.schedule(p)
        if self._founded:
            self.economy.open(p)
        return p

    def new_household(self, home: int, has_car: bool) -> Household:
        hh = Household(id=self._next_hh, home=home, members=[], has_car=has_car)
        self._next_hh += 1
        self.households[hh.id] = hh
        self.occupancy[home].append(hh.id)
        return hh

    def free_home(self, rng: np.random.Generator, near: int | None = None) -> int | None:
        free = [b for b, occ in self.occupancy.items() if len(occ) < self.city.buildings[b].households]
        if not free:
            return None
        if near is not None:
            nb = self.city.buildings[near]
            free.sort(key=lambda b: math.hypot(self.city.buildings[b].x - nb.x, self.city.buildings[b].y - nb.y))
            return free[int(rng.integers(min(5, len(free))))]
        return free[int(rng.integers(len(free)))]

    def alive(self) -> list[Person]:
        return [p for p in self.people.values() if p.alive]

    # ---- jobs and schools ---------------------------------------------------------------

    def vacancies(self) -> list[tuple[int, int]]:
        """(building, slot index) for every unfilled job."""
        out = []
        for b, holders in self.job_holders.items():
            for k in range(len(holders), len(self.city.buildings[b].jobs)):
                out.append((b, k))
        return out

    def hire(self, p: Person, building: int) -> None:
        b = self.city.buildings[building]
        slot = len(self.job_holders[building])
        shift = b.jobs[slot % len(b.jobs)]
        wage = b.type.wage * (0.8 + 0.6 * p.skill)
        p.job = Job(building=building, shift=shift, wage=round(wage, 2), since=self.t)
        p.unemployed_since = None
        self.job_holders[building].append(p.id)

    def fire(self, p: Person) -> None:
        if p.job is not None:
            holders = self.job_holders[p.job.building]
            if p.id in holders:
                holders.remove(p.id)
            p.job = None

    def enrol(self, p: Person) -> bool:
        home = self.city.buildings[self.households[p.household].home]
        schools = sorted(
            self._by_kind["school"],
            key=lambda s: (len(self.pupils[s.id]) >= s.students, math.hypot(s.x - home.x, s.y - home.y), s.id),
        )
        if not schools:
            return False
        p.school = schools[0].id
        self.pupils[p.school].append(p.id)
        return True

    def unenrol(self, p: Person) -> None:
        if p.school is not None:
            if p.id in self.pupils[p.school]:
                self.pupils[p.school].remove(p.id)
            p.school = None

    # ---- places -----------------------------------------------------------------------------

    def nearest_open(self, here: int, kind: str, t: int) -> int | None:
        st = SimTime(t)
        mod, weekend = st.minute_of_day, st.is_weekend
        for b in self._nearby(here, kind):
            if b.is_open(mod, weekend):
                return b.id
        return None

    def _nearby(self, here: int, kind: str) -> list:
        key = (here, kind)
        hit = self._near_cache.get(key)
        if hit is None:
            b0 = self.city.buildings[here]
            hit = sorted(self._by_kind[kind], key=lambda b: ((b.x - b0.x) ** 2 + (b.y - b0.y) ** 2, b.id))[:6]
            self._near_cache[key] = hit
        return hit

    # ---- founding population ----------------------------------------------------------------

    def _populate(self, target: int) -> None:
        rng = self.streams("founding")
        slots = [b for b, cap in ((b.id, b.households) for b in self.city.buildings if b.kind == "home") for _ in range(cap)]
        order = [slots[i] for i in rng.permutation(len(slots))]
        Y = MINUTES_PER_YEAR

        def born(age: float) -> int:
            return -int(age * Y) - int(rng.integers(0, Y))

        made = 0
        for home in order:
            if made >= target:
                break
            hh = self.new_household(home, has_car=bool(rng.random() < 0.45))
            last = str(rng.choice(SURNAMES))
            kind = rng.choice(["single", "couple", "family", "single_parent", "seniors"], p=[0.2, 0.22, 0.38, 0.07, 0.13])
            adults: list[Person] = []
            if kind == "seniors":
                a = 65 + rng.integers(0, 22)
                adults.append(self.new_person(sex="F", born=born(a), household=hh.id, last=last))
                if rng.random() < 0.7:
                    adults.append(self.new_person(sex="M", born=born(a + rng.integers(-3, 5)), household=hh.id, last=last))
            else:
                a = 21 + rng.integers(0, 40) if kind != "family" else 27 + rng.integers(0, 22)
                first_sex = "F" if kind in ("family", "single_parent") or rng.random() < 0.5 else "M"
                adults.append(self.new_person(sex=first_sex, born=born(a), household=hh.id, last=last))
                if kind in ("couple", "family"):
                    other = "M" if rng.random() < 0.95 else first_sex
                    adults.append(self.new_person(sex=other, born=born(max(20, a + rng.integers(-4, 6))), household=hh.id, last=last))
            if len(adults) == 2:
                lifecycle.make_couple(self, adults[0], adults[1], announce=False)
            if kind in ("family", "single_parent"):
                mother_age = adults[0].age(0)
                for _ in range(int(rng.integers(1, 4))):
                    child_age = float(rng.uniform(0, max(0.5, min(17.9, mother_age - 20))))
                    self.new_person(sex="F" if rng.random() < 0.49 else "M", born=born(child_age), household=hh.id,
                                    last=last, parents=tuple(q.id for q in adults))
            made += len(hh.members)

        # skills, schools, jobs, retirement
        vac = self.vacancies()
        vac_order = [vac[i] for i in rng.permutation(len(vac))]
        for p in self.alive():
            age = p.age(0)
            p.skill = float(np.clip(rng.normal(0.25 + min(age, 45) / 90.0, 0.12), 0.05, 0.95))
            if 6 <= age < 18:
                self.enrol(p)
            elif age >= 65:
                p.retired = True
            elif age >= 18 and rng.random() < 0.9 and vac_order:
                home = self.city.buildings[self.households[p.household].home]
                # take one of the nearer open jobs, as people tend to
                sample = vac_order[: 25]
                sample.sort(key=lambda bk: (math.hypot(self.city.buildings[bk[0]].x - home.x, self.city.buildings[bk[0]].y - home.y), bk))
                pick = sample[int(rng.integers(min(4, len(sample))))]
                vac_order.remove(pick)
                self.hire(p, pick[0])
            elif age >= 18:
                p.unemployed_since = 0

        # a starting web of acquaintances: coworkers, classmates and neighbours
        groups: dict[str, list[int]] = {}
        for p in self.alive():
            if p.job:
                groups.setdefault(f"w{p.job.building}", []).append(p.id)
            if p.school is not None:
                groups.setdefault(f"s{p.school}", []).append(p.id)
            if p.age(0) >= 14:
                groups.setdefault(f"h{self.households[p.household].home}", []).append(p.id)
        for key in sorted(groups):
            members = groups[key]
            for pid in members:
                for q in rng.choice(members, size=min(3, len(members)), replace=False):
                    if int(q) != pid:
                        self.social.tie(pid, int(q), "friend", float(rng.uniform(0.1, 0.6)))
        # everyone starts the first night asleep at home
        for p in self.alive():
            p.activity = SLEEP
        self.emit("founded", f"The city was founded with {len(self.alive())} people in {len(self.households)} households.",
                  data={"population": len(self.alive()), "households": len(self.households)})

    # ---- views for the API ------------------------------------------------------------------

    def position(self, p: Person) -> tuple[float, float]:
        if p.activity == TRAVEL and p.trip is not None:
            return p.trip.position(self.t)
        b = self.city.buildings[p.place if p.place is not None else self.households[p.household].home]
        # spread people inside their building so they do not stack on one pixel
        h = stable_hash(p.id, b.id)
        return b.x + 4 + (h % 997) / 997 * max(1.0, b.w - 8), b.y + 4 + (h // 997 % 991) / 991 * max(1.0, b.h - 8)

    def frame(self) -> dict[str, Any]:
        alive = self.alive()
        ids, xs, ys, acts, ages = [], [], [], [], []
        for p in alive:
            x, y = self.position(p)
            ids.append(p.id)
            xs.append(round(x, 1))
            ys.append(round(y, 1))
            acts.append(p.activity)
            ages.append(int(p.age(self.t)))
        st = self.now
        return {
            "t": self.t,
            "label": st.label(),
            "day": st.day,
            "minute_of_day": st.minute_of_day,
            "weather": self.weather.at(self.t).to_dict(),
            "ids": ids,
            "x": xs,
            "y": ys,
            "activity": acts,
            "age": ages,
            "counts": {ACTIVITY_NAMES[k]: acts.count(k) for k in range(len(ACTIVITY_NAMES))},
        }

    def person_card(self, pid: int) -> dict[str, Any]:
        p = self.people[pid]
        t = self.t
        hh = self.households[p.household]
        def ref(q: int | None) -> dict[str, Any] | None:
            if q is None or q not in self.people:
                return None
            o = self.people[q]
            return {"id": o.id, "name": o.name, "age": int(o.age(t if o.alive else o.died or t)), "alive": o.alive}

        p.update_needs(t) if p.alive else None
        job = None
        if p.job:
            b = self.city.buildings[p.job.building]
            s = p.job.shift
            job = {"building": b.id, "place": b.name, "kind": b.kind, "wage_per_day": p.job.wage,
                   "shift": f"{s.start // 60:02d}:{s.start % 60:02d}-{s.end // 60:02d}:{s.end % 60:02d}",
                   "since_day": p.job.since // MINUTES_PER_DAY}
        friends = [{"id": q, "name": self.people[q].name, "strength": round(w, 2)} for q, w in self.social.friends(pid)[:12]]
        return {
            "id": p.id,
            "name": p.name,
            "sex": p.sex,
            "age": round(p.age(t if p.alive else p.died or t), 1),
            "stage": p.stage(t),
            "alive": p.alive,
            "home": {"building": hh.home, "name": self.city.buildings[hh.home].name, "district": self.city.buildings[hh.home].district},
            "household": [ref(q) for q in hh.members if q != pid],
            "partner": ref(p.partner),
            "parents": [ref(q) for q in p.parents],
            "children": [ref(q) for q in p.children],
            "job": job,
            "school": self.city.buildings[p.school].name if p.school is not None else None,
            "retired": p.retired,
            "unemployed": p.unemployed_since is not None,
            "personality": {"openness": round(p.openness, 2), "conscientiousness": round(p.conscientiousness, 2),
                            "extraversion": round(p.extraversion, 2), "agreeableness": round(p.agreeableness, 2),
                            "neuroticism": round(p.neuroticism, 2)},
            "needs": {"hunger": round(p.hunger, 2), "energy": round(p.energy, 2), "social": round(p.social, 2), "fun": round(p.fun, 2)},
            "mood": round(p.mood, 2),
            "health": round(p.health, 2),
            "skill": round(p.skill, 2),
            "activity": ACTIVITY_NAMES[p.activity],
            "place": self.city.buildings[p.place].name if p.place is not None else None,
            "heading_to": self.city.buildings[p.pending.place].name if p.pending else None,
            "until": SimTime(p.until).label() if p.alive else None,
            "friends": friends,
            "friend_count": len(self.social.friends(pid)),
            "money": self.economy.person_view(pid),
        }

    def summary(self) -> dict[str, Any]:
        alive = self.alive()
        t = self.t
        working_age = [p for p in alive if 18 <= p.age(t) < 65 and p.school is None]
        employed = sum(1 for p in working_age if p.job)
        return {
            "t": t,
            "label": self.now.label(),
            "population": len(alive),
            "households": sum(1 for h in self.households.values() if h.members),
            "employed": employed,
            "unemployed": sum(1 for p in working_age if p.unemployed_since is not None),
            "pupils": sum(1 for p in alive if p.school is not None),
            "retired": sum(1 for p in alive if p.retired),
            "couples": sum(1 for p in alive if p.partner is not None) // 2,
            "vacancies": len(self.vacancies()),
            "free_homes": sum(self.city.buildings[b].households - len(o) for b, o in self.occupancy.items()),
            "social": self.social.summary(),
            "events": self.bus.count,
            "hours_simulated": t // MINUTES_PER_HOUR,
        }
