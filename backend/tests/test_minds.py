"""Minds that differ, grow and rub off on each other; and an Ask that keeps up with the city by itself."""

import copy
import statistics

import pytest

from citylab.config import Settings
from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.mind import TOPICS, independence
from citylab.core.people import EAT_OUT, HOSPITAL, learn
from citylab.core.world import World
from citylab.services.runner import Runner

DAY = MINUTES_PER_DAY


@pytest.fixture(scope="module")
def town():
    w = World(seed=8, population=600)
    w.advance(6 * DAY + 19 * 60)  # an evening in the first week
    return w


def _adults(w):
    return [p for p in w.alive() if p.age(w.t) >= 18]


# ---- people think differently ------------------------------------------------------------------


def test_views_stay_varied_instead_of_melting_into_one(town):
    adults = _adults(town)
    for k in TOPICS:
        v = [p.opinions.get(k, 0.0) for p in adults]
        assert statistics.pstdev(v) > 0.12, k
    # every topic has its fans and its critics
    for k in ("taxes", "police", "council"):
        assert any(p.opinions[k] > 0.15 for p in adults) and any(p.opinions[k] < -0.15 for p in adults), k


def test_the_same_moment_brings_different_choices_from_different_minds(town):
    w = copy.deepcopy(town)
    me = next(p for p in _adults(w) if p.job is not None and p.place is not None)
    picks = set()
    for other in _adults(w)[:150]:
        clone = copy.copy(me)
        for trait in ("openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism", "joy", "sadness", "fear"):
            setattr(clone, trait, getattr(other, trait))
        clone.likes, clone.ways, clone.opinions = dict(other.likes), dict(other.ways), dict(other.opinions)
        clone.hunger, clone.energy, clone.social, clone.fun = 0.5, 0.6, 0.4, 0.4
        best = max(w.brain.options(clone, w.t))
        picks.add((best[1], best[2]))
    assert len(picks) >= 4  # the same evening, the same place: home, a meal out, a friend, the park...


# ---- minds grow from experience -----------------------------------------------------------------


def test_a_bad_meal_changes_where_they_eat_next(town):
    w = copy.deepcopy(town)
    p = next(p for p in _adults(w) if p.place is not None)
    p.hunger = 0.2
    w.economy.balance[w.economy.person(p.id)] = 50_000.0
    meals = [o for o in w.brain.options(p, w.t) if o[1] == EAT_OUT]
    if len(meals) < 2:
        pytest.skip("only one restaurant open nearby at this hour")
    best = max(meals)
    for _ in range(4):  # four bad experiences in a row
        learn(p.likes, best[2], -1.0)
    after = {o[2]: o[0] for o in w.brain.options(p, w.t) if o[1] == EAT_OUT}
    assert after[best[2]] < best[0] - 0.4
    assert max(after, key=after.get) != best[2]  # they'd go somewhere else now


def test_people_build_their_own_habits_over_time(town):
    adults = _adults(town)
    assert sum(1 for p in adults if p.likes) > len(adults) * 0.5  # most have tried places and remember them
    assert sum(1 for p in adults if p.ways) > len(adults) * 0.2  # and have a feel for how to get about
    favourites = {max(p.likes, key=p.likes.get) for p in adults if p.likes}
    assert len(favourites) >= 10  # not one favourite for everyone


def test_leanings_drift_towards_what_life_keeps_telling_them(town):
    w = copy.deepcopy(town)
    p = next(p for p in _adults(w) if p.leanings)
    p.opinions["buses"], p.leanings["buses"] = -0.9, 0.0  # far gloomier about the buses than the rest of town
    w.mind._experience(_adults(w))
    assert p.leanings["buses"] < 0.0


# ---- person to person ---------------------------------------------------------------------------


def test_a_view_spreads_to_friends_not_strangers(town):
    a, b = copy.deepcopy(town), copy.deepcopy(town)
    hubs = sorted(_adults(b), key=lambda p: (-len(b.social.friends(p.id)), p.id))[:3]
    for h in hubs:
        b.people[h.id].opinions["buses"], b.people[h.id].leanings["buses"] = -1.0, -0.8
    friends = {q for h in hubs for q, _ in b.social.top_friends(h.id, 6)} - {h.id for h in hubs}
    far = {p.id for p in _adults(b)} - friends - {h.id for h in hubs}
    far -= {r for q in friends for r, _ in b.social.top_friends(q, 6)}
    a.advance(3 * DAY)
    b.advance(3 * DAY)

    def moved(ids):
        ids = [i for i in ids if a.people[i].alive and b.people[i].alive and "buses" in a.people[i].opinions]
        return sum(b.people[i].opinions["buses"] - a.people[i].opinions["buses"] for i in ids) / len(ids)

    assert moved(friends) < -0.01  # friends of the bus-haters now like the buses less
    assert abs(moved(far)) < abs(moved(friends)) / 3


