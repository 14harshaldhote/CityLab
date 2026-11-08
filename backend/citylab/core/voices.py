"""What's bothering people, in their own words.

Nobody writes these lines. Each one is read straight off a person's own life in the
simulation: the days they have spent looking for work, what is left in their bank
account, the minutes they waited at the Civil Hospital, the wallet picked on the bus,
the score they would give the buses. Nothing is added that the town did not do to them.

And not everyone speaks up. Each person has their own limits (``mind.thresholds``): a
nervous person worries at things a calm one shrugs off, an agreeable one is slow to
anger. A complaint is voiced only when the feeling it stirs has passed that person's
own limit, so the same bad day can leave one neighbour fuming and the next one calm.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from .clock import MINUTES_PER_DAY, SimTime
from .health import CHECKUP
from .people import JAIL

if TYPE_CHECKING:
    from .people import Person
    from .world import World

DAY = MINUTES_PER_DAY
# what each worry is about, as the panel lists it
ABOUT = {
    "work": "no job",
    "money": "money running out",
    "debt": "debts",
    "health": "being ill",
    "hospital": "the hospital queue",
    "lonely": "loneliness",
    "pay": "low pay",
    "taxes": "paying tax when others don't",
    "theft": "being robbed",
    "safety": "thefts nearby",
    "grief": "losing someone",
    "jail": "being in jail",
    "buses": "the buses",
    "police": "the police",
    "council": "the city council",
    "jobs": "finding work",
    "hospital_view": "the hospital",
    "taxes_view": "taxes",
    "day": "a rough day",
    "low": "a passing mood, no clear cause",
}
VIEW_TOPICS = {"taxes": "taxes_view", "police": "police", "hospital": "hospital_view", "buses": "buses", "jobs": "jobs", "council": "council"}
ROUGH_DAY = {"fun": "No time for anything but work and chores lately.", "energy": "Completely worn out.",
             "hunger": "Haven't had a proper meal today.", "social": "Haven't seen a friend in days."}
LOW_PAY = 12_000.0  # a month: below this a wage barely covers rent and food in a town


def context(w: World) -> dict[str, Any]:
    """What happened around town lately, gathered once so each person's worries are quick to read."""
    week = w.t - 7 * DAY
    thefts: Counter[str] = Counter()
    robbed: dict[int, Any] = {}
    for c in w.crime.cases.values():
        if c.t < week:
            continue
        if c.reported and c.building is not None:
            thefts[w.city.buildings[c.building].district] += 1
        if c.victim_id is not None:
            robbed[c.victim_id] = c
    visits = {v["patient"]: v for v in w.health.visits if v["t"] >= w.t - 3 * DAY}
    return {"thefts": thefts, "robbed": robbed, "visits": visits}


