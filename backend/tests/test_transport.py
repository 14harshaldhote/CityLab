from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.routing import BUS, WAIT
from citylab.core.transport import ROUTES, WIDE, Transport
from citylab.core.world import World


def _morning(seed=6, population=600):
    """A weekday morning: day 1 (a Friday) at 08:30."""
    w = World(seed=seed, population=population)
    w.advance(MINUTES_PER_DAY + 8 * 60 + 30)
    return w


def test_bus_network_reaches_across_the_city():
    w = World(seed=6, population=200)
    net = w.transport.network()
    assert [line["number"] for line in net["lines"]] == [n for n, _, _ in ROUTES]
    names = [s["name"] for s in net["stops"]]
    assert len(names) >= 25 and len(set(names)) == len(names)  # every stop has its own name
    for line in net["lines"]:
        nodes = line["nodes"]
        assert all(w.city.graph.has_edge(a, b) for a, b in zip(nodes, nodes[1:]))  # buses only drive on streets
        assert len(line["stops"]) >= 5
    ring = next(line for line in net["lines"] if line["number"] == "3")
    assert ring["nodes"][0] == ring["nodes"][-1]


def test_rush_hour_mixes_walking_cars_buses_and_autos():
    w = _morning()
    trips = w.transport.today.trips
    assert trips["walk"] > 0 and trips["car"] > 0 and trips["bus"] > 0 and trips["auto"] > 0
    assert w.transport.active(w.t), "buses should be on the road"
    frame = w.frame()
    assert len(frame["move"]) == len(frame["ids"]) and frame["buses"]
    assert all(len(b) == 6 for b in frame["buses"])
    # money: fares reach the city, petrol and autos are paid to the outside world, nothing leaks
    flows = w.economy.flows
    assert flows["bus fares"] > 0 and flows["petrol"] > 0 and flows["bus diesel"] > 0


def test_bus_riders_wait_at_the_stop_and_ride_with_the_bus():
    w = _morning()
    riders = [p for p in w.alive() if p.trip is not None and p.trip.mode == "bus"]
    assert riders
    for p in riders:
        trip = p.trip
        assert all(b >= a - 1e-9 for a, b in zip(trip.times, trip.times[1:]))
        run, k0, k1 = trip.run
        board = trip.legs.index(WAIT)
        # they stand at the stop until the bus comes, then move exactly as it does
        assert trip.points[board] == run.route.xy[k0]
        assert abs(trip.times[board + 1] - run.times[k0]) < 1e-6
        rides = [i for i, leg in enumerate(trip.legs) if leg == BUS]
        assert len(rides) == k1 - k0
        mid = (run.times[k0] + run.times[k1]) / 2
        assert trip.leg(mid) == BUS
        assert all(run.load[k] >= 1 for k in range(k0, k1))
        assert w.transport.describe(p, int(trip.times[board])) is not None


def test_crowded_streets_slow_down():
    w = World(seed=6, population=200)
    tr: Transport = w.transport
    a, b = next(iter(sorted(w.city.graph.edges())))
    t = 3 * 60  # night: empty streets
    empty = tr._drive([a, b], t, "car", record=False)
    for _ in range(20):
        tr._drive([a, b], t, "car", record=True)
    jammed = tr._drive([a, b], t, "car", record=False)
    assert jammed[-1] - t > 2 * (empty[-1] - t)
    # two more lanes take more traffic
    e = (a, b) if a < b else (b, a)
    before = tr.capacity(e)
    w.city.graph.edges[e]["lanes"] = 2
    assert tr.capacity(e) == before * WIDE


def test_public_works_widens_a_street_that_keeps_jamming():
    w = World(seed=6, population=200)
    w.economy.transfer("outside", "city", 500_000, "test grant")
    e = tuple(sorted(next(iter(w.city.graph.edges()))))
    w.transport.jam_days[e] = [0, 1, 2, 3, 4]
    news = []
    w.bus.subscribe("roads", news.append)
    w.government._widen()
    assert w.government.widening and e in w.city.widening
    assert w.city.graph.edges[e].get("works")
    for _ in range(10):
        w.government._widen()
    assert w.city.graph.edges[e]["lanes"] == 2
    assert not w.city.widening
    assert w.city.to_dict()["wide"] == [list(e)]
    assert "started widening" in news[0].text and "four lanes" in news[-1].text
