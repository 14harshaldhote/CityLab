"""The everyday brain of every citizen: a schedule plus utility AI.

Whenever a person finishes what they were doing, they look at what they could do
next and score each option:

    score = how much it helps their most pressing needs
            x their personality (an outgoing person values visits more)
            + obligations (a shift starting soon, a school day)
            + time of day and weather (no park in the rain at night)
            - the distance to get there
            + a little noise, so people are not robots

and they do the best one. This is *utility AI*, the technique behind The Sims: it is
cheap (microseconds per decision), explainable (every score can be printed) and
needs no language model. The schedule part is just obligations with strong scores:
a worker's shift and a pupil's school day win unless something is badly wrong.

**Learning from experience.** Nobody is born knowing which mess serves the best
thali. People weigh the two or three nearest places of each kind, and after each
visit they remember how it went: was the food good *for them*, was it packed,
did it cost more than they could spare, was the clinic quick and kind. That
memory (``likes``, from -1 to +1) tilts their next choice, so each person slowly
grows their own habits: a favourite restaurant, a park they avoid, the clinic
they trust. Curious, open people try new places more often. Friends pass on
tips too (see ``mind.py``), so a good clinic's name travels by word of mouth.
The same goes for getting about (``ways``): a long wait for a packed bus, or a
soaking on foot, makes the next trip by that way a little less likely.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np

from .clock import MINUTES_PER_DAY, SimTime
from .faith import FAITHS, FESTIVAL_SERVICE
from .health import CHECKUP, CLINIC_FEE, MEDICINES
from .rng import stable_hash
from .people import (
    EAT_HOME, EAT_OUT, HOME, HOSPITAL, JAIL, PARK, SCHOOL, SHOP, SLEEP, SOCIAL, TRAVEL, WORK, WORSHIP,
    Person, Plan, learn, urgency,
)

if TYPE_CHECKING:
    from .world import World

SCHOOL_START = 8 * 60
SCHOOL_END = 15 * 60
VISIT_KINDS = (WORK, SCHOOL, PARK, EAT_OUT, SHOP, SOCIAL, WORSHIP, HOSPITAL)
GOING_OUT = (EAT_OUT, SHOP, PARK, SOCIAL, WORSHIP)
TASTE = 0.7  # how much what they have learned about a place counts against how far it is
CHOICES = 3  # nearby places of each kind they weigh up


def fit(p: Person, place: int) -> float:
    """How well a place suits this one person (their own taste, -1..1): the same thali is perfect for one and bland for another."""
    return (stable_hash("fit", p.id, place) % 2001) / 1000.0 - 1.0


def is_workday(p: Person, day: int, weekdays_only: bool) -> bool:
    if weekdays_only:
        return (day + 3) % 7 < 5
    return (day + p.id) % 7 < 5  # shift workers get two rotating days off


def shift_window(p: Person, t: int) -> tuple[int, int] | None:
    """The shift instance this person should be heading to or working now, if any."""
    if p.job is None:
        return None
    s = p.job.shift
    day = t // MINUTES_PER_DAY
    for d in (day - 1, day):
        start = d * MINUTES_PER_DAY + s.start
        end = start + s.length
        if start - 90 <= t < end - 45 and p.last_shift != start and is_workday(p, d, s.weekdays_only):
            return start, end
    return None


def next_obligation(p: Person, t: int) -> int | None:
    """Absolute minute of the next shift or school start within ~20 hours."""
    day = t // MINUTES_PER_DAY
    best = None
    for d in (day, day + 1):
        if p.job is not None and is_workday(p, d, p.job.shift.weekdays_only):
            start = d * MINUTES_PER_DAY + p.job.shift.start
            if start > t and (best is None or start < best):
                best = start
        if p.school is not None and (d + 3) % 7 < 5:
            start = d * MINUTES_PER_DAY + SCHOOL_START
            if start > t and (best is None or start < best):
                best = start
    return best


class Brain:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("brain")
        self._noise = np.empty(0)
        self._k = 0
        self._far_cache: dict[tuple[int, int], float] = {}
        self._near: dict[tuple[int, str, int], list[tuple[int, float]]] = {}

    # snapshots leave out the distance cache: it refills itself
    def __getstate__(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k not in ("_far_cache", "_near")}

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._far_cache, self._near = {}, {}

    def _gumbel(self, n: int) -> np.ndarray:
        """Taste noise for ``n`` options, drawn in big batches (one numpy call per few thousand choices)."""
        if self._k + n > len(self._noise):
            self._noise = self.rng.gumbel(0.0, 0.12, 8192)
            self._k = 0
        self._k += n
        return self._noise[self._k - n:self._k]

    def options(self, p: Person, t: int) -> list[tuple[float, int, int, int]] | tuple[int, int, int]:
        """Everything this person could do next, each with its score before the noise of taste.

        Nothing in the city changes: they only think it over. (A small child's day is decided by
        the family, and comes back as a single plan.)
        """
        w = self.w
        hh = w.households[p.household]
        home = hh.home
        st = SimTime(t)
        hour = st.hour
        night = hour >= 22 or hour < 6
        age = p.age(t)

        if age < 6:  # small children stay home; the family feeds and plays with them
            p.hunger, p.social, p.fun = max(p.hunger, 0.85), max(p.social, 0.8), max(p.fun, 0.8)
            if hour >= 20 or hour < 7:
                wake = (t // MINUTES_PER_DAY + (1 if hour >= 20 else 0)) * MINUTES_PER_DAY + 7 * 60
                return SLEEP, home, wake
            return HOME, home, t + 120 if hour < 18 else (t // MINUTES_PER_DAY) * MINUTES_PER_DAY + 20 * 60

        here = p.place if p.place is not None else home
        wx = w.weather.at(t)
        options: list[tuple[float, int, int, int]] = []  # score, activity, place, until

        # obligations
        win = shift_window(p, t)
        if win is not None:
            options.append((4.0 + p.conscientiousness, WORK, p.job.building, win[1]))
        elif p.trade:  # their own trade: the vegetable cart, the homes they clean, the labour naka
            trade = w.informal.option(p, t)
            if trade is not None:
                options.append(trade)
        day = st.day
        if p.school is not None and not st.is_weekend and p.last_school_day != day:
            s0 = day * MINUTES_PER_DAY + SCHOOL_START
            s1 = day * MINUTES_PER_DAY + SCHOOL_END
            if s0 - 60 <= t < s1 - 60:
                options.append((4.5 + 0.5 * p.conscientiousness, SCHOOL, p.school, s1))

        # sleep, capped so they wake in time for the next obligation
        sleep_need = urgency(p.energy) * 1.5 + (1.6 if night else -1.4 if 7 <= hour < 21.5 else 0.0)
        wake = t + max(60, int((1.0 - p.energy) * 640) + 30 + int(60 * (0.5 - p.conscientiousness)))
        nxt = next_obligation(p, t)
        if nxt is not None and nxt - 75 > t + 60:
            wake = min(wake, nxt - 75)
        options.append((sleep_need, SLEEP, home, wake))

        options.append((urgency(p.hunger) * 2.4, EAT_HOME, home, t + 30))
        options.append((0.35 + urgency(p.fun) * 0.6 + (0.4 if wx.dark else 0.0), HOME, home, t + 90))

        adult = age >= 18
        if adult:
            if w.economy.can_afford(p, w.economy.meal_price()):
                evening = 0.3 if 19 <= hour < 22 else 0.0
                base = urgency(p.hunger) * 2.2 + 0.3 * p.extraversion + evening
                options += [(base + pull, EAT_OUT, r, t + 50) for r, pull in self._places(p, here, "restaurant", t, CHOICES)]
            if w.economy.can_afford(p, 300.0):
                base = urgency(p.fun) * 1.0 + 0.2
                options += [(base + pull, SHOP, s, t + 40) for s, pull in self._places(p, here, "shop", t, CHOICES)]

        if not night or adult and hour < 23:
            friends = w.social.top_friends(p.id, 3, 0.2)
            if friends:
                f = friends[int(self.rng.integers(len(friends)))][0]
                fhome = w.households[w.people[f].household].home
                late = 0.8 if hour >= 22 or hour < 7 else 0.0
                options.append(
                    (urgency(p.social) * 2.0 * (0.6 + p.extraversion) - late - self._far(here, fhome), SOCIAL, fhome, t + 90 + int(self.rng.integers(60)))
                )

        score = urgency(p.fun) * 1.6 * (0.5 + p.openness)
        if wx.raining:
            score *= 0.3
        if wx.dark:
            score *= 0.3
        for pk, pull in self._places(p, here, "park", t, 2):
            options.append((score + pull, PARK, pk, t + 60 + int(self.rng.integers(60))))

        worship = self._worship(p, st, here, t)
        if worship is not None:
            options.append(worship)

        # feeling ill: see a doctor if it calls for one, and rest rather than work
        if p.illness is not None:
            # clinics and the hospital's outpatient department open at nine; a serious case goes to casualty earlier
            if w.health.needs_doctor(p) and (9 <= hour < 21 or p.severity == 3 and 7 <= hour < 23):
                options += self._doctors(p, here, t, age)
            if p.severity >= 2 or p.illness != CHECKUP:
                options = [self._sick(p, o) for o in options]
        # feelings tilt the choice: the sad seek company or comfort, the joyful go out, the anxious stay in after dark
        cheer = 0.4 * (p.joy - 0.4)
        lift = {SOCIAL: 0.6 * p.sadness + cheer, WORSHIP: 0.6 * p.sadness, EAT_OUT: cheer, PARK: cheer, SHOP: cheer}
        if wx.dark:
            for act in GOING_OUT:
                lift[act] -= 0.8 * p.fear
        return [(s + lift.get(a, 0.0), a, pl, u) for s, a, pl, u in options]

    def decide(self, p: Person, t: int) -> None:
        w = self.w
        p.update_needs(t)
        if p.pending is not None:  # just arrived: start what they came for
            plan = p.pending
            p.pending = None
            p.trip = None
            self._start(p, plan.activity, plan.place, max(t + 10, plan.until), t)
            return
        if p.jailed_until > t:  # serving a sentence
            p.activity, p.until = JAIL, p.jailed_until
            w.schedule(p)
            return
        if p.activity == JAIL:
            w.emit("released", f"{p.name} was released from jail and went home.", (p.id,))
        options = self.options(p, t)
        if isinstance(options, tuple):  # a small child: the family decided
            activity, place, until = options
            self._go(p, activity, place, until, t)
            return
        noise = self._gumbel(len(options)).tolist()
        best = max(zip(options, noise), key=lambda on: on[0][0] + on[1])[0]
        _, activity, place, until = best
        day = SimTime(t).day
        if activity == WORK:
            win = shift_window(p, t) if p.job is not None else None
            if win is not None:
                p.last_shift = win[0]
            p.worked_day = day
        elif activity == SCHOOL:
            p.last_school_day = day
        self._go(p, activity, place, until, t)

    @staticmethod
    def _sick(p: Person, o: tuple[float, int, int, int]) -> tuple[float, int, int, int]:
        score, act, place, until = o
        if act in (WORK, SCHOOL):
            score *= 0.15 if p.severity >= 2 else 0.7
        elif act in (SLEEP, HOME):
            score += 0.4 * p.severity
        elif act in GOING_OUT:
            score -= 0.3 * p.severity
        return score, act, place, until

    def _worship(self, p: Person, st: SimTime, here: int, t: int) -> tuple[float, int, int, int] | None:
        """A visit to their place of worship, if a service is on now and they have not been to it yet."""
        faith = FAITHS[p.religion]
        if faith.place is None or p.devotion <= 0:
            return None
        services = faith.services
        festival = self.w.festival is not None and self.w.festival[0] == p.religion
        if festival:
            services = (FESTIVAL_SERVICE,) + services
        mod, wd = st.minute_of_day, st.weekday
        for svc in services:
            if svc.weekday is not None and svc.weekday != wd or not svc.start <= mod < svc.end:
                continue
            if p.last_worship >= st.day * MINUTES_PER_DAY + svc.start:
                continue  # already went during this service
            place = self.w.nearest_open(here, faith.place, t)
            if place is None:
                return None
            # weekly prayers and festivals draw people whenever they come; daily visits wait a day
            weekly = svc.weekday is not None or svc is FESTIVAL_SERVICE
            recency = 1.0 if weekly else min(1.0, (t - p.last_worship) / (22 * 60))
            score = svc.weight * 1.8 * p.devotion**2 * recency - self._far(here, place)
            return score, WORSHIP, place, t + svc.stay + int(self.rng.integers(15))
        return None

    def _places(self, p: Person, here: int, kind: str, t: int, k: int) -> list[tuple[int, float]]:
        """The ``k`` nearest open places of a kind, each with its pull: what they think of it, less the walk."""
        if not self.w._kind_open(kind, t):
            return []
        key = (here, kind, k)
        near = self._near.get(key)
        if near is None:
            near = self._near[key] = [(b, self._far(here, b)) for b in self.w.open_nearby(here, kind, t, k)]
        likes, untried = p.likes, 0.25 * (p.openness - 0.5)
        return [(b, (TASTE * likes[b] if b in likes else untried) - far) for b, far in near]

    def _taste(self, p: Person, place: int) -> float:
        """What they have learned about a place; somewhere new is a small adventure for the curious."""
        like = p.likes.get(place)
        if like is None:
            return 0.25 * (p.openness - 0.5)
        return TASTE * like

    def _doctors(self, p: Person, here: int, t: int, age: float) -> list[tuple[float, int, int, int]]:
        """Where to see a doctor: the free Civil Hospital, with its queue, or a private clinic that charges.

        Most town families who can pay go private for everyday illness, as in India, where about
        three in four doctor visits in towns are to private doctors (NSS 75th round). Those who
        can't afford the fee, or trust the hospital, go to the Civil Hospital.
        """
        w = self.w
        out = []
        urgent = 5.0 + p.severity
        hosp = w.nearest_open(here, "hospital", t)
        if hosp is not None:
            score = urgent - 0.7 + 0.6 * p.opinions.get("hospital", 0.0) + self._taste(p, hosp) - self._far(here, hosp)
            out.append((score, HOSPITAL, hosp, t + 60))
        payer = w.transport._payer(p, age)
        fee = CLINIC_FEE + MEDICINES[max(1, p.severity)]
        if payer is not None and w.economy.can_afford(payer, fee + 1000.0):
            # the fee hurts less the more the family has put by (a month's spare money, roughly)
            savings = w.economy.balance[w.economy.person(payer.id)]
            pain = 1.5 * fee / (fee + savings / 30.0)
            out += [(urgent - pain + pull, HOSPITAL, c, t + 40) for c, pull in self._places(p, here, "clinic", t, 2)]
        return out

    def _far(self, a: int, b: int) -> float:
        """How much the distance puts them off (buildings never move, so each pair is worked out once)."""
        key = (a, b)
        far = self._far_cache.get(key)
        if far is None:
            ba, bb = self.w.city.buildings[a], self.w.city.buildings[b]
            far = self._far_cache[key] = 1.3 * math.hypot(ba.x - bb.x, ba.y - bb.y) / 4000.0
        return far

    def _remember(self, p: Person, activity: int, place: int, t: int) -> None:
        """How did it go? A good meal, a packed shop, a park in the rain: it shapes the next choice."""
        w = self.w
        quality = (stable_hash("quality", w.seed, place) % 1001) / 500.0 - 1.0  # some places are simply better run
        crowd = len(w.visits.get(place, ())) / (40.0 if activity == PARK else 25.0)
        how = 0.45 * quality + 0.45 * fit(p, place) - 0.4 * max(0.0, crowd - 0.6)
        if activity == PARK and w.weather.at(t).raining:
            how -= 0.5
        if activity in (EAT_OUT, SHOP) and w.economy.balance[w.economy.person(p.id)] < 2000:
            how -= 0.2  # it was more than they could really spare
        how += float(self.rng.normal(0.0, 0.25))  # a good day or an off day
        learn(p.likes, place, how)

    def _go(self, p: Person, activity: int, place: int, until: int, t: int) -> None:
        if p.place == place:
            self._start(p, activity, place, until, t)
            return
        w = self.w
        src = w.city.buildings[p.place if p.place is not None else w.households[p.household].home]
        trip = w.transport.plan(p, src, w.city.buildings[place], t, activity if activity in (WORK, SCHOOL) else None)
        p.trip = trip
        p.pending = Plan(activity, place, until)
        p.activity = TRAVEL
        p.place = None
        p.until = trip.arrive
        w.schedule(p)

    def _start(self, p: Person, activity: int, place: int, until: int, t: int) -> None:
        if activity == HOSPITAL:
            until = self.w.health.consult(p, place, t)
        p.activity = activity
        p.place = place
        p.until = max(until, t + 5)
        if activity in VISIT_KINDS:
            self.w.visits.setdefault(place, []).append(p.id)
        econ = self.w.economy
        if activity in (EAT_OUT, SHOP, PARK):
            self._remember(p, activity, place, t)
        if activity == WORK and p.job is None:
            self.w.informal.start(p, place, t)
        elif activity == WORK:
            econ.attendance[place].append(p.id)
            if t > p.last_shift + 5 and p.last_shift >= 0 and p.trip is None and p.job is not None and p.job.building == place:
                self.w.transport.late_for_work()
                if p.last_mode:  # late again: maybe there's a better way to get here
                    learn(p.ways, p.last_mode, -0.6, 0.2)
        elif activity == EAT_OUT:
            econ.purchase(p, place, econ.meal_price(), "meals out")
        elif activity == SHOP:
            econ.purchase(p, place, econ.shopping_price(), "shopping")
        elif activity == WORSHIP:
            p.last_worship = t
            econ.offering(p, place)
            if self.w.city.buildings[place].kind == "gurudwara":  # langar: a free meal for everyone who comes
                p.hunger = max(p.hunger, 0.9)
                econ.langar(place)
        self.w.schedule(p)
