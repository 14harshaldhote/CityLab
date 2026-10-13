import math

import networkx as nx
import pytest

from citylab.core.citygen import TYPES, generate_city
from citylab.core.clock import MINUTES_PER_DAY, SimTime, minutes
from citylab.core.events import Event, EventBus
from citylab.core.rng import Streams, stable_hash
from citylab.core.routing import Router
from citylab.core.weather import Weather
from citylab.storage.memory import MemoryStore


def test_clock_decodes_minutes():
    st = SimTime(minutes(days=1, hours=8, mins=30))
    assert st.day == 1 and st.minute_of_day == 510 and st.hour == 8.5
    assert SimTime(0).weekday == 3  # 1 Jan 2026 was a Thursday
    assert SimTime(minutes(days=2)).is_weekend  # Saturday
    assert SimTime(0).label() == "Thu 01 Jan 2026 00:00"


def test_streams_are_independent_and_repeatable():
    a, b = Streams(7), Streams(7)
    x1 = a("births").random(5)
    a("crime").random(100)  # drawing from another stream must not disturb births
    x2 = a("births").random(5)
    assert list(b("births").random(5)) == list(x1)
    assert list(b("births").random(5)) == list(x2)
    assert stable_hash("a", 1) == stable_hash("a", 1) != stable_hash("a", 2)


def test_event_bus_numbers_and_routes_events():
    bus = EventBus()
    seen, births = [], []
    bus.subscribe("*", seen.append)
    bus.subscribe("birth", births.append)
    bus.publish(Event(t=1, kind="birth", text="x", people=(1, 2)))
    bus.publish(Event(t=2, kind="death", text="y", people=(3,)))
    assert [e.id for e in seen] == [0, 1]
    assert len(births) == 1


def test_memory_store_queries_newest_first():
    store = MemoryStore()
    for i in range(5):
        e = Event(t=i, kind="birth" if i % 2 else "death", text=str(i), people=(i % 2,))
        e.id = i
        store(e)
    assert [e.id for e in store.query(limit=2)] == [4, 3]
    assert [e.id for e in store.query(kind="birth")] == [3, 1]
    assert [e.id for e in store.query(person=0)] == [4, 2, 0]


def test_weather_is_deterministic_in_any_order():
    w1, w2 = Weather(3), Weather(3)
    t = 180 * MINUTES_PER_DAY + 13 * 60
    late = w1.at(t)
    w2.at(5)
    assert w2.at(t) == late
    noon, midnight = w1.at(10 * MINUTES_PER_DAY + 12 * 60 + 30), w1.at(10 * MINUTES_PER_DAY)
    assert noon.phase == 3 and noon.sun_elevation_deg > 30
    assert midnight.phase == 0 and midnight.dark


def test_monsoon_is_wetter_than_winter():
    w = Weather(1)
    rain = lambda d0: sum(w.at((d0 + d) * MINUTES_PER_DAY + h * 60).rain_mm_h for d in range(60) for h in range(24))  # noqa: E731
    assert rain(181) > 5 * rain(0)  # July-August vs January-February


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_city_is_connected_and_complete(seed):
    city = generate_city(seed)
    assert nx.is_connected(city.graph)
    kinds = {b.kind for b in city.buildings}
    for k in ("home", "office", "shop", "restaurant", "school", "hospital", "police", "city_hall", "bank", "park"):
        assert k in kinds
    assert sum(1 for b in city.buildings if b.kind == "city_hall") == 1
    for b in city.buildings:
        assert b.node in city.graph
        assert len(b.jobs) == TYPES[b.kind].jobs
    # buildings never overlap
    rects = [(b.x, b.y, b.x + b.w, b.y + b.h) for b in city.buildings]
    for i, a in enumerate(rects):
        for c in rects[i + 1 :]:
            assert a[2] <= c[0] or c[2] <= a[0] or a[3] <= c[1] or c[3] <= a[1]


def test_same_seed_same_city():
    a, b = generate_city(5), generate_city(5)
    assert [x.to_dict() for x in a.buildings] == [x.to_dict() for x in b.buildings]
    assert sorted(a.graph.edges()) == sorted(b.graph.edges())


def test_routes_follow_streets():
    city = generate_city(1)
    router = Router(city)
    homes, offices = city.of_kind("home"), city.of_kind("office")
    src, dst = homes[0], offices[-1]
    trip = router.trip(src, dst, depart=100, has_car=False)
    straight = math.hypot(src.x - dst.x, src.y - dst.y)
    assert trip.cumulative[-1] >= straight - 1
    assert trip.mode == "walk" and trip.arrive > trip.depart
    assert trip.position(trip.depart) == trip.points[0]
    assert trip.position(trip.arrive) == trip.points[-1]
    mid = trip.position((trip.depart + trip.arrive) // 2)
    assert 0 <= mid[0] <= city.size + 300 and 0 <= mid[1] <= city.size + 300
    car = router.trip(src, dst, depart=100, has_car=True)
    if car.mode == "car":
        assert car.arrive - car.depart < trip.arrive - trip.depart
