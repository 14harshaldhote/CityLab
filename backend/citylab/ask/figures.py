"""Exact figures on the subjects people ask about, worked out from the city's own books.

Each function reads the live city and returns a few plain sentences. Counting and
adding up is done here, by the code, never left to a language model.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..core.agencies import SITE_WAGE
from ..core.clock import MINUTES_PER_DAY, SimTime
from ..core.health import CHECKUP, happiness_view, is_doctor
from ..core.mind import TOPIC_WORDS, TOPICS, feeling_word, opinion_word, score10

# event kinds that tell each subject's story, for the records shown as sources
SUBJECT_KINDS: dict[str, tuple[str, ...]] = {
    "budget": ("report", "loan", "policy"),
    "plans": ("zoning", "construction", "opened", "roads"),
    "police": ("arrest", "cctv", "court", "crime"),
    "rich": (),
    "story": ("founded", "opened", "festival", "zoning"),
    "failed": ("laid_off", "default", "construction", "zoning"),
    "happiness": ("report",),
    "feelings": (),
    "opinions": ("policy",),
    "health": ("treated", "sick"),
    "tax": ("tax_audit", "policy"),
    "council": ("policy", "zoning"),
}

SPEND_WORDS = {
    "wages": "staff wages (schools, hospital, police, City Hall, parks)", "pensions": "pensions", "bus diesel": "bus diesel",
    "unemployment benefit": "help for people out of work", "water supply": "pumping water", "police patrols": "police patrols",
    "medicines": "hospital medicines", "road widening": "widening roads", "roadworks": "new streets", "CCTV cameras": "CCTV cameras",
    "contract labour": "contract labour on city building sites", "building materials": "building materials", "loan repayments": "loan repayments",
}
INCOME_WORDS = {"income tax": "income tax", "business tax": "business tax", "property tax": "property tax", "sales tax": "sales tax",
                "water bills": "water bills", "bus fares": "bus fares", "hospital fees": "hospital fees", "court fines": "court fines",
                "back taxes and fines": "back taxes and fines from audits"}


def rs(v: float) -> str:
    return f"₹{v:,.0f}"


def _last(w: Any, days: int = 30) -> list[dict[str, Any]]:
    return w.daily[-days:]


def _sum(rows: list[dict[str, Any]], key: str) -> float:
    return float(sum(float(r.get(key) or 0) for r in rows))


# ---- money -------------------------------------------------------------------------------------------

def budget(w: Any) -> list[str]:
    rows = _last(w)
    if not rows:
        return ["The city hasn't finished its first day yet, so there are no accounts to show."]
    out_, in_ = Counter(), Counter()
    for r in rows:
        out_.update(r.get("city_out") or {})
        in_.update({k: v for k, v in (r.get("city_in") or {}).items() if k != "opening balances"})
    spent, took = sum(out_.values()), sum(in_.values())
    n = len(rows)
    top = ", ".join(f"{SPEND_WORDS.get(k, k)} {rs(v)}" for k, v in out_.most_common(6))
    inc = ", ".join(f"{INCOME_WORDS.get(k, k)} {rs(v)}" for k, v in in_.most_common(6))
    debt = sum(l.balance for l in w.economy.loans.values() if l.account == "city")
    s = [f"Running Kamalnagar cost {rs(spent)} over the last {n} days, about {rs(spent / n)} a day. The biggest costs: {top}.",
         f"It took in {rs(took)}: {inc}.",
         f"The city now has {rs(w.economy.balance['city'])} in its budget" + (f" and owes City Bank {rs(debt)}." if debt else " and no debts.")]
    return s


def tax(w: Any) -> list[str]:
    econ = w.economy
    rows = _last(w)
    dodge = econ.dodging()
    dodged = _sum(rows, "tax_dodged")
    collected = sum(float((r.get("city_in") or {}).get(k, 0)) for r in rows for k in ("income tax", "business tax"))
    recovered = sum(float((r.get("city_in") or {}).get("back taxes and fines", 0)) for r in rows)
    payers = max(1, dodge["taxpayers"])
    s = [f"{dodge['taxpayers']:,} people pay income tax on their wages. {dodge['cash_workers']} are paid cash in hand, so no tax is taken, "
         f"and {dodge['cash_books']} shops and restaurants declare only half their takings."]
    where = Counter(w.city.buildings[p.job.building].name for p in w.alive() if p.job is not None and p.cash_job)
    if where:
        s.append("Most cash-in-hand jobs are at " + ", ".join(f"{b} ({n})" for b, n in where.most_common(3)) + ".")
    if rows:
        share = dodged / max(1.0, collected + dodged)
        s.append(f"Over the last {len(rows)} days {rs(dodged)} of tax went unpaid, {share * 100:.1f}% of what was due. That is about "
                 f"{rs(dodged / payers)} more for every honest taxpayer to carry, or money the city can't spend on schools, the hospital, "
                 f"police and buses.")
        patrol = sum(float((r.get("city_out") or {}).get("police patrols", 0)) for r in rows) / len(rows)
        if patrol:
            s.append(f"The tax dodged would pay for about {dodged / patrol:,.0f} days of police patrols.")
    if recovered:
        s.append(f"The Municipal Tax Office's audits got back {rs(recovered)} in back taxes and fines.")
    s.append(f"The income tax rate is {w.policy.income_tax * 100:.0f}%. The higher it is, the more people are tempted to dodge it.")
    return s


# ---- people's lives ---------------------------------------------------------------------------------

def happiness(w: Any, taxpayers: bool = False) -> list[str]:
    hv = happiness_view(w)
    if not hv:
        return []
    rows = _last(w)
    s = [f"Kamalnagar's happiness index is {hv['index']:.0f} out of 100 (the average life satisfaction of its adults)."]
    old = next((r.get("happiness") for r in rows if r.get("happiness") is not None), None)
    if old is not None and rows:
        trend = hv["index"] - old
        s.append(f"{len(rows)} days ago it was {old:.0f}" + (", so the city is happier." if trend > 1 else ", so it's a little less happy." if trend < -1 else ", much the same."))
    parts = hv["parts"]
    names = {"day": "how their days feel", "money": "money", "work": "work", "friends": "friends", "health": "health", "feelings": "feelings"}
    lo = min(parts, key=parts.get)
    hi = max(parts, key=parts.get)
    s.append(f"People score best on {names[hi]} ({parts[hi]:.0f}) and worst on {names[lo]} ({parts[lo]:.0f}).")
    g = hv["groups"]
    bits = [f"{k} {v:.0f}" for k, v in g.items() if k != "counts" and v is not None]
    s.append("By group: " + ", ".join(bits) + ".")
    d = hv["districts"]
    if d:
        s.append(f"Happiest neighbourhood: {max(d, key=d.get)} ({max(d.values()):.0f}); least happy: {min(d, key=d.get)} ({min(d.values()):.0f}).")
    if taxpayers:
        poll = w.mind.poll
        r = rows[-1] if rows else {}
        if r.get("happiness_taxpayers") is not None:
            s.append(f"Taxpayers score {r['happiness_taxpayers']:.0f} on happiness, against {r.get('happiness_others') or 0:.0f} for everyone else.")
        if poll.get("taxpayers"):
            s.append(f"Asked about taxes, taxpayers give them {poll['taxpayers'].get('taxes', 5):.1f} out of 10 and others "
                     f"{poll['others'].get('taxes', 5):.1f}. Honest taxpayers grumble more when friends are paid cash in hand.")
    return s


def feelings(w: Any) -> list[str]:
    poll = w.mind.poll
    if not poll.get("adults"):
        return []
    moods = poll["moods"]
    n = poll["adults"]
    parts = ", ".join(f"{v * 100 / n:.0f}% {k}" for k, v in moods.items())
    return [f"How the city's {n:,} adults feel tonight: {parts}.",
            "Feelings come from what happens to each person (a new job, a lay-off, a theft, a wedding, an illness) and fade back to their "
            "own nature over a few days; they change what people choose to do next."]


def opinions(w: Any, topics: tuple[str, ...] = TOPICS) -> list[str]:
    poll = w.mind.poll
    if not poll.get("overall"):
        return []
    o = poll["overall"]
    s = ["What the city thinks, out of 10: " + ", ".join(f"{TOPIC_WORDS[k]} {o[k]:.1f}" for k in topics if k in o) + "."]
    s.append("Everyone forms their own views from what happens to them, then compares notes with friends; open-minded people "
             "keep their own views, agreeable ones go along more.")
    return s


def rich(w: Any) -> list[str]:
    econ = w.economy
    adults = [p for p in w.alive() if p.age(w.t) >= 18]
    top = sorted(adults, key=lambda p: (-econ.balance.get(econ.person(p.id), 0.0), p.id))[:3]
    s = []
    if top:
        def job(p: Any) -> str:
            return f"works at {w.city.buildings[p.job.building].name}" if p.job else "is retired" if p.retired else "has no job"
        s.append("The richest people: " + "; ".join(f"{p.name}, {rs(econ.balance.get(econ.person(p.id), 0.0))} in the bank, {job(p)}"
                                                for p in top) + ".")
    celebs = w.mind.celebrities(5)
    if celebs:
        s.append("Kamalnagar has no film stars; its best-known people are: " + "; ".join(f"{c['name']}, who {c['known_for']}"
                                                                                      if not c["known_for"].startswith("a ") else f"{c['name']}, {c['known_for']}"
                                                                                      for c in celebs) + ".")
    firms = econ.companies()[:2]
    if firms:
        s.append("The richest businesses: " + "; ".join(f"{c['name']} ({rs(c['balance'])})" for c in firms) + ".")
    return s


# ---- health -------------------------------------------------------------------------------------------

def health(w: Any, behaviour: bool = False) -> list[str]:
    h = w.health
    view = h.view()
    doctors = view["doctors"]
    m = view["month"]
    staff = len(w.job_holders.get(next((b.id for b in w.city.buildings if b.kind == "hospital"), -1), []))
    s = [f"The Civil Hospital has {staff} staff, {len(doctors)} of them doctors. {view['sick']} people are ill right now"
         + (": " + ", ".join(f"{n} with {k}" for k, n in list(view["by_illness"].items())[:4]) if view["by_illness"] else "") + "."]
    if m["visits"]:
        s.append(f"In the last 30 days doctors saw {m['visits']} patients (check-ups included). The average wait was {m['wait']:.0f} minutes, "
                 f"patients rated their visit {m['satisfaction'] * 10:.1f} out of 10, doctors got the diagnosis right {m['right'] * 100:.0f}% "
                 f"of the time, and {m['free']} {'patient' if m['free'] == 1 else 'patients'} who couldn't afford it {'was' if m['free'] == 1 else 'were'} treated free.")
    seen = [d for d in doctors if d["patients"] >= 3]
    if seen:
        busiest = max(seen, key=lambda d: (d["patients"], -d["id"]))
        kindest = max(seen, key=lambda d: (d["kindness"], -d["id"]))
        careful = max(seen, key=lambda d: (d["minutes"], -d["id"]))
        quick = min(seen, key=lambda d: (d["minutes"], d["id"]))
        s.append(f"Dr. {busiest['name']} is the busiest ({busiest['patients']} patients). Dr. {kindest['name']} is the kindest "
                 f"(patients rate their manner {kindest['kindness'] * 10:.1f}/10). Dr. {careful['name']} takes longest, {careful['minutes']:.0f} "
                 f"minutes a patient, and Dr. {quick['name']} is quickest at {quick['minutes']:.0f}.")
    if behaviour:
        s.extend(doctor_behaviour(w))
    return s


def doctor_behaviour(w: Any) -> list[str]:
    b = w.health.behaviour(w.t - 30 * MINUTES_PER_DAY)
    s = ["Every doctor works in their own way, from their personality: caring doctors are kinder, conscientious ones take longer, "
         "experienced ones get the diagnosis right more often, and calm ones keep their manner when the queue is long."]
    age = {k: v for k, v in b["by_age"].items() if v}
    if age:
        s.append("They take more time over children and older people: " + ", ".join(f"{k} {v['minutes']:.0f} minutes" for k, v in age.items()) + ".")
    sev = {k: v for k, v in b["by_severity"].items() if v}
    if sev:
        s.append("And over serious cases: " + ", ".join(f"{k} {v['minutes']:.0f} minutes" for k, v in sev.items()) + ".")
    sh = {k: v for k, v in b["by_shift"].items() if v}
    if len(sh) >= 2:
        s.append("They tire as the shift goes on: " + ", ".join(f"{k}: {v['minutes']:.0f} minutes, kindness {v['kindness'] * 10:.1f}/10, "
                                                              f"right {v['right'] * 100:.0f}%" for k, v in sh.items()) + ".")
    s.append("A patient's faith, name or neighbourhood never changes how they are treated.")
    return s


# ---- the city's work -----------------------------------------------------------------------------------

def plans(w: Any) -> list[str]:
    g = w.government
    view = g.view()
    d = {x["key"]: x for x in view["departments"]}
    s = []
    if d.get("planning", {}).get("watching"):
        s.append(f"Town Planning is watching: {d['planning']['watching']}")
    if view["projects"]:
        bits = [f"{p['name']} for {p['owner']}, {p['progress'] * 100:.0f}% built, about {p['days_left']} days to go, " +
                (f"{p['crew']} of {p['crew_needed']} builders on the crew" if p["crew"] else "no builders on the crew yet")
                for p in view["projects"][:4]]
        s.append(f"{len(view['projects'])} buildings are going up: " + "; ".join(bits) + ".")
    else:
        s.append("Nothing is being built right now.")
    if view["roadworks"]:
        s.append("Roadworks: " + "; ".join((f"new streets in {r['district']}" if "district" in r else f"widening {r['street']}")
                                           + f", {r['progress'] * 100:.0f}% done" for r in view["roadworks"][:3]) + ".")
    plots = view["plots"]
    if any(plots.values()):
        s.append(f"Plots ready to build on: {plots['residential']} for homes, {plots['commercial']} for shops and offices, {plots['industrial']} for factories.")
    done = view["finished"][:3]
    if done:
        s.append("Recently finished: " + ", ".join(f["name"] for f in done if f.get("name")) + ".")
    pwd = d.get("pwd")
    if pwd:
        s.append(f"Public Works has spent {rs(pwd['spent'])} on {pwd['done']} jobs so far.")
    return s


def police(w: Any) -> list[str]:
    sv = w.crime.view()
    pol, m = sv["police"], sv["month"]
    s = [f"{w.city.buildings[next(b.id for b in w.city.buildings if b.kind == 'police')].name} has "
         f"{len(w.job_holders.get(next(b.id for b in w.city.buildings if b.kind == 'police'), []))} officers; {pol['on_duty']} are on duty now "
         f"with {pol['patrols']} patrol {'car' if pol['patrols'] == 1 else 'cars'} out, and the city has {pol['cameras']} CCTV cameras.",
         f"In the last 30 days there were {m['crimes']} thefts, {m['reported']} reported to the police; {m['solved']} have been solved, "
         f"{m['solved_with_cctv']} of them with CCTV footage. {rs(m['stolen'])} was stolen in all."]
    s.append(f"{len(sv['in_jail'])} {'person is' if len(sv['in_jail']) == 1 else 'people are'} in jail and {len(sv['court'])} "
             f"{'case is' if len(sv['court']) == 1 else 'cases are'} waiting for court.")
    poll = w.mind.poll.get("overall") or {}
    if "police" in poll:
        s.append(f"People rate the police {poll['police']:.1f} out of 10.")
    return s


def people_and_police(w: Any, ids: list[int], called: str, upto: int, events: list[Any]) -> list[str]:
    """Every dealing the police had with a person (or everyone of one name): as a suspect, in court, or as a victim."""
    who = set(ids)
    arrests, court, victims = [], [], []
    for e in events:
        if e.id >= upto or not who & set(e.people):
            continue
        if e.kind == "arrest":
            arrests.append(e)
        elif e.kind == "court":
            court.append(e)
        elif e.kind == "crime":
            victims.append(e)
    group = f"the {len(ids)} people called {called}" if called and len(ids) > 1 else w.people[ids[0]].name if ids else "them"

    def names(es: list[Any]) -> str:
        found = sorted({w.people[p].name for e in es for p in e.people if p in who})
        return f" ({', '.join(found[:4])}{'...' if len(found) > 4 else ''})" if found else ""

    return [f"Police dealings with {group}: {len(arrests)} {'arrest' if len(arrests) == 1 else 'arrests'}{names(arrests)}, "
            f"{len(court)} court {'case' if len(court) == 1 else 'cases'}{names(court)}, and {len(victims)} "
            f"{'time' if len(victims) == 1 else 'times'} as the victim of a theft{names(victims)}."]


def story(w: Any) -> list[str]:
    rows = w.daily
    start = SimTime(0).datetime
    s = [f"{w.city.name} was founded on {start:%-d %B %Y} with {rows[0]['population'] - (rows[0].get('arrived') or 0) if rows else len(w.alive()):,} "
         f"people around Kamal Talav, the lotus lake. It has now run for {len(rows)} days and has {len(w.alive()):,} people."]
    if rows:
        s.append(f"Since then {int(_sum(rows, 'births'))} babies were born, {int(_sum(rows, 'couples'))} couples got together, "
                 f"{int(_sum(rows, 'arrived'))} people moved in and {int(_sum(rows, 'left'))} left; "
                 + (f"{len(w.government.finished)} new buildings opened" if w.government.finished else "no new buildings have opened yet")
                 + f", and police recorded {int(_sum(rows, 'crimes_reported'))} thefts.")
    from ..core import reports

    reps = reports.reports(rows, w.government.finished, w.city.name, "month") if rows else []
    done = [r for r in reps if r["complete"]]
    for rep in (done[:2] or reps[:1])[::-1]:  # whole months tell the story; a month just begun adds little
        s.append(rep["text"] + ("" if rep["complete"] else " (So far this month.)"))
    celebs = w.mind.celebrities(1)
    if celebs:
        s.append(f"Its best-known resident is {celebs[0]['name']}, who {celebs[0]['known_for']}." if not celebs[0]["known_for"].startswith("a ")
                 else f"Its best-known resident is {celebs[0]['name']}, {celebs[0]['known_for']}.")
    return s


def failures(w: Any, events: list[Any]) -> list[str]:
    g = w.government.view()
    s = []
    short = [p for p in g["projects"] if p["crew_needed"] and p["crew"] < p["crew_needed"] / 2]
    if short:
        need = sum(p["crew_needed"] for p in short)
        have = sum(p["crew"] for p in short)
        extra = sum((p["crew_needed"] - p["crew"]) * SITE_WAGE * 0.5 for p in short)
        worst = max(short, key=lambda p: p["days_left"])
        s.append(f"{len(short)} building {'site is' if len(short) == 1 else 'sites are'} short of builders: between them they have "
                 f"{have} of the {need} they need, so the developers pay about {rs(extra)} a day extra for contract labour from outside. "
                 f"The furthest behind is {worst['name']}, {worst['progress'] * 100:.0f}% built with {worst['days_left']} days still to go.")
    alive = w.alive()
    seekers = sum(1 for p in alive if p.job is None and p.unemployed_since is not None and not p.retired)
    vac = sum(1 for bid, _ in w.vacancies() if w.city.buildings[bid].status == "open")
    if vac > 5 * seekers + 20:
        s.append(f"{vac:,} jobs are open but only {seekers} people are looking for work: the city has more workplaces than workers, "
                 "so businesses run short-staffed.")
    elif seekers > vac + 15:
        s.append(f"{seekers} people are looking for work but only {vac} jobs are open.")
    rows = _last(w)
    since = w.t - 30 * MINUTES_PER_DAY
    laid = _count_by_place(w, events, "laid_off", since)
    if laid:
        n = sum(laid.values())
        s.append(f"{n} {'person was' if n == 1 else 'people were'} laid off in the last 30 days by businesses that ran out of money, "
                 + (f"all at {next(iter(laid))}." if len(laid) == 1 else "most at " + ", ".join(f"{b} ({k})" for b, k in laid.most_common(2)) + "."))
    defaults = _count_by_place(w, events, "default", since)
    if defaults:
        s.append(f"{sum(defaults.values())} loans went bad and City Bank wrote them off.")
    struggling = [c for c in w.economy.companies() if c["balance"] < 0 or c["debt"] > 0]
    if struggling:
        s.append(f"{len(struggling)} businesses are in debt, such as {struggling[-1]['name']}.")
    full = 1 - sum(w.city.buildings[b].households - len(o) for b, o in w.occupancy.items()) / max(1, sum(w.city.buildings[b].households for b in w.occupancy))
    if full > 0.97:
        s.append(f"Homes are {full * 100:.0f}% full: there's almost nowhere left for newcomers to live.")
    if rows and _sum(rows, "tax_dodged"):
        s.append(f"{rs(_sum(rows, 'tax_dodged'))} of tax went unpaid in the last {len(rows)} days.")
    if not s:
        s.append("Nothing has gone badly wrong yet: building sites are staffed, jobs and workers are in balance, and no business is in trouble.")
    return s


def _count_by_place(w: Any, events: list[Any], kind: str, since: int) -> Counter:
    c: Counter = Counter()
    for e in reversed(events):
        if e.t < since:
            break
        if e.kind == kind and e.place is not None:
            c[w.city.buildings[e.place].name] += 1
    return c


def council(w: Any) -> list[str]:
    g = w.government.view()
    heads = [f"{d['name']}: {d['head']['name']}" for d in g["departments"] if d.get("head")]
    s = ["Kamalnagar is run by its municipal corporation's departments, each led by a City Hall officer: " + "; ".join(heads[:6]) + "."]
    poll = w.mind.poll.get("overall") or {}
    if "council" in poll:
        s.append(f"People rate the city council {poll['council']:.1f} out of 10.")
    return s


# ---- comparing places, groups and moments ---------------------------------------------------------------

PART_NAMES = {"day": "how their days go", "money": "money", "work": "work", "friends": "friends", "health": "health", "feelings": "feelings"}


def _district(w: Any, p: Any) -> str:
    return w.city.buildings[w.households[p.household].home].district


def _adults(w: Any) -> list[Any]:
    return [p for p in w.alive() if p.age(w.t) >= 18]


def in_group(w: Any, p: Any, g: str) -> bool:
    econ = w.economy
    if g == "unemployed":
        return p.job is None and p.unemployed_since is not None and not p.retired
    if g == "retired":
        return p.retired
    if g == "workers":
        return p.job is not None
    if g == "cash":
        return p.job is not None and p.cash_job
    if g == "doctors":
        return is_doctor(w, p)
    if g == "police":
        return p.job is not None and w.city.buildings[p.job.building].kind == "police"
    if g == "teachers":
        return p.job is not None and w.city.buildings[p.job.building].kind == "school"
    if g == "poor":
        return econ.balance.get(econ.person(p.id), 0.0) < 500
    if g == "rich":
        return econ.balance.get(econ.person(p.id), 0.0) >= 10000
    return False


GROUP_NAMES = {"unemployed": "people looking for work", "retired": "retired people", "workers": "people with a job",
               "cash": "people paid cash in hand", "doctors": "doctors", "police": "police officers", "teachers": "teachers",
               "poor": "people with under ₹500 saved", "rich": "people with ₹10,000 or more saved"}


def _parts(w: Any, people: list[Any]) -> dict[str, float]:
    from ..core.health import satisfaction

    xs = [satisfaction(w, p) for p in people]
    return {k: 100 * sum(x[k] for x in xs) / len(xs) for k in ("score",) + tuple(PART_NAMES)} if xs else {}


def _why(parts: dict[str, float], city: dict[str, float]) -> str:
    gaps = sorted(((parts[k] - city[k]) * (0.2 if k == "day" else 0.18 if k == "money" else 0.17 if k == "work" else 0.15), k) for k in PART_NAMES)
    low = [(d, k) for d, k in gaps if d < -0.3][:2]
    high = [(d, k) for d, k in gaps[::-1] if d > 0.3][:1]
    bits = []
    if low:
        bits.append("they score lower on " + " and ".join(f"{PART_NAMES[k]} ({parts[k]:.0f} against {city[k]:.0f} city-wide)" for _, k in low))
    if high:
        bits.append(f"higher on {PART_NAMES[high[0][1]]} ({parts[high[0][1]]:.0f} against {city[high[0][1]]:.0f})")
    return "; ".join(bits) if bits else "they score close to the city average on everything"


def happiness_where(w: Any, districts: list[str], why: bool, claim: str = "") -> list[str]:
    """``claim`` is what the question takes for granted ("less" happy, "more" happy), checked rather than repeated."""
    adults = _adults(w)
    city = _parts(w, adults)
    s = []
    if claim and len(districts) == 1:
        here = _parts(w, [p for p in adults if _district(w, p) == districts[0]])
        if here and (claim == "less" and here["score"] >= city["score"] or claim == "more" and here["score"] <= city["score"]):
            s.append(f"Actually, {districts[0]} is {'not less' if claim == 'less' else 'not more'} happy than the rest of the city.")
    for d in districts:
        people = [p for p in adults if _district(w, p) == d]
        if not people:
            s.append(f"No adults live in {d} yet.")
            continue
        parts = _parts(w, people)
        line = f"{d}: happiness {parts['score']:.0f} out of 100 ({len(people)} adults), against {city['score']:.0f} for the whole city"
        s.append(line + (f". Why: {_why(parts, city)}." if why or len(districts) > 1 else "."))
    if len(districts) > 1:
        scores = {d: _parts(w, [p for p in adults if _district(w, p) == d]).get("score", 0) for d in districts}
        best = max(scores, key=scores.get)
        s.append(f"{best} is the happier of the two." if len(districts) == 2 else f"Happiest of these: {best}.")
    return s


def by_group(w: Any, groups: list[str], what: str) -> list[str]:
    """Happiness, feelings or opinions of one group of people next to everyone else."""
    adults = _adults(w)
    city = _parts(w, adults)
    s = []
    for g in groups:
        people = [p for p in adults if in_group(w, p, g)]
        name = GROUP_NAMES[g]
        if not people:
            s.append(f"There are no {name} in Kamalnagar right now.")
            continue
        if what == "happiness":
            parts = _parts(w, people)
            s.append(f"{name[0].upper() + name[1:]} ({len(people)}) score {parts['score']:.0f} on happiness, against {city['score']:.0f} "
                     f"city-wide: {_why(parts, city)}.")
        elif what == "opinions":
            avg = {k: score10(sum(p.opinions.get(k, 0.0) for p in people) / len(people)) for k in TOPICS}
            overall = w.mind.poll.get("overall") or {}
            s.append(f"What {name} ({len(people)}) think, out of 10: " + ", ".join(
                f"{TOPIC_WORDS[k]} {avg[k]:.1f}" + (f" (city {overall[k]:.1f})" if k in overall else "") for k in TOPICS) + ".")
        else:
            moods = Counter(feeling_word(p) for p in people)
            s.append(f"How {name} ({len(people)}) feel: " + ", ".join(f"{n * 100 / len(people):.0f}% {k}" for k, n in moods.most_common()) + ".")
    return s


def extremes(w: Any, feeling: str, events: list[Any], k: int = 3) -> list[str]:
    """The people feeling something most strongly right now, and what happened to them lately."""
    from ..core.mind import resting

    adults = _adults(w)
    top = sorted(adults, key=lambda p: (-(getattr(p, feeling) - resting(p)[feeling]), p.id))[:k]
    word = {"anger": "angriest", "joy": "happiest", "sadness": "saddest", "fear": "most worried"}[feeling]
    ids = {p.id for p in top}
    last: dict[int, Any] = {}
    since = w.t - 7 * MINUTES_PER_DAY
    for e in reversed(events):
        if e.t < since:
            break
        for pid in e.people:
            if pid in ids and pid not in last:
                last[pid] = e
    econ = w.economy
    bits = []
    for p in top:
        acct = econ.person(p.id)
        reasons = []
        e = last.get(p.id)
        if e is not None:
            reasons.append(f"lately: {e.text.rstrip('.')}")
        if p.job is None and p.unemployed_since is not None and not p.retired and w.t - p.unemployed_since >= MINUTES_PER_DAY:
            reasons.append(f"out of work for {(w.t - p.unemployed_since) // MINUTES_PER_DAY} days")
        if econ.balance.get(acct, 0.0) < 200:
            reasons.append(f"only {rs(econ.balance.get(acct, 0.0))} in the bank")
        if econ._debt(acct) > 0:
            reasons.append("in debt to City Bank")
        if p.illness is not None and p.illness != CHECKUP:
            reasons.append(f"ill with {p.illness}")
        if not w.social.top_friends(p.id, 1):
            reasons.append("no friends yet")
        if p.mood < 0.4:
            reasons.append("having a hard day")
        if p.neuroticism > 0.7 and feeling != "joy":
            reasons.append("an easily upset person by nature")
        if p.extraversion > 0.7 and feeling == "joy":
            reasons.append("cheerful by nature")
        why = "; ".join(reasons[:3]) or "no single cause: small things added up"
        bits.append(f"{p.name}, {int(p.age(w.t))}, of {_district(w, p)} ({why})")
    return [f"The {word} people in Kamalnagar right now: " + "; ".join(bits) + ".",
            "Feelings rise with what happens to people and with money worries, illness, loneliness and bad days, then fade back to each person's own nature."]


def friends_of(w: Any, pid: int) -> list[str]:
    p = w.people[pid]
    fr = w.social.top_friends(pid, 6)
    kin = ([(p.partner, "partner")] if p.partner is not None else []) + [(q, "parent") for q in p.parents] + [(q, "child") for q in p.children]
    s = []
    if fr:
        def close(x: float) -> str:
            return "close" if x >= 0.6 else "good" if x >= 0.3 else "new"
        s.append(f"{p.name}'s closest friends: " + ", ".join(f"{w.people[q].name} ({close(x)} friend)" for q, x in fr if q in w.people) + ".")
    else:
        s.append(f"{p.name} hasn't made any friends yet.")
    if kin:
        s.append("Family: " + ", ".join(f"{w.people[q].name} ({k})" for q, k in kin[:6] if q in w.people) + ".")
    return s


def theft_by_district(w: Any) -> list[str]:
    c = Counter(w.city.buildings[x.building].district for x in w.crime.cases.values() if x.reported and x.building is not None)
    if not c:
        return ["No thefts have been reported yet."]
    pop = Counter(_district(w, p) for p in w.alive())
    worst = c.most_common(3)
    return ["Thefts reported by neighbourhood (where they happened): " + ", ".join(f"{d} {n}" for d, n in worst)
            + f". Per 1,000 residents the worst is {max(c, key=lambda d: c[d] / max(1, pop[d]))}. Thieves go where people gather"
              " (markets, restaurants, parks) and where homes are left empty, not where any one community lives."]


def cctv(w: Any) -> list[str]:
    cases = [x for x in w.crime.cases.values() if x.reported]
    cam = [x for x in cases if x.cctv]
    rest = [x for x in cases if not x.cctv]

    def rate(xs: list[Any]) -> float:
        return 100 * sum(1 for x in xs if x.caught or x.status in ("awaiting trial", "convicted", "acquitted")) / len(xs) if xs else 0.0

    if not cam:
        return [f"No reported theft has been caught on camera yet; {rate(rest):.0f}% of the others led to an arrest."]
    a, b = rate(cam), rate(rest)
    verdict = "Yes" if a > b + 5 else "Not so far" if a < b - 5 else "A little, if at all"
    return [f"{verdict}: {len(cam)} reported {'theft was' if len(cam) == 1 else 'thefts were'} caught on a CCTV camera and {a:.0f}% of those "
            f"led to an arrest, against {b:.0f}% of the {len(rest)} without footage. In Kamalnagar a camera gives the police evidence; "
            "it doesn't scare thieves away. The police add one each week on the corner with the most reported thefts."]


def dodgers(w: Any) -> list[str]:
    econ = w.economy
    by = sorted(((v, a) for a, v in econ.dodged.items() if v >= 1 and a.startswith("c:")), reverse=True)[:3]
    if not by:
        return ["No business owes back tax right now; the Tax Office's last audits cleared them."]
    return ["The businesses with the most unpaid tax right now (not yet audited): " + ", ".join(
        f"{w.city.buildings[int(a[2:])].name} ({rs(v)})" for v, a in by) + "."]


def doctor_mistakes(w: Any) -> list[str]:
    docs = [d for d in w.health.doctor_stats(w.t - 30 * MINUTES_PER_DAY) if d["patients"] >= 5]
    if not docs:
        return ["No doctor has seen enough patients yet to compare."]
    worst = sorted(docs, key=lambda d: (d["right"], d["id"]))
    d0 = worst[0]
    if d0["right"] >= 1:
        return [f"Dr. {d0['name']} hasn't got a diagnosis wrong in the last 30 days." if len(docs) == 1 else
                f"None of the {len(docs)} doctors has got a diagnosis wrong in the last 30 days."]
    return [f"Dr. {d0['name']} gets the diagnosis wrong most often: right {d0['right'] * 100:.0f}% of the time over {d0['patients']} patients. "
            + "The others: " + ", ".join(f"Dr. {d['name']} {d['right'] * 100:.0f}%" for d in worst[1:5]) + ". Mistakes rise late in a long shift "
            "and with less experienced doctors."]


def fairness(w: Any) -> list[str]:
    vs = [v for v in w.health.visits if v["t"] >= w.t - 30 * MINUTES_PER_DAY and v["doctor"] is not None]
    free = [v for v in vs if not v["paid"]]
    paid = [v for v in vs if v["paid"]]
    if not free or not paid:
        return []

    def avg(xs: list[dict[str, Any]], k: str) -> float:
        return sum(float(v[k]) for v in xs) / len(xs)

    return [f"Patients who can't afford the fee (under ₹300 in the bank) are treated free: {len(free)} in the last 30 days. They waited "
            f"{avg(free, 'wait'):.0f} minutes against {avg(paid, 'wait'):.0f} for paying patients, got {avg(free, 'minutes'):.1f} minutes with "
            f"the doctor against {avg(paid, 'minutes'):.1f}, and were diagnosed right {avg(free, 'correct') * 100:.0f}% of the time against "
            f"{avg(paid, 'correct') * 100:.0f}%. Doctors never see a patient's bank balance; any gap comes from the time of day and the queue."]


def hospital_hours(w: Any) -> list[str]:
    vs = [v for v in w.health.visits if v["t"] >= w.t - 30 * MINUTES_PER_DAY]
    slots = {"morning (7 to 12)": (7, 12), "afternoon (12 to 5)": (12, 17), "evening (5 to 9)": (17, 21)}
    bits = []
    for name, (a, b) in slots.items():
        xs = [v for v in vs if a <= (v["t"] % MINUTES_PER_DAY) // 60 < b]
        if xs:
            bits.append(f"{name}: {sum(v['wait'] for v in xs) / len(xs):.0f} minutes ({len(xs)} visits)")
    if not bits:
        return []
    return ["Patients only come in between 7 in the morning and 9 at night, so nobody waits at night. Average wait by time of day: "
            + ", ".join(bits) + "."]


def trend(w: Any) -> list[str]:
    rows = w.daily
    if len(rows) < 4:
        return ["The city is too young to compare: it has run for fewer than 4 days."]
    n = min(7, len(rows) // 2)  # two weeks that don't overlap, or as close as a young city allows
    a, b = rows[:n], rows[-n:]
    span = "week" if n == 7 else f"{n} days"

    def avg(rs_: list[dict[str, Any]], k: str) -> float:
        xs = [float(r[k]) for r in rs_ if r.get(k) is not None]
        return sum(xs) / len(xs) if xs else 0.0

    def tot(rs_: list[dict[str, Any]], k: str) -> float:
        return sum(float(r.get(k) or 0) for r in rs_)

    s = [f"Comparing the first {span} with the last {n} days: population {a[-1]['population']:,} → {b[-1]['population']:,}; happiness "
         f"{avg(a, 'happiness'):.0f} → {avg(b, 'happiness'):.0f}; thefts {tot(a, 'crimes'):.0f} → {tot(b, 'crimes'):.0f} a {span}; people looking for "
         f"work {a[-1].get('unemployed', 0)} → {b[-1].get('unemployed', 0)}; ill {avg(a, 'sick'):.0f} → {avg(b, 'sick'):.0f}; the trip to work "
         f"{avg(a, 'commute_min'):.1f} → {avg(b, 'commute_min'):.1f} minutes; the city's budget {rs(a[-1].get('city', 0))} → {rs(b[-1].get('city', 0))}."]
    views = [(k, avg(a, f"view_{k}"), avg(b, f"view_{k}")) for k in TOPICS]
    moved = sorted(views, key=lambda x: -abs(x[2] - x[1]))[:2]
    if moved and abs(moved[0][2] - moved[0][1]) >= 0.2:
        s.append("Opinions that moved most: " + ", ".join(f"{TOPIC_WORDS[k]} {x:.1f} → {y:.1f} out of 10" for k, x, y in moved) + ".")
    return s


LEVERS = {"income_tax": ("tax", "taxes", "income"), "bus_fare": ("fare", "fares", "bus", "buses", "ticket"),
          "benefit": ("benefit", "benefits", "dole", "allowance"), "patrols": ("patrol", "patrols", "police")}


def whatif(w: Any, words: list[str]) -> list[str]:
    lever = next((k for k, ws in LEVERS.items() if set(ws) & set(words)), None)
    s = ["I won't guess at the future. The What-if tab can answer that properly: it runs a copy of Kamalnagar forward with the new rule, "
         "next to the real one, and shows the difference day by day."]
    if lever == "income_tax":
        s.append(f"For now: income tax is {w.policy.income_tax * 100:.0f}%. In this city a higher rate means more money for services, but more "
                 "businesses tempted to pay cash in hand, and honest taxpayers rating taxes and the council lower.")
    elif lever == "bus_fare":
        s.append(f"For now: the bus fare is ₹{w.policy.bus_fare:.0f}. Dearer fares push people to walk, take autos or drive, and lower how they rate the buses.")
    elif lever == "patrols":
        s.append(f"For now: police patrols are at {w.policy.patrols:.1f} times the normal level. More patrols mean more thefts seen and stopped, and cost diesel and wages.")
    elif lever == "benefit":
        s.append(f"For now: help for people out of work is ₹{w.policy.benefit:.0f} a day. More help means fewer people in hard times, and hard times are what make theft tempting.")
    return s


def runway(w: Any) -> list[str]:
    rows = _last(w)
    if not rows:
        return []
    spent = sum(sum((r.get("city_out") or {}).values()) for r in rows) / len(rows)
    took = sum(sum(v for k, v in (r.get("city_in") or {}).items() if k != "opening balances") for r in rows) / len(rows)
    bal = w.economy.balance["city"]
    if took >= spent:
        return [f"No: over the last {len(rows)} days it took in {rs(took - spent)} a day more than it spent."]
    days = bal / (spent - took) if spent > took else 0
    return [f"Not yet, but it is spending {rs(spent - took)} a day more than it takes in. At that rate the {rs(bal)} in the budget would last "
            f"about {days:,.0f} days, after which the city would have to borrow from City Bank."]


__all__ = ["SUBJECT_KINDS", "budget", "by_group", "cctv", "council", "doctor_mistakes", "dodgers", "extremes", "fairness",
           "friends_of", "happiness_where", "hospital_hours", "runway", "theft_by_district", "trend", "whatif", "doctor_behaviour", "failures", "feelings", "happiness", "health", "opinions",
           "people_and_police", "plans", "police", "rich", "story", "tax", "feeling_word", "opinion_word", "score10", "is_doctor", "CHECKUP"]
