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
| 2 | People and their day: needs, personality, schedules, utility AI, friendships from shared places, API and live map | done |
| 3 | Life cycle and the social graph: ageing, couples, births, deaths, jobs, migration | done |
| 4 | Economy and the bank: accounts, wages, taxes, rent, shopping, loans, lay-offs | done |
| 5 | Government agencies, zoning and new buildings | next |
| 6 | Roads, traffic and buses | planned |
| 7 | Crime, police, CCTV and courts | planned |
| 8 | History and rewind, what-if branches | planned |
| 9 | RAG: "Ask the city" (local, free models via Ollama) | planned |
| 10 | AI leaders, featured citizens, city growth | planned |

![A person's card next to the live map](docs/images/person-card.png)

## Run it

With Docker (city, API, web page and Postgres):

```bash
docker compose up --build
# open http://localhost:8080
```

Without Docker:

```bash
cd backend && pip install -e ".[dev]" && uvicorn citylab.main:app --port 8000
cd frontend && npm install && npm run dev   # open http://localhost:5173
```

Settings are environment variables: `CITYLAB_SEED`, `CITYLAB_POPULATION` (default
2000), `CITYLAB_SPEED` (simulated minutes per real second, default 10),
`CITYLAB_AUTOPLAY`, `CITYLAB_DATABASE_URL` (optional Postgres).

## Stage 4: money and City Bank

`core/economy.py` gives every person, company, the city, the landlord and City Bank
an account, and money only moves by double-entry transfer, so the books always
balance (the simulation checks this every midnight, to the paisa). Money enters
and leaves through one account, the outside world.

* **During the day** people pay for meals out and shopping on the spot (with 5%
  sales tax). The brain skips those options when someone cannot afford them.
* **Every midnight**: wages for each shift actually worked (15% income tax
  withheld; the city pays teachers, doctors, police and City Hall staff, the bank
  pays its own); offices, factories and the bus depot sell their output to the
  outside world in proportion to who turned up and how skilled they are; every
  household pays rent and buys groceries from its nearest shop; the city pays
  pensions and unemployment benefit; shops pay for their stock; companies pay
  business tax and, once they have a cushion, dividends; the landlord pays upkeep
  and property tax.
* **City Bank** pays interest on savings (base rate minus 3%), charges base rate
  plus 3% plus a risk premium on loans, turns overdrafts into amortised one-year
  loans for people and companies with good credit, lowers credit scores for missed
  payments and writes loans off after 60 missed days. The city borrows when its
  budget runs dry.
* **Companies** that still run out of money lay people off. Money is inherited by a
  partner or children when someone dies and leaves with households that move away.

The Economy tab shows the bank, the city budget, today's money flows and the
richest and struggling companies; person and building cards show balances, debts
and credit scores.

![The Economy tab](docs/images/economy.png)

## Stage 3: life, growth and the social graph

Every simulated midnight (`core/lifecycle.py`) the city lives a little:

* **Birthdays** move people through life: school at 6, graduation and job hunting
  at 18, retirement at 65, a little more skill for every year of work.
* **Deaths** follow the Gompertz law of mortality: yearly risk
  `0.00003 * e^(0.09 * age)`, so it roughly doubles every 7.7 years, raised by poor
  health. When someone dies their job and school place are freed, their partner is
  widowed and they leave the social graph; the registry keeps their story.
* **Couples** form between single adults who are already close in the social graph,
  more likely the stronger the tie and the more alike their personalities. The one
  with the smaller household moves in with the other, bringing their children.
* **Births** come from couples: a fertility curve peaking near 29, lower with each
  child they already have and in crowded homes. Babies join the family, take after
  their parents' personality a little and are tied to parents and siblings in the
  graph.
* **Jobs**: people without work look for one of the nearest open jobs.
* **Leaving home**: grown children with a job move out when a home is free.
* **Migration**: when open jobs outnumber job seekers and homes are free, newcomers
  arrive, often following a friend already here, picked in proportion to how
  connected they are (preferential attachment). Households that stay unemployed
  for months may leave.

The social graph now grows and prunes itself: chance meetings at shared places,
friends of friends, ties that fade unless kept up, and nobody keeping up with more
than 40 people. Each person's card shows their corner of the graph (D3 force
layout), their family and their life story from the records.

![Charts of population, births, deaths and the social graph](docs/images/charts.png)

## Stage 2: people and their day

* **Who lives here** (`core/world.py`): the city is founded with about 2,000
  people in households (singles, couples, families, single parents, retired
  couples), with ages, Big Five personalities, skills, homes, cars for some
  households, schools for children and jobs for most adults, near home where
  possible.
* **Needs** (`core/people.py`): hunger, energy, social and fun drain over time;
  each activity restores some and costs others. Needs are updated lazily, only when
  a person decides, which is exact because rates are constant within an activity.
* **The brain** (`core/brain.py`): a schedule (shifts, school days, two rotating days
  off for shift workers, small children kept at home) plus utility AI. Every option
  (sleep, eat at home, eat out, work, school, visit a friend, park, shop, relax) is
  scored from needs, personality, time of day, weather, opening hours and distance,
  with a little noise. The best one wins. No language model, microseconds per
  decision.
* **The tick loop**: people sit in a priority queue keyed by when their current
  activity ends; each simulated minute only pops the people who need to decide.
  Positions between decisions are read off the planned route.
* **Friendships** (`core/social.py`): people who share a workplace, school, park or
  restaurant meet; the person met is picked in proportion to how many ties they
  already have (preferential attachment), friends of friends get introduced
  (triadic closure), and unused ties fade.
* **API** (`api/routes.py`): `/api/city`, `/api/frame`, `/api/summary`,
  `/api/people/{id}`, `/api/buildings/{id}`, `/api/events`, `/api/stats/daily`,
  `/api/control`, `/api/reset`, and a WebSocket `/api/ws` that streams every
  person's position five times a second.
* **The page** (`frontend/`): React + TypeScript, the map drawn with
  [PixiJS](https://pixijs.com/) (WebGL) so thousands of moving dots stay smooth,
  charts with D3. Pan, zoom, click a person to follow them (needs, personality,
  family, friends, life story) or a building to see who is inside. Night falls with
  the real sun angle and street lamps come on.

On a laptop the city of 2,000 runs at roughly one simulated day per 1.5 seconds
(`python -m benchmarks.bench`).

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