def test_views_far_from_your_own_sway_you_less(town):
    w = copy.deepcopy(town)
    p = next(p for p in _adults(w) if w.social.top_friends(p.id, 6))
    friends = [q for q, _ in w.social.top_friends(p.id, 6)]
    shifts = []
    for theirs in (0.3, 1.0):  # a friendly nudge, then a view from the other end of the scale
        for q in friends:
            w.people[q].opinions["taxes"] = theirs
        p.opinions["taxes"] = 0.0
        w.mind._talk([p] + [w.people[q] for q in friends])
        shifts.append(p.opinions["taxes"] / theirs)
    assert shifts[1] < shifts[0]  # per unit of disagreement, the far view moved them less


def test_agreeable_people_go_along_more(town):
    p = copy.copy(_adults(town)[0])
    p.openness, p.agreeableness = 0.2, 0.9
    follower = independence(p)
    p.openness, p.agreeableness = 0.9, 0.2
    assert independence(p) > follower


def test_tips_travel_by_word_of_mouth(town):
    w = copy.deepcopy(town)
    p = next(p for p in _adults(w) if w.social.top_friends(p.id, 6))
    friend = w.people[w.social.top_friends(p.id, 6)[0][0]]
    clinic = next(b.id for b in w.city.buildings if b.kind == "clinic")
    p.likes.pop(clinic, None)
    friend.likes = {clinic: 0.9}
    w.mind._talk([p, friend])
    assert p.likes.get(clinic, 0.0) > 0.0


# ---- clinics, the informal economy, new ways to travel -----------------------------------------


def test_families_with_money_go_private_and_the_poor_go_to_the_hospital(town):
    w = copy.deepcopy(town)
    w.advance((w.t // DAY + 1) * DAY + 10 * 60 - w.t)  # ten in the morning: clinics and the hospital are open
    p = next(p for p in _adults(w) if p.place is not None)
    p.illness, p.severity, p.wants_doctor, p.seen_doctor = "a fever", 2, True, False
    p.likes = {}
    p.opinions["hospital"] = 0.0
    acct = w.economy.person(p.id)

    def where(balance):
        w.economy.balance[acct] = balance
        docs = [o for o in w.brain.options(p, w.t) if o[1] == HOSPITAL]
        return w.city.buildings[max(docs)[2]].kind

    assert where(80_000.0) == "clinic"
    assert where(1_700.0) == "hospital"


def test_a_clinic_visit_is_paid_to_the_clinic_and_remembered(town):
    w = copy.deepcopy(town)
    clinic = next(b.id for b in w.city.buildings if b.kind == "clinic")
    p = next(p for p in _adults(w) if w.economy.balance[w.economy.person(p.id)] > 5000)
    p.illness, p.severity = "a fever", 2
    money, before = w.economy.total(), w.economy.balance[w.economy.company(clinic)]
    w.health.consult(p, clinic, w.t)
    assert w.economy.balance[w.economy.company(clinic)] > before
    assert clinic in p.likes
    assert abs(w.economy.total() - money) < 0.01


def test_vendors_maids_and_labourers_earn_without_a_payslip(town):
    rows = town.daily
    assert rows[-1]["vendors"] > 0 and rows[-1]["maids"] > 0 and rows[-1]["labourers"] > 0
    assert sum(r["vendor_takings"] for r in rows) > 0
    assert sum(r["maid_pay"] for r in rows) > 0
    assert sum(r["naka_hired"] for r in rows) > 0
    traders = [p for p in town.alive() if p.trade]
    assert all(p.job is None and p.unemployed_since is None for p in traders)


def test_cycles_and_shared_autos_are_part_of_the_mix(town):
    rows = town.daily
    assert sum(r.get("trips_cycle", 0) for r in rows) > 0
    assert sum(r.get("trips_shared", 0) for r in rows) > 0


# ---- Ask keeps up by itself ----------------------------------------------------------------------


def test_ask_reads_new_events_as_they_happen():
    r = Runner(Settings(seed=6, population=300, start_playing=False, database_url="", ollama_url=""))
    r.step(DAY)
    first = r.asker.ask("Who found a job?")
    n = len(r.asker.index.ids)
    r.step(2 * DAY)
    assert r.asker.ask("Who found a job?")["answer"] != first["answer"] or len(r.asker.index.ids) > n
    assert len(r.asker.index.ids) > n  # the new days' events were indexed without anyone asking for it
    with r.lock:
        e = r.world.emit("opened", "Zarine's Sweet Mart opened its doors on Laxmi Road.")
    ans = r.asker.ask("When did Zarine's Sweet Mart open?")
    assert any(s["id"] == e.id for s in ans["sources"])
    assert "Sweet Mart" in ans["answer"]
