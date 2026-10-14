"""Health and happiness: people fall ill, see a doctor, get better, and feel how life is going.

**Falling ill.** Every night each person has a small chance of coming down with
something. The chance rises with age and poor health, for small children, in the
monsoon (stomach bugs, dengue) and in winter (colds), and a little when someone is
run down. Illnesses run from a cold to a heart problem, and each has its own
seriousness and recovery time. Mild ones are slept off at home; anything worse
sends people to the Civil Hospital, and keeps them off work or school.

**Doctors.** The hospital's most skilled staff are its doctors, and each one works
in their own way, from their personality:

* *care* (agreeableness): how kind they are with a patient;
* *thoroughness* (conscientiousness): how long they take over a check-up;
* *calm* (low neuroticism): how well they keep their manner when the queue is long;
* *experience* (skill): how often they get the diagnosis right.

The same doctor also behaves differently from one patient to the next. They take
more time over children, older people and serious cases; they get tired as the
shift goes on, so the tenth patient gets a shorter, less patient check-up than the
first; and a rushed check-up is more likely to miss what's wrong, which means a
slower recovery and a second visit. A patient's faith, name or neighbourhood never
changes how they're treated: the tests check that.

**Happiness.** Every night each person's life satisfaction is worked out from five
things: how their day felt (their needs), money (savings and debt), work (a job,
school or a pension, against looking for work), friends, health, and their feelings (joy against sadness, fear and anger). The city's
happiness index is the average over its adults, from 0 to 100.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from .clock import MINUTES_PER_DAY, SimTime
from .people import HOSPITAL, JAIL, WORK, Person

if TYPE_CHECKING:
    from .world import World

DOCTOR_SKILL = 0.72  # hospital staff at least this skilled work as doctors; the rest are nurses and orderlies
CONSULT_FEE = 30.0
MEDICINES = {1: 40.0, 2: 120.0, 3: 400.0}
FREE_BELOW = 300.0  # patients with less than this in the bank are treated free; the city pays
BASE_MINUTES = {1: 8.0, 2: 14.0, 3: 25.0}
SEE_DOCTOR = {1: 0.35, 2: 0.85, 3: 1.0}  # chance of going to hospital, by seriousness
SEVERITY = {1: "mild", 2: "moderate", 3: "serious"}


@dataclass(frozen=True, slots=True)
class Illness:
    name: str
    severity: int  # 1 mild, 2 moderate, 3 serious
    days: float  # recovery when treated well


CHECKUP = "a routine check-up"
ILLNESSES = (
    Illness("a cold and cough", 1, 3), Illness("a fever", 1, 4), Illness("back pain", 1, 5), Illness("a stomach bug", 2, 3),
    Illness("a bad fever", 2, 5), Illness("high blood pressure", 2, 7), Illness("a broken bone", 2, 20), Illness("dengue", 3, 10),
    Illness("pneumonia", 3, 12), Illness("a heart problem", 3, 14),
)
ROUTINE = Illness(CHECKUP, 1, 0.5)  # not ill at all: a blood-pressure check, a vaccination, a prescription


def _weights(age: float, month: int) -> np.ndarray:
    monsoon = 6 <= month <= 9
    winter = month in (12, 1, 2)
    w = {
        "a cold and cough": 3.0 + (2.0 if winter else 0.0), "a fever": 2.0, "back pain": 1.0 if age >= 25 else 0.2,
        "a stomach bug": 1.2 + (1.5 if monsoon else 0.0), "a bad fever": 0.8, "high blood pressure": 0.9 if age >= 40 else 0.0,
        "a broken bone": 0.3, "dengue": 0.6 if monsoon else 0.02, "pneumonia": 0.15 + (0.4 if age >= 65 or age < 5 else 0.0) + (0.2 if winter else 0.0),
        "a heart problem": 0.35 if age >= 55 else 0.0,
    }
    v = np.array([w[i.name] for i in ILLNESSES])
    return v / v.sum()


def is_doctor(w: World, p: Person) -> bool:
    return p.job is not None and w.city.buildings[p.job.building].kind == "hospital" and p.skill >= DOCTOR_SKILL


def style(p: Person) -> dict[str, float]:
    """How a doctor works, from who they are."""
    return {"care": p.agreeableness, "thoroughness": p.conscientiousness, "calm": 1.0 - p.neuroticism, "experience": p.skill}


def age_group(age: float) -> str:
    return "children" if age < 13 else "older people" if age >= 65 else "adults"


class Health:
    def __init__(self, world: World) -> None:
        self.w = world
        self.visits: deque[dict[str, Any]] = deque(maxlen=4000)  # every consultation, newest last
        self.seen_today: dict[int, int] = defaultdict(int)  # doctor -> patients seen this shift-day
        self.arrivals: deque[tuple[int, int]] = deque(maxlen=200)  # (minute, hospital) of recent arrivals, for the queue
        self.today = {"fell_ill": 0, "visits": 0, "recovered": 0, "wait": 0.0, "satisfaction": 0.0, "fees": 0.0}

    # ---- falling ill and getting better ----------------------------------------------------

    def nightly(self) -> dict[str, Any]:
        w = self.w
        rng = w.streams("health")
        t = w.t
        month = SimTime(t).datetime.month
        for p in w.alive():
            if p.illness is not None:
                if t >= p.well_at:
                    p.illness, p.severity, p.seen_doctor = None, 0, False
                    self.today["recovered"] += 1
                elif p.severity >= 2 and not p.seen_doctor and t - p.ill_since > 2 * MINUTES_PER_DAY:
                    # untreated, it drags on and wears them down
                    p.health = max(0.05, p.health - 0.02 * p.severity)
                    p.well_at += MINUTES_PER_DAY // 2
                continue
            age = p.age(t)
            if age >= 18 and rng.random() < (1 / 60 if age >= 60 else 1 / 200):
                p.illness, p.severity, p.ill_since, p.seen_doctor, p.wants_doctor = CHECKUP, 1, t, False, True
                p.well_at = t + 2 * MINUTES_PER_DAY
                continue
            chance = (0.0025 + 0.00005 * max(0.0, age - 45) + 0.003 * (1.0 - p.health) + (0.0015 if age < 6 else 0.0)
                      + (0.0012 if 6 <= month <= 9 else 0.0) + (0.0006 if month in (12, 1) else 0.0) + (0.0008 if p.mood < 0.3 else 0.0))
            if rng.random() >= chance:
                continue
            ill = ILLNESSES[int(rng.choice(len(ILLNESSES), p=_weights(age, month)))]
            p.illness, p.severity, p.ill_since, p.seen_doctor = ill.name, ill.severity, t, False
            p.well_at = t + int(ill.days * MINUTES_PER_DAY * float(rng.uniform(1.1, 1.5)))  # slower if nobody treats it
            p.wants_doctor = bool(rng.random() < SEE_DOCTOR[ill.severity]) and age >= 6
            self.today["fell_ill"] += 1
            if ill.severity == 3:
                w.emit("sick", f"{p.name} came down with {ill.name}.", (p.id,), illness=ill.name, severity=ill.severity)
        visits = self.today["visits"]
        row = {
            "sick": sum(1 for p in w.alive() if p.illness not in (None, CHECKUP)),
            "fell_ill": self.today["fell_ill"],
            "recovered": self.today["recovered"],
            "hospital_visits": visits,
            "hospital_wait": round(self.today["wait"] / visits, 1) if visits else None,
            "patient_satisfaction": round(self.today["satisfaction"] / visits, 3) if visits else None,
            "doctors": sum(1 for p in w.alive() if is_doctor(w, p)),
        }
        self.today = {"fell_ill": 0, "visits": 0, "recovered": 0, "wait": 0.0, "satisfaction": 0.0, "fees": 0.0}
        self.seen_today = defaultdict(int)
        return row

    # ---- at the hospital -------------------------------------------------------------------------

    def needs_doctor(self, p: Person) -> bool:
        return p.illness is not None and p.wants_doctor and not p.seen_doctor

    def consult(self, p: Person, hospital: int, t: int) -> int:
        """A patient arrives: wait, see a doctor, pay, go home with a diagnosis. Returns when they leave."""
        w = self.w
        rng = w.streams("health")
        age = p.age(t)
        doctors = [q for q in (w.people[i] for i in w.job_holders.get(hospital, []))
                   if is_doctor(w, q) and q.activity == WORK and q.place == hospital]
        while self.arrivals and self.arrivals[0][0] < t - 60:
            self.arrivals.popleft()
        queue = sum(1 for _, h in self.arrivals if h == hospital)
        self.arrivals.append((t, hospital))
        if doctors:
            doc = min(doctors, key=lambda q: (self.seen_today[q.id], q.id))
            s = style(doc)
        else:  # nobody on duty: the duty nurse does what they can
            doc, s = None, {"care": 0.6, "thoroughness": 0.4, "calm": 0.5, "experience": 0.35}
        on_duty = max(1, len(doctors))
        wait = int(round(8 + 18 * queue / on_duty + (25 if doc is None else 0) + float(rng.uniform(0, 10))))
        tired = min(1.0, self.seen_today[doc.id] / 10.0) if doc is not None else 0.5
        # how this doctor handles this patient
        attention = 1.15 if age < 13 else 1.25 if age >= 65 else 1.0
        minutes = BASE_MINUTES[p.severity] * (0.55 + 0.9 * s["thoroughness"]) * attention * (1.0 - 0.35 * tired)
        minutes = max(4, int(round(minutes * float(rng.uniform(0.85, 1.15)))))
        kindness = s["care"] * (1.0 - 0.5 * tired * (1.0 - s["calm"])) + (0.08 if age < 13 or age >= 65 else 0.0) + (0.05 if p.severity == 3 else 0.0)
        kindness = float(np.clip(kindness + rng.normal(0, 0.05), 0.0, 1.0))
        needed = BASE_MINUTES[p.severity]
        right = 0.4 + 0.4 * s["experience"] + 0.15 * min(1.0, minutes / needed) - 0.15 * tired
        correct = bool(rng.random() < min(0.97, max(0.35, right)))
        satisfaction = round(0.45 * kindness + 0.3 * (1.0 - min(1.0, wait / 90.0)) + 0.25 * min(1.0, minutes / needed), 3)
        ill = next((i for i in ILLNESSES if i.name == p.illness), ROUTINE)
        if ill is ROUTINE:
            correct = True
        if correct:
            p.well_at = min(p.well_at, t + int(ill.days * MINUTES_PER_DAY * 0.8))
            p.seen_doctor = True
        else:  # it was missed: they'll be back if it doesn't clear up
            p.well_at = max(p.well_at, t + int(ill.days * MINUTES_PER_DAY * 1.3))
            p.wants_doctor = p.severity >= 2
            p.seen_doctor = p.severity < 2
        # the bill: a consultation fee and medicines, free for those who can't afford it
        econ = w.economy
        bill = CONSULT_FEE + MEDICINES[p.severity]
        acct = econ.person(p.id)
        if econ.balance[acct] - bill >= FREE_BELOW:
            econ.transfer(acct, "city", bill, "hospital fees")
            paid = bill
        else:
            paid = 0.0
        econ.transfer("city", "outside", MEDICINES[p.severity] * 0.8, "medicines")
        if doc is not None:
            self.seen_today[doc.id] += 1
        self.today["visits"] += 1
        self.today["wait"] += wait
        self.today["satisfaction"] += satisfaction
        visit = {"t": t, "patient": p.id, "doctor": doc.id if doc else None, "illness": p.illness, "severity": p.severity,
                 "age": round(age, 1), "group": age_group(age), "wait": wait, "minutes": minutes, "kindness": round(kindness, 3),
                 "correct": correct, "satisfaction": satisfaction, "tired": round(tired, 2), "paid": paid,
                 "nth": self.seen_today[doc.id] if doc else 0}
        self.visits.append(visit)
        who = f"Dr. {doc.name}" if doc else "The duty nurse"
        manner = ("a rushed" if tired > 0.6 and minutes < needed else "a careful" if minutes >= needed * 1.2 else "a")
        heal = round((p.well_at - t) / MINUTES_PER_DAY)
        outcome = ("All clear." if p.illness == CHECKUP else
                   f"Expected to be well in about {max(1, heal)} {'day' if heal <= 1 else 'days'}." if correct else
                   "The diagnosis was wrong, so getting better may take longer.")
        w.emit("treated", f"{who} saw {p.name} for {p.illness} after a {wait}-minute wait: {manner} {minutes}-minute visit. "
               + outcome + ("" if paid else " Treated free."),
               (p.id,) + ((doc.id,) if doc else ()), hospital, doctor=doc.id if doc else None, wait=wait, minutes=minutes, correct=correct, satisfaction=satisfaction)
        return t + wait + minutes

    # ---- views ------------------------------------------------------------------------------------

    def doctor_stats(self, since: int = 0) -> list[dict[str, Any]]:
        w = self.w
        by: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for v in self.visits:
            if v["doctor"] is not None and v["t"] >= since:
                by[v["doctor"]].append(v)
        out = []
        for p in w.alive():
            if not is_doctor(w, p):
                continue
            vs = by.get(p.id, [])
            n = len(vs)
            out.append({
                "id": p.id, "name": p.name, "style": {k: round(v, 2) for k, v in style(p).items()}, "patients": n,
                "minutes": round(sum(v["minutes"] for v in vs) / n, 1) if n else None,
                "kindness": round(sum(v["kindness"] for v in vs) / n, 2) if n else None,
                "right": round(sum(v["correct"] for v in vs) / n, 2) if n else None,
                "satisfaction": round(sum(v["satisfaction"] for v in vs) / n, 2) if n else None,
            })
        return sorted(out, key=lambda d: (-d["patients"], d["id"]))

    def behaviour(self, since: int = 0) -> dict[str, Any]:
        """How check-ups change from patient to patient: by age, seriousness and how tired the doctor is."""
        vs = [v for v in self.visits if v["t"] >= since and v["doctor"] is not None]

        def avg(sel: list[dict[str, Any]]) -> dict[str, Any] | None:
            if not sel:
                return None
            n = len(sel)
            return {"visits": n, "minutes": round(sum(v["minutes"] for v in sel) / n, 1), "kindness": round(sum(v["kindness"] for v in sel) / n, 2),
                    "right": round(sum(v["correct"] for v in sel) / n, 2)}

        return {
            "by_age": {g: avg([v for v in vs if v["group"] == g]) for g in ("children", "adults", "older people")},
            "by_severity": {SEVERITY[s]: avg([v for v in vs if v["severity"] == s]) for s in (1, 2, 3)},
            "by_shift": {"first 3 patients": avg([v for v in vs if v["nth"] <= 3]), "4th to 9th": avg([v for v in vs if 4 <= v["nth"] <= 9]),
                         "10th and later": avg([v for v in vs if v["nth"] >= 10])},
        }

    def view(self) -> dict[str, Any]:
        w = self.w
        month = w.t - 30 * MINUTES_PER_DAY
        sick = [p for p in w.alive() if p.illness not in (None, CHECKUP)]
        recent = [v for v in self.visits if v["t"] >= month]
        n = len(recent)
        return {
            "sick": len(sick),
            "by_illness": dict(sorted(((name, sum(1 for p in sick if p.illness == name)) for name in {p.illness for p in sick}), key=lambda kv: -kv[1])),
            "month": {"visits": n, "wait": round(sum(v["wait"] for v in recent) / n, 1) if n else None,
                      "satisfaction": round(sum(v["satisfaction"] for v in recent) / n, 2) if n else None,
                      "right": round(sum(v["correct"] for v in recent) / n, 2) if n else None,
                      "free": sum(1 for v in recent if not v["paid"])},
            "doctors": self.doctor_stats(month),
            "behaviour": self.behaviour(month),
        }


# ---- happiness ---------------------------------------------------------------------------------------

def satisfaction(w: World, p: Person) -> dict[str, float]:
    """Life satisfaction, 0..1, and the five things it's made of."""
    t = w.t
    econ = w.economy
    acct = econ.person(p.id)
    bal = econ.balance.get(acct, 0.0)
    money = float(np.clip(bal / 3000.0, 0.0, 1.0)) * (0.6 if econ._debt(acct) > 0 else 1.0)
    age = p.age(t)
    if p.job is not None or p.school is not None:
        work = 0.85
    elif p.retired or age < 18:
        work = 0.8
    else:
        work = 0.3  # looking for work
    friends = min(1.0, len(w.social.friends(p.id)) / 8.0)
    health = p.health * (0.5 if p.severity >= 2 else 0.85 if p.severity == 1 and p.illness != CHECKUP else 1.0)
    feelings = float(np.clip(0.7 + 0.6 * (p.joy - 0.4) - 0.6 * p.sadness - 0.4 * p.fear - 0.3 * p.anger, 0.0, 1.0))
    parts = {"day": p.mood, "money": money, "work": work, "friends": friends, "health": health, "feelings": feelings}
    score = 0.2 * parts["day"] + 0.18 * money + 0.17 * work + 0.15 * friends + 0.15 * health + 0.15 * feelings
    if p.activity == JAIL:
        score *= 0.4
    parts["score"] = float(np.clip(score, 0.0, 1.0))
    return parts


