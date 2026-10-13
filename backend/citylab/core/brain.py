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
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from .clock import MINUTES_PER_DAY, SimTime
from .faith import FAITHS, FESTIVAL_SERVICE
from .people import (
    EAT_HOME, EAT_OUT, HOME, PARK, SCHOOL, SHOP, SLEEP, SOCIAL, TRAVEL, WORK, WORSHIP,
    Person, Plan, urgency,
)

if TYPE_CHECKING:
    from .world import World

SCHOOL_START = 8 * 60
SCHOOL_END = 15 * 60
VISIT_KINDS = (WORK, SCHOOL, PARK, EAT_OUT, SHOP, SOCIAL, WORSHIP)


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

    def decide(self, p: Person, t: int) -> None:
        w = self.w
        p.update_needs(t)
        if p.pending is not None:  # just arrived: start what they came for
            plan = p.pending
            p.pending = None
            p.trip = None
            self._start(p, plan.activity, plan.place, max(t + 10, plan.until), t)
            return

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
                self._go(p, SLEEP, home, wake, t)
            else:
                self._go(p, HOME, home, t + 120 if hour < 18 else (t // MINUTES_PER_DAY) * MINUTES_PER_DAY + 20 * 60, t)
            return

        here = p.place if p.place is not None else home
        wx = w.weather.at(t)
        options: list[tuple[float, int, int, int]] = []  # score, activity, place, until

        # obligations
        win = shift_window(p, t)
        if win is not None:
            options.append((4.0 + p.conscientiousness, WORK, p.job.building, win[1]))
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
            r = w.nearest_open(here, "restaurant", t)
            if r is not None and w.economy.can_afford(p, w.economy.meal_price()):
                evening = 0.3 if 19 <= hour < 22 else 0.0
                options.append((urgency(p.hunger) * 2.2 + 0.3 * p.extraversion + evening - self._far(here, r), EAT_OUT, r, t + 50))
            s = w.nearest_open(here, "shop", t)
            if s is not None and w.economy.can_afford(p, 60.0):
                options.append((urgency(p.fun) * 1.0 + 0.2 - self._far(here, s), SHOP, s, t + 40))

        if not night or adult and hour < 23:
            friends = w.social.top_friends(p.id, 3, 0.2)
            if friends:
                f = friends[int(self.rng.integers(len(friends)))][0]
                fhome = w.households[w.people[f].household].home
                late = 0.8 if hour >= 22 or hour < 7 else 0.0
                options.append(
                    (urgency(p.social) * 2.0 * (0.6 + p.extraversion) - late - self._far(here, fhome), SOCIAL, fhome, t + 90 + int(self.rng.integers(60)))
                )

        pk = w.nearest_open(here, "park", t)
        if pk is not None:
            score = urgency(p.fun) * 1.6 * (0.5 + p.openness)
            if wx.raining:
                score *= 0.3
            if wx.dark:
                score *= 0.3
            options.append((score - self._far(here, pk), PARK, pk, t + 60 + int(self.rng.integers(60))))

        worship = self._worship(p, st, here, t)
        if worship is not None:
            options.append(worship)

        noise = self.rng.gumbel(0.0, 0.12, len(options))
        best = options[max(range(len(options)), key=lambda i: options[i][0] + noise[i])]
        _, activity, place, until = best
        if activity == WORK:
            p.last_shift = win[0]
        elif activity == SCHOOL:
            p.last_school_day = day
        self._go(p, activity, place, until, t)

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

    def _far(self, a: int, b: int) -> float:
        if a == b:
            return 0.0
        ba, bb = self.w.city.buildings[a], self.w.city.buildings[b]
        return 1.3 * math.hypot(ba.x - bb.x, ba.y - bb.y) / 4000.0

    def _go(self, p: Person, activity: int, place: int, until: int, t: int) -> None:
        if p.place == place:
            self._start(p, activity, place, until, t)
            return
        w = self.w
        src = w.city.buildings[p.place if p.place is not None else w.households[p.household].home]
        trip = w.router.trip(src, w.city.buildings[place], t, w.households[p.household].has_car)
        p.trip = trip
        p.pending = Plan(activity, place, until)
        p.activity = TRAVEL
        p.place = None
        p.until = trip.arrive
        w.schedule(p)

    def _start(self, p: Person, activity: int, place: int, until: int, t: int) -> None:
        p.activity = activity
        p.place = place
        p.until = max(until, t + 5)
        if activity in VISIT_KINDS:
            self.w.visits.setdefault(place, []).append(p.id)
        econ = self.w.economy
        if activity == WORK:
            econ.attendance[place].append(p.id)
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
