"""Inner lives: feelings, opinions of their own, and a reputation.

**Feelings.** Everyone carries four feelings between 0 and 1: joy, sadness, anger
and fear. Things that happen to them move those feelings (a new job brings joy, a
lay-off brings sadness, anger and worry, a burglary brings fear), and every night
they drift back towards that person's own resting point, which comes from their
personality: an outgoing person's resting joy is higher, a nervous person's fear
is higher. Feelings change what people do next (see ``brain.py``): someone sad
seeks out friends or their place of worship, someone joyful goes out more,
someone afraid stays in after dark.

**Opinions.** Everyone has their own view, from -1 (very unhappy) to +1 (very
happy), of six things: taxes, the police, the hospital, the buses, jobs and the
city council. Views are formed first from what happened to *them*: their own
check-up at the hospital, a theft on their street, being late because the bus
was slow, paying tax while a friend is paid cash in hand. Then friends talk, and
views spread along friendships. How much someone is swayed is their own: open,
less agreeable people think more independently; agreeable people go along more.
So two neighbours who lived through the same month can see it very differently.

**Reputation.** People become known for something: having more friends than
almost anyone, being among the richest, running a city department, being the
doctor patients love, or being known to the police. The best known are the
city's celebrities.

Nothing here ever looks at a person's faith: the tests check that.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

import numpy as np

from .clock import MINUTES_PER_DAY
from .health import CHECKUP

if TYPE_CHECKING:
    from .events import Event
    from .people import Person
    from .world import World

FEELINGS = ("joy", "sadness", "anger", "fear")
TOPICS = ("taxes", "police", "hospital", "buses", "jobs", "council")
TOPIC_WORDS = {"taxes": "taxes", "police": "the police", "hospital": "the hospital", "buses": "the buses", "jobs": "finding work",
               "council": "the city council"}

# (who in the event, feeling changes, opinion changes)
REACTIONS: dict[str, list[tuple[str, dict[str, float], dict[str, float]]]] = {
    "birth": [("parents", {"joy": 0.5}, {})],
    "couple": [("all", {"joy": 0.45}, {})],
    "hired": [("all", {"joy": 0.3, "fear": -0.2}, {"jobs": 0.25})],
    "laid_off": [("all", {"sadness": 0.4, "anger": 0.35, "fear": 0.3}, {"jobs": -0.45, "council": -0.1})],
    "crime": [("all", {"fear": 0.4, "anger": 0.25}, {"police": -0.2})],
    "arrest": [("all", {"fear": 0.5, "sadness": 0.2}, {"police": -0.3})],
    "court": [("all", {"sadness": 0.3, "fear": 0.2}, {"police": -0.1})],
    "released": [("all", {"joy": 0.3}, {})],
    "sick": [("all", {"fear": 0.3, "sadness": 0.1}, {})],
    "default": [("all", {"fear": 0.35, "sadness": 0.2}, {})],
    "graduated": [("all", {"joy": 0.4}, {})],
    "retired": [("all", {"joy": 0.2, "sadness": 0.1}, {})],
    "arrived": [("all", {"joy": 0.2, "fear": 0.15}, {})],
}


def resting(p: Person) -> dict[str, float]:
    """Where each feeling settles when nothing is happening, from personality."""
    return {
        "joy": 0.25 + 0.35 * p.extraversion,
        "sadness": 0.05 + 0.2 * p.neuroticism,
        "anger": 0.03 + 0.15 * p.neuroticism * (1.0 - p.agreeableness),
        "fear": 0.03 + 0.2 * p.neuroticism,
    }


def independence(p: Person) -> float:
    """How much someone thinks for themselves rather than taking on their friends' views (0..1)."""
    return float(np.clip(0.5 + 0.4 * (p.openness - p.agreeableness) + 0.2 * (p.conscientiousness - 0.5), 0.1, 0.95))


def feeling_word(p: Person) -> str:
    vals = {f: getattr(p, f) - resting(p)[f] for f in FEELINGS}
    top = max(FEELINGS, key=lambda f: (vals[f], f))
    if vals[top] < 0.12:
        return "calm, much as usual"
    return {"joy": "happy and upbeat", "sadness": "low and sad", "anger": "angry and frustrated", "fear": "anxious and worried"}[top]


def opinion_word(v: float) -> str:
    return ("very unhappy with" if v < -0.5 else "unhappy with" if v < -0.15 else "fine with" if v < 0.15 else "happy with" if v < 0.5
            else "very happy with")


