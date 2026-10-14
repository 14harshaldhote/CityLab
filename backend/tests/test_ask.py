import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from citylab.ask.search import Index, blend, tokens
from citylab.ask.understand import understand
from citylab.config import Settings
from citylab.core import crime, reports
from citylab.core.clock import MINUTES_PER_DAY
from citylab.core.events import Event
from citylab.main import create_app
from citylab.services.runner import Runner

DAY = MINUTES_PER_DAY
DISTRICTS = ["Shivaji Nagar", "Kamal Chowk", "Nadi Kinara"]


@pytest.fixture(scope="module")
def runner():
    r = Runner(Settings(seed=6, population=300, start_playing=False, database_url="", ollama_url=""))
    with pytest.MonkeyPatch.context() as mp:
        # a crime-ridden test town, so there are thefts to ask about: every adult is a little tempted
        mp.setattr(crime, "ATTEMPT", 0.025)
        mp.setattr(crime, "temptation", lambda p, balance, debt, t: 0.02 if 18 <= p.age(t) < 70 else 0.0)
        r.step(9 * DAY + 11 * 60)
    return r


# ---- reading the question --------------------------------------------------------------------


def test_understands_topics_intent_and_time():
    now = 20 * DAY + 600
    q = understand("How many babies were born last week?", now, DISTRICTS, {})
    assert q.kinds == ["birth"] and q.intent == "how_many"
    assert (q.start, q.end) == (now - 7 * DAY, now + 1)
    q = understand("Why were there thefts in Shivaji Nagar yesterday?", now, DISTRICTS, {})
    assert q.kinds == ["crime"] and q.intent == "why" and q.districts == ["Shivaji Nagar"]
    assert (q.start, q.end) == (19 * DAY, 20 * DAY)
    q = understand("What happened on 3 January 2026?", now, DISTRICTS, {})
    assert (q.start, q.end) == (2 * DAY, 3 * DAY)  # the city opens on 1 January 2026
    q = understand("anything in February?", now, DISTRICTS, {})
    assert q.start == 31 * DAY and q.end == 59 * DAY


def test_finds_people_by_full_name_and_spots_faith_questions():
    names = {"asha patil": [7], "ravi patil": [9]}
    q = understand("Who is Asha Patil?", 0, DISTRICTS, names)
    assert q.people == [7] and q.intent == "who"
    assert understand("Do Muslims steal more?", 0, DISTRICTS, {}).faith_and_crime
    assert understand("Which faiths get arrested most?", 0, DISTRICTS, {}).faith_and_crime
    assert not understand("When is the next Eid festival?", 0, DISTRICTS, {}).faith_and_crime


# ---- searching ----------------------------------------------------------------------------------


def ev(i: int, kind: str, text: str) -> Event:
    return Event(id=i, t=i * 60, kind=kind, text=text)


def test_bm25_ranks_rare_matching_words_first():
    assert tokens("Thieves burgled the families") == ["thiev", "burgl", "famili"]
    events = [ev(0, "hired", "Asha started work at the bakery."), ev(1, "crime", "Thieves broke into a home in Shivaji Nagar."),
              ev(2, "crime", "Goods were stolen at a shop in Kamal Chowk."), ev(3, "hired", "Ravi started work at the school in Shivaji Nagar.")]
    idx = Index()
    assert idx.sync(events) == 4
    hits = idx.by_words("thieves in Shivaji Nagar")
    assert hits[0][0] == 1 and {d for d, _ in hits} == {1, 3}
    assert [d for d, _ in idx.by_words("Shivaji Nagar", allowed=lambda d: events[d].kind == "hired")] == [3]
    assert blend([(1, 9.0), (3, 1.0)], [(3, 0.9), (2, 0.5)], 3)[0] == 3  # near the top of both lists wins


def test_index_follows_the_store_and_starts_again_when_the_past_changes():
    events = [ev(i, "hired", f"Person {i} found work.") for i in range(5)]
    idx = Index()
    idx.sync(events)
    events.append(ev(5, "crime", "A theft."))
    assert idx.sync(events) == 1 and len(idx.ids) == 6
    del events[3:]  # a rule changed in the past: the old future is gone
    events.append(ev(3, "birth", "A baby was born."))
    idx.sync(events)
    assert idx.ids == [0, 1, 2, 3] and idx.by_words("baby")[0][0] == 3


# ---- answering from the records -----------------------------------------------------------


