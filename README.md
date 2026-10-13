# CityLab: welcome to Kamalnagar

Imagine a toy city that lives by itself. Nobody moves the pieces. Its 2,000
people wake up, catch the morning rush, go to work and school, grab chai with
friends, pray, shop, fall in love, have babies and grow old. Your job is simple:
watch, poke around, and see what happens.

CityLab is a playground for understanding the ideas behind today's AI and
simulation games, by playing with them instead of reading about them. It's
completely free and runs on your own computer.

![Kamalnagar on a Tuesday morning](docs/images/city-day.png)

## Things to try

1. **Follow someone for a day.** Click any little person in the street, then press
   *Follow them*. You'll see their family, their job, their mood, their friends
   and the story of their life so far.
2. **Catch the morning rush.** Set the speed to *1 h/s* and watch around 8 o'clock
   as people walk to school and drive to work. Everyone keeps to the left, as on
   Indian roads.
3. **Watch the lights come on.** Jump ahead to the evening. Windows light up where
   families are awake, offices go dark, and street lamps glow.
4. **Find Friday prayers and Sunday Mass.** Open the Records tab, or click a
   masjid on a Friday afternoon or the church on a Sunday morning, and see who's
   inside.
5. **Wait for a festival.** Diwali, Eid, Christmas, Vaisakhi and more are on the
   city's calendar. On the day, the City tab tells you, and the places of worship
   fill up.
6. **Check who's rich and who's struggling.** The Economy tab shows the bank, the
   city's budget and the companies doing best and worst.
7. **Watch a family grow.** In Records, pick *Births* or *Couples*, then open the
   people involved and follow their family tree.
8. **Watch the city grow.** Let it run for a few weeks. When homes start filling up,
   the town planners mark out new land, road crews lay fresh streets, and builders
   put up fences and tower cranes. Open the *Agencies* tab to see every building
   site, who's paying for it and how many days are left. When a housing society
   is finished, new families move in.
9. **Switch to the flat map.** Press *Map* for a colourful, hand-drawn view where
   every dot is a person, coloured by what they're doing.

![Kamalnagar at night](docs/images/city-night.png)

## How the city thinks

These are the same ideas that power modern games and AI, in plain words.

* **Every person has a tiny brain.** Whenever someone finishes what they're doing,
  they look at their choices (sleep, eat, work, visit a friend, go to the park,
  pray) and give each one a score. Hungry people score food higher, outgoing
  people score friends higher, and nobody wants the park in the rain. The best
  score wins, with a little randomness so nobody acts like a robot. Characters in
  games like The Sims think the same way.
* **Friendships grow like real social networks.** People who keep meeting at work,
  school, the park or the masjid become friends. Friends introduce friends,
  popular people attract more friends, and friendships fade if nobody keeps them
  up. That's how real-life friend networks grow, and how social media
  networks grow too.
* **Life follows real patterns.** Birthdays, school, first jobs, weddings, babies
  and old age follow the curves real populations follow. Nobody scripts the
  population; it grows or shrinks on its own.
* **The city plans ahead.** The municipal corporation keeps an eye on how full
  the homes are, how many jobs are waiting and whether there are enough shops and
  school seats. When something runs short, it decides what to build next, a bit
  like the planners in a city-building game.
* **Money can't leak.** Every rupee is always somewhere: in a person's account, a
  shop's till, the city's budget or the bank. When it moves, it leaves one place
  and arrives in another, just like a real bank's books.
* **The city keeps a diary.** Every birth, wedding, new job, festival, loan and new building is
  written down in plain English. Soon you'll be able to ask the city questions,
  like "who are the busiest people in Phool Baug?", and an AI running on your own
  computer will answer from that diary.
* **Same seed, same story.** Every city grows from a number called a seed, like a
  level code in a game. Use the same seed and you get the same city and the same
  lives, every time. Change it and a whole new Kamalnagar appears.

## What's in Kamalnagar

* **Neighbourhoods:** Kamal Chowk in the middle, next to the lotus lake Kamal
  Talav, surrounded by Shivaji Nagar, Tekdi Wadi, Talav Paar, Girni Gaon, Bazaar
  Peth, Phool Baug, Nadi Kinara and Paschim Peth, with farmland all around.
* **People and families** from every community: Hindu, Muslim, Buddhist, Jain,
  Christian, Sikh and Parsi, with names from their community.
* **Places to go:** bungalows and housing societies with water tanks on the roof,
  glass office towers, shops, restaurants, factories, schools, a hospital, the
  police station, the municipal corporation and City Bank.
* **Places of worship:** mandirs, masjids, a church, a gurudwara with its free
  langar, a Buddha vihar, a Jain derasar and a Parsi agiary.
* **Money:** wages, rent, groceries, water bills, taxes, pensions, savings,
  loans, and companies that grow or lay people off.
* **People who run the city:** a town planning office, a public works department
  that lays roads, an education department, the water supply, and local builders
  who borrow from City Bank to put up new homes and shops.

![New housing societies going up in Nadi Kinara](docs/images/city-growing.png)

![Someone's life story](docs/images/person-card.png)

## Start it on your computer

The easiest way is with [Docker](https://www.docker.com/products/docker-desktop/)
(free). Download this project, open a terminal in its folder and type:

```bash
docker compose up --build
```

Then open <http://localhost:8080> in your browser. That's it.

<details>
<summary>Without Docker, for tinkerers</summary>

You'll need Python and Node.js. In one terminal:

```bash
cd backend && pip install -e ".[dev]" && uvicorn citylab.main:app --port 8000
```

In another:

```bash
cd frontend && npm install && npm run dev
```

Then open <http://localhost:5173>. To get a different city, set
`CITYLAB_SEED` to any number before starting. To start with more or fewer people,
set `CITYLAB_POPULATION`.

</details>

## Coming soon

* Traffic jams, buses and bus stops.
* Crime, police patrols, CCTV cameras and courts.
* A time machine to rewind the city and try "what if...?".
* Chatting with the city: ask it anything about its people and history.
* AI-run city leaders who make decisions you can watch.

## Made with free tools

The 3D city is drawn with [three.js](https://threejs.org/), the flat map with
[PixiJS](https://pixijs.com/) and the charts with [D3](https://d3js.org/). The
city itself runs on Python. Everything is free and open source, and nothing ever
needs a paid account or an internet service.

CityLab grew out of [LotusLab](https://github.com/14harshaldhote/LotusLab), a
lotus pond simulator. That's why the lake at the heart of Kamalnagar is full of
lotuses.
