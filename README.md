# CityLab

**A city that runs itself.** CityLab simulates **Kamalnagar**, a small Indian city
of about 2,000 people. Nobody tells them what to do. They wake up, go to work or
school, eat, visit friends, pray, shop, fall in love, have children, grow old and
die. Money moves between people, shops, companies, the city and the bank. Every
event is written down, so the city keeps its own history.

It is free, open source, and runs on your own computer. No paid services, no API
keys.

![Kamalnagar by day](docs/images/map-day.png)

## What you see

* **The map.** Every dot is a person, coloured by what they are doing right now.
  Buildings stand up off the paper. Taller blocks are taller buildings, and their
  shadows move with the real sun. At night windows light up where people are
  awake, and street lamps come on.
* **Click a person** to follow them: their family, job, money, mood, personality,
  friends, and their life story so far.
* **Click a building** to see who lives, works or is inside right now.
* **The City tab** shows what everyone is doing, how many people belong to each
  community, today's festival if there is one, and a city advisor that points out
  what needs attention (homes running out, people out of work, the budget).
* **Economy, Records and Charts** show the money, every recorded event, and how the
  city changes over time.
* **Time controls** let you pause, speed up (from one minute to one day per
  second) or jump ahead.

![Night in Kamalnagar](docs/images/map-night.png)

## What happens in the city

**People.** Each person has an age, a personality, a home, a family, a faith, and
needs (food, sleep, company, fun). Whenever they finish something, they pick what
to do next by weighing their needs, the time, the weather, what is open and how far
it is. Workers keep their shifts, children go to school, small children stay home.

**Neighbourhoods.** Kamalnagar grows around Kamal Chowk, its centre, with the lotus
lake Kamal Talav beside it. Around it are Shivaji Nagar, Tekdi Wadi, Talav Paar,
Girni Gaon (the mill area), Bazaar Peth, Phool Baug, Nadi Kinara and Paschim Peth.

**Faith and festivals.** Families are Hindu, Muslim, Buddhist, Jain, Christian,
Sikh or Parsi (or follow no religion), in shares close to a Maharashtrian city. A
family's names come from its community, and children take their parents' faith.
Each community has its own place of worship and goes at its own times:

* Hindus visit the mandir in the morning or for the evening aarti.
* Muslims pray at the masjid, and many join Friday's midday prayer.
* Christians go to Sunday Mass.
* Sikhs visit the gurudwara, where the langar serves a free meal to all.
* Buddhists gather at the Buddha vihar on Sunday mornings.
* Jains visit the derasar in the morning.
* Parsis visit the agiary.

Some people go every day, many go weekly, some only on festival days. Diwali, Eid,
Christmas, Vaisakhi, Buddha Purnima, Mahavir Jayanti, Navroz, Ganesh Chaturthi and
others are announced on their day, and places of worship fill up. Meeting at the
same place builds friendships. Faith never changes anyone's pay or job chances.

![Sunday Mass at St. Mary's Church](docs/images/sunday-mass.png)

**Friendships.** People who meet at work, school, the park, a restaurant or a place
of worship become acquaintances. Friends of friends get introduced, ties fade if
they are not kept up, and well-connected people attract more friends, the way real
social networks grow.

**Life.** Every midnight people have birthdays, start school, finish school, find
jobs and retire. Couples form between close friends who get along, and move in
together. Babies are born. People die, more likely as they age. Grown children move
out. When there are more jobs than workers, newcomers arrive, often following a
friend. Families who stay out of work for months may leave.

**Money.** Everyone has a bank account at City Bank. People earn wages and pay for
rent, groceries, meals and shopping, with taxes going to the city. Companies sell
what they make, pay staff, and lay people off if they run out of money. Places of
worship live on offerings. The city pays teachers, doctors, police, pensions and
benefits. The bank pays interest, gives loans to people it trusts and writes off
bad debts. Money is never created or lost by accident: the books are checked every
midnight.

![A citizen's card](docs/images/person-card.png)

![The Economy tab](docs/images/economy.png)

## Run it

With Docker (city, web page and database):

```bash
docker compose up --build
# open http://localhost:8080
```

Without Docker:

```bash
cd backend && pip install -e ".[dev]" && uvicorn citylab.main:app --port 8000
cd frontend && npm install && npm run dev   # open http://localhost:5173
```

You can change these with environment variables:

| Variable | What it does | Default |
|---|---|---|
| `CITYLAB_SEED` | Which city you get. The same seed always builds the same city and the same lives. | 1 |
| `CITYLAB_POPULATION` | How many people the city starts with | 2000 |
| `CITYLAB_SPEED` | Simulated minutes per real second | 10 |
| `CITYLAB_AUTOPLAY` | Start running as soon as the server starts | on |
| `CITYLAB_DATABASE_URL` | Save events to PostgreSQL (optional) | none |

A city of 2,000 runs at about one simulated day per 1.5 seconds on a laptop
(`python -m benchmarks.bench` in `backend/`).

## Coming next

City departments and new buildings as the city grows, traffic and buses, crime
with police, CCTV and courts, rewinding history, asking the city questions in plain
English with a free local AI model, and AI-run city leaders.

## How it is built

* **Simulation:** Python. Each person decides only when their current activity
  ends, so thousands of people cost very little. Routes come from
  [NetworkX](https://networkx.org/), daylight from the sun's real position (the
  same code as [LotusLab](https://github.com/14harshaldhote/LotusLab), which
  CityLab grew out of).
* **Server:** [FastAPI](https://fastapi.tiangolo.com/), with a live WebSocket that
  sends everyone's position five times a second.
* **Page:** React and TypeScript. The map is drawn with
  [PixiJS](https://pixijs.com/) (WebGL); charts and the friendship graph with
  [D3](https://d3js.org/).
* **Storage:** in memory, or [PostgreSQL](https://www.postgresql.org/) with
  pgvector, ready for the "ask the city" feature.

## Tests

```bash
cd backend && pytest -q
cd frontend && npm test
```

Database tests run when `CITYLAB_TEST_DATABASE_URL` is set. `docker compose up db`
starts one at `postgresql://citylab:citylab@localhost:5432/citylab`.