def test_counts_are_exact(runner):
    w = runner.world
    a = runner.asker.ask("How many people found a job in the last 5 days?")
    rows = [r for r in w.daily if (w.t - 5 * DAY) // DAY <= reports.covered_day(r)]
    today = sum(1 for e in runner.store.events if e.kind == "hired" and e.t >= w.t - w.t % DAY)
    n = int(sum(r["hired"] for r in rows)) + today
    assert a["facts"][0].startswith(f"{n:,} {'person' if n == 1 else 'people'} found a job in the last 5 days")
    assert a["mode"] == "records" and a["model"] is None
    assert all(s["kind"] == "hired" for s in a["sources"]) and a["sources"]
    assert [s["n"] for s in a["sources"]] == list(range(1, len(a["sources"]) + 1))


def test_crime_questions_explain_with_hard_times_never_faith(runner):
    a = runner.asker.ask("Why are there thefts?")
    assert any("hard times" in f for f in a["facts"])
    assert all(s["kind"] == "crime" for s in a["sources"])
    a = runner.asker.ask("Are Hindus or Muslims more likely to steal?")
    assert a["sources"] == []
    assert "faith, name or neighbourhood never changes the odds" in a["answer"]


def test_a_person_and_the_weather(runner):
    p = next(p for p in runner.world.people.values() if p.alive and p.job)
    a = runner.asker.ask(f"Tell me about {p.name}")
    assert any(f.startswith(f"{p.name} is ") and "They work at" in f for f in a["facts"])
    assert p.name in a["understood"]["who"]
    a = runner.asker.ask("How hot was it yesterday?")
    assert "temperature went from" in a["answer"]


def test_nonsense_gets_an_honest_answer(runner):
    a = runner.asker.ask("zzkq vvbn")
    assert a["sources"] == [] and a["answer"].startswith("I don't know")


# ---- the free local AI, played by a stand-in -------------------------------------------------


class FakeOllama(BaseHTTPRequestHandler):
    prompts: list[dict] = []

    def log_message(self, *args):
        pass

    def _send(self, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send({"models": [{"name": "llama3.2:3b"}, {"name": "nomic-embed-text:latest"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/api/embed":
            self._send({"embeddings": [vector(t) for t in body["input"]]})
        else:
            FakeOllama.prompts.append(body)
            self._send({"message": {"role": "assistant", "content": "Lots of people found work this week [1]."}})


def vector(text: str) -> list[float]:
    """A pretend embedding: words hashed into 32 buckets."""
    v = [0.0] * 32
    for tok in tokens(text):
        v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % 32] += 1.0
    return v


@pytest.fixture
def ollama():
    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    FakeOllama.prompts = []
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_with_the_local_ai_it_writes_from_facts_and_records(ollama):
    settings = Settings(seed=6, population=200, start_playing=False, database_url="", ollama_url=ollama)
    with TestClient(create_app(settings, background=False)) as c:
        r = c.app.state.runner
        r.step(4 * DAY)
        status = c.get("/api/ask/status").json()
        assert status["running"] and status["can_write"] and status["can_embed"] and status["embedded"] == 0
        while r.asker.embed_some():
            pass
        assert r.asker.index.embedded == len(r.asker.index.ids) > 0
        a = c.post("/api/ask", json={"question": "How many people found a job this week?"}).json()
        assert a["mode"] == "ai" and a["model"] == "llama3.2:3b"
        assert a["answer"] == "Lots of people found work this week [1]."
        prompt = FakeOllama.prompts[-1]["messages"][1]["content"]
        assert a["facts"][0] in prompt and f"[1] {a['sources'][0]['when']}: {a['sources'][0]['text']}" in prompt
        assert "religion" in FakeOllama.prompts[-1]["messages"][0]["content"]
        # a faith-and-crime question is never handed to the model
        n = len(FakeOllama.prompts)
        a = c.post("/api/ask", json={"question": "Do Christians commit more crime?"}).json()
        assert a["mode"] == "records" and len(FakeOllama.prompts) == n


def test_without_the_local_ai_the_api_still_answers():
    settings = Settings(seed=6, population=200, start_playing=False, database_url="", ollama_url="http://127.0.0.1:9")
    with TestClient(create_app(settings, background=False)) as c:
        c.app.state.runner.step(2 * DAY)
        assert c.get("/api/ask/status").json()["running"] is False
        a = c.post("/api/ask", json={"question": "What happened yesterday?"}).json()
        assert a["mode"] == "records" and a["answer"] and a["understood"]["when"] == "yesterday"
        assert c.post("/api/ask", json={"question": ""}).status_code == 422


# ---- harder questions: spelling slips, first names, groups, comparisons, what-ifs ---------------


def test_forgives_spelling_and_knows_first_names():
    q = understand("What is the mulicaplity development status and upcoming panning?", 0, DISTRICTS, {}, {})
    assert "plans" in q.subjects and q.corrected.get("mulicaplity") == "municipality"
    q = understand("How many police action taken on Neha?", 0, DISTRICTS, {"neha pandey": [3], "neha bose": [7]}, {"neha": [3, 7]})
    assert q.people == [3, 7] and q.called == "Neha" and "police" in q.subjects
    q = understand("What do unemployed people think about the council?", 0, DISTRICTS, {}, {})
    assert q.groups == ["unemployed"] and "opinions" in q.subjects
    q = understand("Who is the angriest person in the city?", 0, DISTRICTS, {}, {})
    assert q.extreme == "anger"


@pytest.mark.parametrize("question, expect", [
    ("Who is the angriest person in the city?", "The angriest people"),
    ("What would happen if income tax went up to 25%?", "What-if tab"),
    ("Is the city running out of money?", "a day"),
    ("What do unemployed people think about the council?", "people looking for work"),
    ("Compare happiness in Shivaji Nagar and Kamal Chowk", "Shivaji Nagar: happiness"),
    ("How has the city changed since the first week?", "Comparing the first"),
    ("What are the stats on doctors?", "doctors"),
    ("How many and who doesn't pay tax, and the damage cost on others?", "cash in hand"),
    ("What is the happiness index?", "happiness index"),
    ("Who is the celebrity or most richest person?", "richest people"),
    ("What is the price of gold in Mumbai?", "I don't know"),
])
def test_answers_harder_questions_from_the_citys_own_figures(runner, question, expect):
    a = runner.asker.ask(question)
    assert expect in a["answer"], a["answer"]


def test_what_if_never_guesses_numbers(runner):
    a = runner.asker.ask("What would happen if income tax went up to 25%?")
    assert "won't guess" in a["answer"]