def nightly_happiness(w: World) -> dict[str, Any]:
    adults = [p for p in w.alive() if p.age(w.t) >= 18]
    if not adults:
        return {"happiness": None}
    tax, other = [], []
    for p in adults:
        s = satisfaction(w, p)["score"]
        p.happiness = s
        (tax if p.job is not None and not p.cash_job else other).append(s)
    mean = lambda xs: round(100 * sum(xs) / len(xs), 1) if xs else None  # noqa: E731
    return {"happiness": mean(tax + other), "happiness_taxpayers": mean(tax), "happiness_others": mean(other)}


def happiness_view(w: World) -> dict[str, Any]:
    adults = [p for p in w.alive() if p.age(w.t) >= 18]
    if not adults:
        return {}
    parts = [satisfaction(w, p) for p in adults]
    keys = ("day", "money", "work", "friends", "health", "feelings")
    avg = {k: round(100 * sum(x[k] for x in parts) / len(parts), 1) for k in keys + ("score",)}
    by_district: dict[str, list[float]] = defaultdict(list)
    for p, x in zip(adults, parts):
        by_district[w.city.buildings[w.households[p.household].home].district].append(x["score"])
    groups = {
        "with a job": [x["score"] for p, x in zip(adults, parts) if p.job is not None],
        "looking for work": [x["score"] for p, x in zip(adults, parts) if p.job is None and p.unemployed_since is not None and not p.retired],
        "retired": [x["score"] for p, x in zip(adults, parts) if p.retired],
        "ill right now": [x["score"] for p, x in zip(adults, parts) if p.illness not in (None, CHECKUP)],
    }
    return {
        "index": avg["score"],
        "parts": {k: avg[k] for k in keys},
        "districts": {d: round(100 * sum(v) / len(v), 1) for d, v in sorted(by_district.items())},
        "groups": {g: (round(100 * sum(v) / len(v), 1) if v else None) for g, v in groups.items()} | {"counts": {g: len(v) for g, v in groups.items()}},
    }


__all__ = ["Health", "HOSPITAL", "nightly_happiness", "happiness_view", "is_doctor", "satisfaction"]