def score10(v: float) -> float:
    return round(5 + 5 * v, 1)


class Mind:
    def __init__(self, world: World) -> None:
        self.w = world
        self.rng = world.streams("mind")
        self.poll: dict[str, Any] = {}

    # ---- events move feelings and opinions ---------------------------------------------------

    def react(self, e: Event) -> None:
        w = self.w
        if e.kind == "treated":
            p = w.people.get(e.people[0]) if e.people else None
            if p is not None:
                sat = float(e.data.get("satisfaction", 0.5))
                self._nudge(p, {"joy": 0.1 if sat > 0.6 else 0.0, "anger": 0.25 if sat < 0.4 else 0.0}, {"hospital": (sat - 0.5) * 0.9})
            return
        if e.kind == "death":
            dead = w.people.get(e.people[0]) if e.people else None
            if dead is None:
                return
            close = [q for q in ([dead.partner] if dead.partner is not None else []) + dead.children + list(dead.parents) if q in w.people]
            for q in close:
                self._nudge(w.people[q], {"sadness": 0.6, "joy": -0.3}, {})
            for q, strength in w.social.friends(dead.id)[:10]:
                if q in w.people and q not in close:
                    self._nudge(w.people[q], {"sadness": 0.25 * strength + 0.1}, {})
            return
        if e.kind == "festival":
            faith = e.data.get("faith")
            for p in w.people.values():
                if p.alive and p.religion == faith:  # their own festival, not anyone else's business
                    self._nudge(p, {"joy": 0.2}, {})
            return
        if e.kind == "policy":
            self._policy(e)
            return
        for who, feel, opine in REACTIONS.get(e.kind, ()):
            ids = list(e.people)
            if who == "parents" and e.people:
                child = w.people.get(e.people[0])
                ids = list(child.parents) if child else []
            for pid in ids:
                p = w.people.get(pid)
                if p is not None and p.alive:
                    self._nudge(p, feel, opine)

    def _policy(self, e: Event) -> None:
        lever, was, value = e.data.get("lever"), float(e.data.get("was", 0)), float(e.data.get("value", 0))
        effect: dict[str, float] = {}
        if lever == "bus_fare":
            effect = {"buses": float(np.clip((was - value) / 20.0, -0.4, 0.4))}
        elif lever == "income_tax":
            effect = {"taxes": float(np.clip((was - value) * 3.0, -0.6, 0.6)), "council": float(np.clip((was - value) * 1.5, -0.3, 0.3))}
        elif lever == "benefit":
            effect = {"council": float(np.clip((value - was) / 1000.0, -0.3, 0.3))}
        elif lever == "patrols":
            effect = {"police": float(np.clip((value - was) * 0.1, -0.2, 0.2))}
        for p in self.w.alive():
            if p.age(self.w.t) >= 18:
                self._nudge(p, {}, effect)

    @staticmethod
    def _nudge(p: Person, feel: dict[str, float], opine: dict[str, float]) -> None:
        sens = 0.6 + 0.8 * p.neuroticism  # nervous people feel things more
        for f, d in feel.items():
            setattr(p, f, float(np.clip(getattr(p, f) + d * (sens if d > 0 else 1.0), 0.0, 1.0)))
        for k, d in opine.items():
            p.opinions[k] = float(np.clip(p.opinions.get(k, 0.0) + d, -1.0, 1.0))

    # ---- every night: settle, form views from experience, talk with friends -----------------------

    def nightly(self) -> dict[str, Any]:
        w = self.w
        t = w.t
        adults = [p for p in w.alive() if p.age(t) >= 18]
        for p in w.alive():
            rest = resting(p)
            for f in FEELINGS:
                setattr(p, f, getattr(p, f) + 0.25 * (rest[f] - getattr(p, f)))
        self._day(adults)
        self._experience(adults)
        self._talk(adults)
        self._reputation()
        self.poll = self._poll(adults)
        return {f"view_{k}": v for k, v in self.poll["overall"].items()}

    def _day(self, adults: list[Person]) -> None:
        """How the day itself went: money worries, a long search for work, illness, loneliness, a good or a bad day."""
        w = self.w
        econ = w.economy
        swings = self.rng.normal(0.0, 1.0, (len(adults), len(FEELINGS)))
        for i, p in enumerate(adults):
            acct = econ.person(p.id)
            feel: dict[str, float] = {}

            def add(f: str, d: float) -> None:
                feel[f] = feel.get(f, 0.0) + d

            if econ.balance.get(acct, 0.0) < 1000:
                add("fear", 0.12)
                add("sadness", 0.05)
            if econ._debt(acct) > 0:
                add("fear", 0.08)
            if p.job is None and p.unemployed_since is not None and not p.retired and w.t - p.unemployed_since > 7 * MINUTES_PER_DAY:
                add("sadness", 0.1)
                add("anger", 0.06)
            if p.illness is not None and p.illness != CHECKUP:
                add("sadness", 0.06 * p.severity)
            if not w.social.top_friends(p.id, 1):
                add("sadness", 0.08)
            if p.mood > 0.75:
                add("joy", 0.12)
            elif p.mood < 0.4:
                add("sadness", 0.06)
                add("anger", 0.06)
            # and the ups and downs no one can explain, bigger for nervous people
            for j, f in enumerate(FEELINGS):
                add(f, 0.07 * (0.4 + p.neuroticism) * float(swings[i, j]))
            self._nudge(p, feel, {})

    def _experience(self, adults: list[Person]) -> None:
        """What each person's own life tells them, today."""
        w = self.w
        rate = w.policy.income_tax
        recent = w.t - 7 * MINUTES_PER_DAY
        thefts: dict[str, int] = defaultdict(int)
        for c in w.crime.cases.values():
            if c.reported and c.t >= recent and c.building is not None:
                thefts[w.city.buildings[c.building].district] += 1
        tr = w.transport.history[-1] if w.transport.history else {}
        commute = float(tr.get("commute_min") or 15.0)
        homes_full = 1 - sum(w.city.buildings[b].households - len(o) for b, o in w.occupancy.items()) / max(
            1, sum(w.city.buildings[b].households for b in w.occupancy))
        for p in adults:
            o = p.opinions
            if not p.leanings:  # everyone starts with their own slant: an optimist, a sceptic, a grumbler about buses
                outlook = 0.25 * (p.extraversion - p.neuroticism)
                p.leanings = {k: float(np.clip(outlook + self.rng.normal(0.0, 0.3), -0.7, 0.7)) for k in TOPICS}
                for k, v in p.leanings.items():
                    o.setdefault(k, v)
            lean = p.leanings
            district = w.city.buildings[w.households[p.household].home].district
            friends = [q for q, _ in w.social.top_friends(p.id, 8)]
            cash_friends = sum(1 for q in friends if w.people[q].cash_job)
            services = (o.get("hospital", 0.0) + o.get("buses", 0.0) + o.get("police", 0.0)) / 3
            if p.job is not None and not p.cash_job:
                # an honest taxpayer: the rate, what they get back, and whether friends dodge it
                target = 0.25 - 3.0 * (rate - 0.1) + 0.4 * services - 0.15 * cash_friends
            elif p.cash_job:
                target = 0.4 - 2.0 * (rate - 0.1)
            else:
                target = 0.1 - 1.0 * (rate - 0.1) + 0.3 * services
            target_police = 0.35 - 0.12 * thefts.get(district, 0) - (0.3 if p.record else 0.0)
            target_buses = 0.4 - (commute - 12.0) / 15.0 - (w.policy.bus_fare - 10.0) / 40.0 if not (w.households[p.household].has_car or w.households[p.household].has_scooter) else 0.1
            looking = p.job is None and p.unemployed_since is not None and not p.retired
            target_jobs = -0.5 if looking else 0.3
            target_council = 0.2 * (o.get("jobs", 0.0) + o.get("taxes", 0.0) + services) - (0.4 if homes_full > 0.95 else 0.0)
            for k, target in (("taxes", target), ("police", target_police), ("buses", target_buses), ("jobs", target_jobs),
                              ("council", target_council)):
                target += lean[k]
                o[k] = float(np.clip(o.get(k, 0.0) + 0.08 * (target - o.get(k, 0.0)), -1.0, 1.0))
            # the hospital is judged on visits (see react); between visits views drift back to their own slant
            o["hospital"] = float(np.clip(o.get("hospital", 0.1) + 0.02 * (0.1 + lean["hospital"] - o.get("hospital", 0.1)), -1.0, 1.0))

    def _talk(self, adults: list[Person]) -> None:
        """Friends compare notes; each person decides how much to take on."""
        w = self.w
        snapshot = {p.id: dict(p.opinions) for p in adults}
        for p in adults:
            friends = [(q, s) for q, s in w.social.top_friends(p.id, 6) if q in snapshot]
            if not friends:
                continue
            pull = 0.12 * (1.0 - independence(p))
            total = sum(s for _, s in friends)
            for k in TOPICS:
                avg = sum(snapshot[q].get(k, 0.0) * s for q, s in friends) / total
                p.opinions[k] = p.opinions.get(k, 0.0) + pull * (avg - p.opinions.get(k, 0.0))

    def _reputation(self) -> None:
        w = self.w
        alive = [p for p in w.alive() if p.age(w.t) >= 18]
        if not alive:
            return
        econ = w.economy
        friends = {p.id: len(w.social.friends(p.id)) for p in alive}
        money = {p.id: econ.balance.get(econ.person(p.id), 0.0) for p in alive}
        f_rank = {pid: i for i, pid in enumerate(sorted(friends, key=lambda q: (-friends[q], q)))}
        m_rank = {pid: i for i, pid in enumerate(sorted(money, key=lambda q: (-money[q], q)))}
        n = len(alive)
        heads = {d.head: d.name for d in w.government.departments.values() if d.head is not None}
        docs = {d["id"]: d for d in w.health.doctor_stats(w.t - 60 * MINUTES_PER_DAY)}
        for p in alive:
            reasons: list[tuple[float, str]] = []
            pop = 1.0 - f_rank[p.id] / n
            rich = 1.0 - m_rank[p.id] / n
            if f_rank[p.id] < max(3, n // 100):
                reasons.append((0.9 + pop, f"has more friends than almost anyone in the city ({friends[p.id]})"))
            if m_rank[p.id] < max(3, n // 100):
                reasons.append((0.8 + rich, f"is one of the richest people in the city (₹{money[p.id]:,.0f} in the bank)"))
            if p.id in heads:
                reasons.append((1.2, f"heads the {heads[p.id]}"))
            d = docs.get(p.id)
            if d and d["patients"] >= 8 and d["satisfaction"] is not None:
                reasons.append((1.0 + min(0.6, d["patients"] / 150), "a doctor patients love" if d["satisfaction"] >= 0.68 else
                                "a busy doctor at the Civil Hospital" if d["satisfaction"] >= 0.5 else "a doctor patients complain about"))
            if p.record:
                reasons.append((0.6 + 0.2 * p.record, f"known to the police ({p.record} {'conviction' if p.record == 1 else 'convictions'})"))
            p.fame = round(0.5 * pop + 0.3 * rich + sum(r for r, _ in reasons), 3)
            p.known_for = max(reasons)[1] if reasons else ""

    def _poll(self, adults: list[Person]) -> dict[str, Any]:
        if not adults:
            return {"overall": {}, "taxpayers": {}, "others": {}, "feelings": {}}

        def avg(group: list[Person]) -> dict[str, float]:
            return {k: score10(sum(p.opinions.get(k, 0.0) for p in group) / len(group)) for k in TOPICS} if group else {}

        tax = [p for p in adults if p.job is not None and not p.cash_job]
        others = [p for p in adults if not (p.job is not None and not p.cash_job)]
        feelings = {f: round(100 * sum(getattr(p, f) for p in adults) / len(adults), 1) for f in FEELINGS}
        mood_counts: dict[str, int] = defaultdict(int)
        for p in adults:
            mood_counts[feeling_word(p)] += 1
        return {"overall": avg(adults), "taxpayers": avg(tax), "others": avg(others), "feelings": feelings,
                "moods": dict(sorted(mood_counts.items(), key=lambda kv: -kv[1])), "adults": len(adults), "taxpayer_count": len(tax)}

    # ---- views -----------------------------------------------------------------------------------

    def person(self, p: Person) -> dict[str, Any]:
        return {
            "feelings": {f: round(getattr(p, f), 2) for f in FEELINGS},
            "feeling": feeling_word(p),
            "opinions": {k: round(p.opinions.get(k, 0.0), 2) for k in TOPICS},
            "independence": round(independence(p), 2),
            "fame": p.fame,
            "known_for": p.known_for,
        }

    def celebrities(self, k: int = 5) -> list[dict[str, Any]]:
        top = sorted((p for p in self.w.alive() if p.known_for), key=lambda p: (-p.fame, p.id))[:k]
        return [{"id": p.id, "name": p.name, "known_for": p.known_for, "fame": p.fame} for p in top]