def complaints(w: World, p: Person, ctx: dict[str, Any]) -> list[tuple[float, str, str, str]]:
    """Everything weighing on this person right now: (how much, what about, which feeling, in their words)."""
    from .mind import TOPIC_WORDS, score10

    t = w.t
    econ = w.economy
    acct = econ.person(p.id)
    out: list[tuple[float, str, str, str]] = []
    if p.activity == JAIL:
        out.append((0.9, "jail", "sadness", f"Locked up until {SimTime(p.jailed_until).label()}."))
    if p.job is None and p.unemployed_since is not None and not p.retired:
        days = (t - p.unemployed_since) // DAY
        if days >= 1:
            out.append((0.4 + min(0.4, days / 60), "work", "anger" if days > 30 else "sadness",
                        f"Still no job after {days} {'day' if days == 1 else 'days'} of looking."))
    bal = econ.balance.get(acct, 0.0)
    if bal < 1000:
        out.append((0.6, "money", "fear", f"Only ₹{max(0.0, bal):,.0f} left in the bank."))
    elif bal < 3000:
        out.append((0.3, "money", "fear", f"Down to ₹{bal:,.0f} in savings."))
    debt = econ._debt(acct)
    if debt > 0:
        out.append((0.3 + min(0.3, debt / 50_000), "debt", "fear", f"I still owe City Bank ₹{debt:,.0f}."))
    if p.illness is not None and p.illness != CHECKUP:
        out.append((0.2 + 0.15 * p.severity, "health", "sadness", f"Laid up with {p.illness}."))
    v = ctx["visits"].get(p.id)
    if v is not None and (v["wait"] >= 60 or v["satisfaction"] < 0.4):
        place = w.city.buildings[v["place"]].name.split(",")[0]
        out.append((0.35 + min(0.3, v["wait"] / 300), "hospital", "anger",
                    f"Waited {v['wait']} minutes at {place}" + (" and the doctor hardly listened." if v["satisfaction"] < 0.4 else ".")))
    if not w.social.friends(p.id):
        out.append((0.4, "lonely", "sadness", "I don't really have anyone to talk to."))
    if p.job is not None and w.city.buildings[p.job.building].status == "open":
        month = 26 * p.job.wage
        if month < LOW_PAY:
            out.append((0.25, "pay", "sadness", f"₹{month:,.0f} a month at {w.city.buildings[p.job.building].name.split(',')[0]} doesn't go far."))
        if not p.cash_job:
            cash = sum(1 for q, _ in w.social.top_friends(p.id, 8) if w.people[q].cash_job)
            if cash >= 2:
                out.append((0.15 + 0.05 * cash, "taxes", "anger", f"I pay my taxes while {cash} of my friends are paid cash in hand."))
    c = ctx["robbed"].get(p.id)
    if c is not None:
        text = {"pickpocket": f"Someone picked my pocket at {c.place}.", "burglary": "Thieves broke into our home."}.get(
            c.kind, f"I was robbed at {c.place}.")
        out.append((0.6, "theft", "fear", text))
    district = w.city.buildings[w.households[p.household].home].district
    near = ctx["thefts"].get(district, 0)
    if near >= 2:
        out.append((0.15 + 0.05 * min(6, near), "safety", "fear", f"{near} thefts reported in {district} this week."))
    grief = w.mind.grief.get(p.id)
    if grief is not None and t - grief[0] <= 14 * DAY:
        out.append((0.7, "grief", "sadness", f"I lost my {grief[1]}."))
    if p.mood < 0.45:  # a rough day: whichever need has gone most unmet
        need, level = min((("fun", p.fun), ("energy", p.energy), ("hunger", p.hunger), ("social", p.social)), key=lambda kv: (kv[1], kv[0]))
        if level < 0.35:
            out.append((0.3, "day", "sadness" if need in ("social", "energy") else "anger", ROUGH_DAY[need]))
    past = w.mind.memory.get(p.id)  # something that happened to them this week, still on their mind
    if past is not None and t - past[0] <= 7 * DAY and all(c[1] != past[1] for c in out):
        out.append((0.25, past[1], past[2], past[3]))
    for k, about in VIEW_TOPICS.items():
        o = p.opinions.get(k, 0.0)
        if o < -0.4:
            out.append((0.1 + 0.3 * -o, about, "anger", f"I'd give {TOPIC_WORDS[k]} {score10(o)} out of 10."))
    out.sort(key=lambda c: (-c[0], c[1]))
    return out


def main_worry(w: World, p: Person, ctx: dict[str, Any], feeling: str | None) -> tuple[str, str]:
    """The one thing on top of their mind: what fits the feeling they have most, else whatever weighs most."""
    worries = complaints(w, p, ctx)
    for _, about, f, text in worries:
        if f == feeling:
            return about, text
    if worries:
        return worries[0][1], worries[0][3]
    return "low", {"sadness": "Just feeling low today.", "anger": "Everything is getting on my nerves today.",
                   "fear": "I can't shake a worried feeling today."}.get(feeling or "", "Just one of those days.")


__all__ = ["ABOUT", "complaints", "context", "main_worry"]
