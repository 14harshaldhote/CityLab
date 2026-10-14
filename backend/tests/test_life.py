"""Doctors and patients, feelings and opinions, happiness and tax dodging."""

import copy
import statistics

import pytest

from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.health import is_doctor
from citylab.core.mind import FEELINGS
from citylab.core.people import WORK
from citylab.core.world import World

DAY = MINUTES_PER_DAY


@pytest.fixture(scope="module")
def city():
    w = World(seed=3, population=500)
    w.advance(9 * DAY + 10 * 60)  # a weekday morning in the second week, doctors on shift
    return w


def _hospital(w):
    return next(b.id for b in w.city.buildings if b.kind == "hospital")


def _patient(w, faith=None):
    p = next(p for p in w.alive() if p.age(w.t) >= 18 and (faith is None or p.religion == faith))
    p.illness, p.severity = "a fever", 2
    return p


def test_doctors_are_people_with_their_own_ways(city):
    docs = [p for p in city.alive() if is_doctor(city, p)]
    assert docs
    stats = city.health.doctor_stats()
    assert {d["id"] for d in stats} == {p.id for p in docs}
    assert len({tuple(d["style"].values()) for d in stats}) == len(stats)  # every doctor works in their own way


def test_faith_never_changes_treatment(city):
    a = copy.deepcopy(city)
    b = copy.deepcopy(city)
    pa = _patient(a)
    pb = b.people[pa.id]
    pb.illness, pb.severity = pa.illness, pa.severity
    pb.religion = next(r for r in {p.religion for p in b.alive()} if r != pa.religion)
    ta = a.health.consult(pa, _hospital(a), a.t)
    tb = b.health.consult(pb, _hospital(b), b.t)
    va, vb = a.health.visits[-1], b.health.visits[-1]
    assert ta == tb
    assert {k: va[k] for k in ("doctor", "wait", "minutes", "kindness", "correct", "satisfaction")} == \
           {k: vb[k] for k in ("doctor", "wait", "minutes", "kindness", "correct", "satisfaction")}


def test_tired_doctors_rush(city):
    w = copy.deepcopy(city)
    hosp = _hospital(w)
    for d in (p for p in w.alive() if is_doctor(w, p)):  # put every doctor on shift, at the start of their day
        d.activity, d.place = WORK, hosp
    w.health.seen_today.clear()
    patients = [p for p in w.alive() if p.age(w.t) >= 18][:100]  # a crowded morning: enough for every doctor to tire
    for p in patients:
        p.illness, p.severity = "a fever", 2
        w.health.consult(p, hosp, w.t)
    vs = [v for v in list(w.health.visits)[-100:] if v["doctor"] is not None]
    early = [v["minutes"] for v in vs if v["nth"] <= 3]
    late = [v["minutes"] for v in vs if v["nth"] >= 6]
    assert early and late
    assert sum(late) / len(late) < sum(early) / len(early)


def test_people_get_ill_and_see_doctors(city):
    rows = city.daily
    assert sum(r["hospital_visits"] for r in rows) > 0
    assert sum(r["fell_ill"] for r in rows) > 0
    assert city.health.visits and all(v["wait"] >= 0 and v["minutes"] >= 4 for v in city.health.visits)


def test_feelings_follow_what_happens(city):
    w = copy.deepcopy(city)
    p = next(p for p in w.alive() if p.age(w.t) >= 25)
    before = p.sadness, p.anger, p.opinions.get("jobs", 0.0)
    w.emit("laid_off", f"Somewhere laid off {p.name} to cut costs.", (p.id,))
    assert p.sadness > before[0] and p.anger > before[1] and p.opinions["jobs"] < before[2]


def test_festivals_cheer_only_their_own_faith(city):
    w = copy.deepcopy(city)
    faith = w.alive()[0].religion
    joy = {p.id: p.joy for p in w.alive()}
    w.emit("festival", "A festival.", faith=faith)
    for p in w.alive():
        if p.religion == faith and joy[p.id] < 1.0:
            assert p.joy > joy[p.id]
        elif p.religion != faith:
            assert p.joy == joy[p.id]


def test_feelings_and_opinions_differ_between_people(city):
    adults = [p for p in city.alive() if p.age(city.t) >= 18]
    for f in FEELINGS:
        assert 0.0 <= min(getattr(p, f) for p in adults) and max(getattr(p, f) for p in adults) <= 1.0
    for k in ("taxes", "police", "buses", "jobs", "council", "hospital"):  # people think for themselves
        xs = [p.opinions.get(k, 0.0) for p in adults]
        assert statistics.pstdev(xs) > 0.1 and min(xs) < 0 < max(xs)
    moods = city.mind.poll["moods"]
    assert len(moods) >= 3  # not everyone feels the same


def test_happiness_index(city):
    rows = city.daily
    assert all(0 <= r["happiness"] <= 100 for r in rows if r.get("happiness") is not None)
    assert rows[-1]["happiness"] is not None


def test_reputation(city):
    celebs = city.mind.celebrities(5)
    assert celebs and all(c["known_for"] for c in celebs)
    assert celebs == sorted(celebs, key=lambda c: -c["fame"])


def test_tax_dodging_keeps_the_books_balanced_and_audits_recover_it():
    w = World(seed=5, population=500)
    audits = []
    w.bus.subscribe("tax_audit", audits.append)
    w.advance(15 * DAY)  # the economy asserts every night that no money leaks; two weekly audit rounds happen
    rows = w.daily
    assert sum(r["tax_dodged"] for r in rows) > 0
    assert audits
    recovered = sum(float((r.get("city_in") or {}).get("back taxes and fines", 0.0)) for r in rows)
    assert recovered == pytest.approx(sum(e.data["paid"] for e in audits), abs=0.05)
    for e in audits:
        assert e.data["paid"] == pytest.approx(e.data["dodged"] * 1.5, abs=0.05)


def test_illness_keeps_people_home(city):
    from citylab.core.brain import Brain
    from citylab.core.people import WORK

    p = copy.copy(next(p for p in city.alive() if p.job is not None))
    p.illness, p.severity = "pneumonia", 3
    assert Brain._sick(p, (5.0, WORK, 0, 0))[0] < 1.0
    p.illness, p.severity = "a cold and cough", 1
    assert 1.0 < Brain._sick(p, (5.0, WORK, 0, 0))[0] < 5.0
