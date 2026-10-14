import hashlib
import time

from fastapi.testclient import TestClient

from citylab.config import Settings
from citylab.core import policy, reports
from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.world import World
from citylab.main import create_app
from citylab.services.history import KEEP_EVERY_DAY, History, freeze, thaw

DAY = MINUTES_PER_DAY


def client() -> TestClient:
    settings = Settings(seed=6, population=200, start_playing=False, database_url="")
    return TestClient(create_app(settings, background=False))


def fingerprint(w: World) -> str:
    h = hashlib.sha256()
    for p in sorted(w.people.values(), key=lambda p: p.id):
        h.update(repr((p.id, p.alive, p.place, p.activity, p.until, round(p.hunger, 9), p.job and p.job.building)).encode())
    h.update(repr(sorted((k, round(v, 4)) for k, v in w.economy.balance.items())).encode())
    h.update(repr([(c.kind, c.t, c.status) for c in w.crime.cases.values()]).encode())
    return h.hexdigest()


def test_a_snapshot_replays_exactly():
    w = World(seed=6, population=200)
    w.advance(DAY + 7 * 60)
    blob, events = freeze(w), w.bus.count
    assert w.bus is not None and len(blob) < 2_000_000
    copy = thaw(blob, events)
    w.advance(DAY)
    copy.advance(DAY)
    assert fingerprint(copy) == fingerprint(w)
    assert copy.bus.count == w.bus.count  # the same events, told in the same order


def test_history_keeps_recent_days_and_thins_older_ones():
    h = History()
    w = World(seed=6, population=50)
    for day in range(0, 60):
        w.t = day * DAY
        h.capture(w)
    days = sorted(t // DAY for t in h.snaps)
    assert days[-KEEP_EVERY_DAY:] == list(range(60 - KEEP_EVERY_DAY, 60))
    assert all(d % 7 == 0 for d in days[:-KEEP_EVERY_DAY]) and 0 in days
    assert h.nearest(40 * DAY + 5).t == 40 * DAY
    h.truncate_after(45 * DAY)
    assert max(h.snaps) == 45 * DAY and h.horizon == 45 * DAY


def test_going_back_in_time_shows_the_city_as_it_was():
    with client() as c:
        c.post("/api/control", json={"advance_minutes": DAY + 10 * 60})
        then = c.get("/api/frame").json()
        events_then = c.get("/api/events?limit=500").json()
        c.post("/api/control", json={"advance_minutes": DAY})
        assert c.get("/api/history").json()["horizon"] == 2 * DAY + 10 * 60
        back = c.post("/api/travel", json={"t": DAY + 10 * 60}).json()
        assert back["t"] == DAY + 10 * 60
        f = c.get("/api/frame").json()
        assert (f["ids"], f["x"], f["y"], f["activity"]) == (then["ids"], then["x"], then["y"], then["activity"])
        assert f["horizon"] == 2 * DAY + 10 * 60  # the future is still there to go back to
        assert [e["id"] for e in c.get("/api/events?limit=500").json()] == [e["id"] for e in events_then]
        # play forward again: the same story, no duplicate records
        c.post("/api/control", json={"advance_minutes": DAY})
        ids = [e["id"] for e in c.get("/api/events?limit=500").json()]
        assert len(ids) == len(set(ids))
        assert c.post("/api/travel", json={"t": 10**9}).json()["t"] == 2 * DAY + 10 * 60


def test_changing_a_rule_rewrites_the_future():
    with client() as c:
        c.post("/api/control", json={"advance_minutes": 2 * DAY})
        c.post("/api/travel", json={"t": DAY})
        rules = c.post("/api/rules", json={"lever": "bus_fare", "value": 0}).json()
        assert rules["bus_fare"] == 0
        hist = c.get("/api/history").json()
        assert hist["horizon"] == DAY and hist["rules"]["bus_fare"] == 0
        assert "changed the bus fare from ₹10 to ₹0" in c.get("/api/events?kind=policy").json()[0]["text"]
        assert c.post("/api/rules", json={"lever": "nonsense", "value": 1}).status_code == 422


def test_what_if_runs_two_cities_side_by_side():
    with client() as c:
        c.post("/api/control", json={"advance_minutes": 8 * 60})
        job = c.post("/api/whatif", json={"lever": "income_tax", "value": 0.4, "days": 3}).json()
        assert job["status"] == "running" and job["was"] == 0.05
        deadline = time.time() + 300
        while job["status"] == "running" and time.time() < deadline:
            time.sleep(1)
            job = c.get(f"/api/whatif/{job['id']}").json()
        assert job["status"] == "done", job["error"]
        res = job["result"]
        tax = next(m for m in res["measures"] if m["key"] == "tax")
        assert tax["changed"] > tax["same"] * 1.5  # a far higher tax collects far more
        assert len(res["same_rows"]) == len(res["changed_rows"]) == 3
        assert 0 <= res["ripple"] <= 1 and res["story"].startswith("Changing the income tax from 5% to 40%")
        assert c.post("/api/whatif", json={"lever": "income_tax", "value": 0.4, "days": 5}).status_code == 422


def test_monthly_reports_add_up():
    w = World(seed=6, population=200)
    seen = []
    w.bus.subscribe("report", seen.append)
    w.advance(32 * DAY)
    assert [e.text.split(".")[0] for e in seen] == ["Monthly report for January 2026"]
    jan, feb = reports.reports(w.daily, w.government.finished, w.city.name)[::-1]
    assert jan["complete"] and not feb["complete"] and jan["days"] == 31
    assert jan["births"] == sum(r["births"] for r in w.daily[:31])
    assert jan["population"] == w.daily[30]["population"] == feb["population_start"]
    assert "Kamalnagar" in jan["text"]


def test_levers_are_described_in_plain_words():
    assert policy.describe("income_tax", 0.25) == "25%"
    assert policy.describe("patrols", 0) == "no patrols"
    assert policy.describe("bus_fare", 20) == "₹20"
    w = World(seed=6, population=50)
    policy.apply(w, "base_rate", 0.1)
    assert w.economy.base_rate == 0.1 and policy.current(w)["base_rate"] == 0.1
