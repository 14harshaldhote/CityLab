from fastapi.testclient import TestClient

from citylab.config import Settings
from citylab.main import create_app


def client() -> TestClient:
    settings = Settings(seed=2, population=200, start_playing=False, database_url="")
    return TestClient(create_app(settings, background=False))


def test_city_frame_and_people():
    with client() as c:
        city = c.get("/api/city").json()
        assert city["buildings"] and city["edges"] and "working" in city["activities"]
        assert c.post("/api/control", json={"advance_minutes": 9 * 60}).json()["t"] == 9 * 60
        f = c.get("/api/frame").json()
        assert len(f["ids"]) == len(f["x"]) == len(f["activity"]) > 150
        assert f["label"].endswith("09:00")
        pid = f["ids"][0]
        card = c.get(f"/api/people/{pid}").json()
        assert card["name"] and "needs" in card and "personality" in card
        assert c.get("/api/people/999999").status_code == 404
        net = c.get(f"/api/people/{pid}/network").json()
        assert net["center"] == pid and net["nodes"][0]["id"] == pid
        ids = {n["id"] for n in net["nodes"]}
        assert all(l["source"] in ids and l["target"] in ids for l in net["links"])
        b = c.get(f"/api/buildings/{city['buildings'][0]['id']}").json()
        assert "inside_count" in b


def test_controls_reset_and_websocket():
    with client() as c:
        assert c.post("/api/control", json={"playing": True, "speed": 60}).json() == {"playing": True, "speed": 60.0, "t": 0}
        assert c.post("/api/control", json={"speed": 10**9}).status_code == 422
        c.post("/api/control", json={"advance_minutes": 24 * 60})
        assert len(c.get("/api/stats/daily").json()) == 1
        assert c.get("/api/events", params={"kind": "day_summary"}).json()[0]["kind"] == "day_summary"
        assert c.post("/api/reset", json={"seed": 3, "population": 100}).json()["population"] >= 95
        with c.websocket_connect("/api/ws") as ws:
            assert "x" in ws.receive_json()
