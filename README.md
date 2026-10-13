# CityLab

**A city that runs itself.** Thousands of simulated people wake up, go to work or
school, eat, visit friends, fall in love, have children, grow old and die. Agencies
and companies run the city, a bank holds the money, traffic and buses move on real
streets, crime happens and cameras watch. Every event is recorded, so you can scrub
back through the city's history and ask it questions in plain English.

Everything is free and open source and runs on your own computer.

CityLab grows out of [LotusLab](https://github.com/14harshaldhote/LotusLab): the
daylight engine, the time controls and the idea of an exact, replayable simulation
come from there.

## Build stages

| Stage | What it adds | Status |
|---|---|---|
| 1 | Foundation: simulation clock, seeded randomness, event bus and log, weather and daylight, generated city with streets, routing, Postgres storage | done |
| 2 | People and their day: needs, personality, schedules, utility AI, live map | next |
| 3 | Life cycle and the social graph: ageing, couples, births, deaths, migration | planned |
| 4 | Economy and the bank | planned |
| 5 | Government agencies, zoning and new buildings | planned |
| 6 | Roads, traffic and buses | planned |
| 7 | Crime, police, CCTV and courts | planned |
| 8 | History and rewind, what-if branches | planned |
| 9 | RAG: "Ask the city" (local, free models via Ollama) | planned |
| 10 | AI leaders, featured citizens, city growth | planned |

## Stage 1: the foundation

* **Time** is an integer count of simulated minutes since the city was founded
  (`core/clock.py`). Integers mean no drift: the same run always lands on the same
  minute.
* **Randomness** comes from named streams derived from one city seed
  (`core/rng.py`). Births, crime and weather each draw from their own stream, so a
  change in one part of the city never reshuffles another. Same seed, same city.
* **Events** (`core/events.py`) are the only way parts of the city talk to each
  other and the city's memory. Each event has a plain-English sentence, so the log
  reads like a diary and is ready for search and RAG later.
* **Weather and daylight** (`core/weather.py`, `core/solar.py`): sun position from
  the NOAA algorithm (from LotusLab) and a seasonal synthetic climate with a
  monsoon. Each day's weather has its own seed, so any day can be asked for in any
  order and always comes out the same, which is what rewind will need.
* **The city** (`core/citygen.py`): a street grid with some streets removed,
  zoned into a downtown, a civic block (City Hall, police, bank, hospital), a
  central park, an industrial edge, residential neighbourhoods with schools and
  local shops, and empty land around it to grow into. Each building type has its
  own jobs, shifts and opening hours.
* **Routing** (`core/routing.py`): A* shortest paths on the street graph with
  [NetworkX](https://networkx.org/), cached per corner pair, turned into timed
  walking or driving trips whose position can be read at any minute.
* **Storage** (`storage/`): an in-memory store for fast lookups and an optional
  PostgreSQL store (with the pgvector extension ready for RAG) that writes events
  in batches, so the simulation never waits on the database.

## Run the tests

```bash
cd backend
pip install -e ".[dev]"
pytest -q
```

Postgres tests run when `CITYLAB_TEST_DATABASE_URL` is set. `docker compose up db`
starts a local database (`postgresql://citylab:citylab@localhost:5432/citylab`).
