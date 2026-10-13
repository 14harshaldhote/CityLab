import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, liveFrames } from "./api/client";
import type { BuildingCard, CityEvent, CityMap as City, DailyRow, Economy, Frame, PersonCard, Summary } from "./api/types";
import BuildingPanel from "./components/BuildingPanel";
import City3D from "./components/City3D";
import CityMap from "./components/CityMap";
import EconomyPanel from "./components/EconomyPanel";
import type { Network } from "./components/EgoGraph";
import LineChart from "./components/LineChart";
import PersonPanel from "./components/PersonPanel";
import TimeBar from "./components/TimeBar";
import { advise } from "./engine/advisor";
import { LEGEND_KINDS, ROOF } from "./engine/art";
import { ACTIVITY_COLORS, hex } from "./engine/view";

type Tab = "city" | "person" | "place" | "economy" | "records" | "charts";

function usePoll(fn: () => void, ms: number, deps: unknown[]) {
  useEffect(() => {
    fn();
    const id = setInterval(fn, ms);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

export default function App() {
  const [city, setCity] = useState<City | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [frame, setFrame] = useState<Frame | null>(null);
  const [connected, setConnected] = useState(false);
  const frames = useRef<{ prev: Frame | null; next: Frame | null; at: number }>({ prev: null, next: null, at: 0 });
  const [summary, setSummary] = useState<Summary | null>(null);
  const [tab, setTab] = useState<Tab>("city");
  const [view, setView] = useState<"3d" | "map">("3d");
  const [personId, setPersonId] = useState<number | null>(null);
  const [buildingId, setBuildingId] = useState<number | null>(null);
  const [person, setPerson] = useState<PersonCard | null>(null);
  const [building, setBuilding] = useState<BuildingCard | null>(null);
  const [net, setNet] = useState<Network | null>(null);
  const [events, setEvents] = useState<CityEvent[]>([]);
  const [eventKind, setEventKind] = useState("");
  const [daily, setDaily] = useState<DailyRow[]>([]);
  const [econ, setEcon] = useState<Economy | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<{ id: number; name: string; age: number; activity: string | null }[]>([]);

  const loadCity = useCallback(() => {
    api.city().then(setCity, (e) => setError(String(e)));
  }, []);
  useEffect(loadCity, [loadCity]);

  useEffect(
    () =>
      liveFrames((f) => {
        frames.current = { prev: frames.current.next, next: f, at: performance.now() };
        setFrame(f);
      }, setConnected),
    [],
  );

  usePoll(() => api.summary().then(setSummary, () => undefined), 2000, []);
  usePoll(() => personId !== null && api.person(personId).then(setPerson, () => undefined), 1500, [personId]);
  usePoll(() => personId !== null && api.network(personId).then(setNet, () => setNet(null)), 15000, [personId]);
  usePoll(() => buildingId !== null && api.building(buildingId).then(setBuilding, () => undefined), 1500, [buildingId]);
  usePoll(() => tab === "records" && api.events(eventKind || undefined).then(setEvents, () => undefined), 2500, [tab, eventKind]);
  usePoll(() => (tab === "economy" || tab === "city") && api.economy().then(setEcon, () => undefined), 3000, [tab]);
  usePoll(() => (tab === "charts" || tab === "city") && api.daily().then(setDaily, () => undefined), 5000, [tab]);
  const tips = useMemo(() => advise(summary, econ, daily), [summary, econ, daily]);

  useEffect(() => {
    if (!query.trim()) return setResults([]);
    const id = setTimeout(() => api.search(query).then(setResults, () => undefined), 250);
    return () => clearTimeout(id);
  }, [query]);

  const pickPerson = useCallback((id: number) => {
    setPersonId(id);
    setTab("person");
  }, []);
  const pickBuilding = useCallback((id: number) => {
    setBuildingId(id);
    setTab("place");
  }, []);

  const chart = useMemo(() => {
    const days = daily.map((d) => d.day);
    return {
      days,
      people: [
        { label: "population", color: "#2c7fb8", values: daily.map((d) => d.population) },
        { label: "employed", color: "#5f8a4a", values: daily.map((d) => d.employed) },
      ],
      life: [
        { label: "births", color: "#5f8a4a", values: daily.map((d) => d.births) },
        { label: "deaths", color: "#5b6c9e", values: daily.map((d) => d.deaths) },
        { label: "arrived", color: "#e3672f", values: daily.map((d) => d.arrived) },
        { label: "left", color: "#c9971a", values: daily.map((d) => d.left) },
      ],
      social: [
        { label: "new acquaintances per day", color: "#d9467f", values: daily.map((d) => d.new_friendships) },
      ],
      ties: [{ label: "social ties", color: "#8a4fc6", values: daily.map((d) => d.ties) }],
      money: [
        { label: "median bank balance", color: "#5f8a4a", values: daily.map((d) => d.median_balance) },
      ],
      budget: [
        { label: "city budget", color: "#2c7fb8", values: daily.map((d) => d.city) },
        { label: "loans outstanding", color: "#d9480f", values: daily.map((d) => d.loans_outstanding) },
      ],
    };
  }, [daily]);

  const control = (body: Parameters<typeof api.control>[0]) => api.control(body).catch((e) => setError(String(e)));

  return (
    <div className="app">
      <header>
        <div className="brand">
          <h1>
            City<span>Lab</span>
          </h1>
          {city?.name && <span className="cityname">{city.name}</span>}
          <span className="muted">a city that runs itself</span>
        </div>
        {summary && (
          <div className="stats">
            <span className="stat">
              <b>{summary.population.toLocaleString()}</b> people
            </span>
            <span className="stat">
              <b>{summary.households}</b> households
            </span>
            <span className="stat">
              <b>{summary.employed}</b> working
            </span>
            <span className="stat">
              <b>{summary.pupils}</b> at school
            </span>
            <span className="stat">
              <b>{summary.social.friendships.toLocaleString()}</b> friendships
            </span>
          </div>
        )}
      </header>
      {error && (
        <div className="error">
          {error} <button onClick={() => (setError(null), loadCity())}>Retry</button>
        </div>
      )}
      <main>
        <section className="stage">
          {city ? (
            view === "3d" ? (
              <City3D city={city} frames={frames} selectedPerson={tab === "person" ? personId : null} selectedBuilding={tab === "place" ? buildingId : null} onPickPerson={pickPerson} onPickBuilding={pickBuilding} />
            ) : (
              <CityMap city={city} frames={frames} selectedPerson={tab === "person" ? personId : null} selectedBuilding={tab === "place" ? buildingId : null} onPickPerson={pickPerson} onPickBuilding={pickBuilding} />
            )
          ) : (
            <div className="map loading">Building the city...</div>
          )}
          <div className="view-switch">
            <button className={view === "3d" ? "on" : ""} onClick={() => setView("3d")}>
              3D city
            </button>
            <button className={view === "map" ? "on" : ""} onClick={() => setView("map")}>
              Map
            </button>
          </div>
          {view === "3d" && <p className="how-to">Drag to look around · right-drag to move · scroll to zoom · click anyone or anything</p>}
          {view === "map" && (
          <details className="map-legend" open>
            <summary>Map key</summary>
            <ul>
              {LEGEND_KINDS.map(([k, label]) => (
                <li key={k}>
                  <i className="swatch" style={{ background: hex(ROOF[k]) }} /> {label}
                </li>
              ))}
            </ul>
            <p className="muted small" style={{ margin: "6px 0 0" }}>
              Dots are people, coloured by what they are doing. Taller blocks are taller buildings; shadows follow the real sun.
            </p>
          </details>
          )}
          <TimeBar
            frame={frame}
            connected={connected}
            onPlay={(playing) => control({ playing })}
            onSpeed={(speed) => control({ speed, playing: true })}
            onSkip={(m) => control({ advance_minutes: m })}
          />
        </section>
        <aside>
          <nav className="tabs">
            {(["city", "person", "place", "economy", "records", "charts"] as Tab[]).map((t) => (
              <button key={t} className={tab === t ? "on" : ""} onClick={() => setTab(t)}>
                {t[0].toUpperCase() + t.slice(1)}
              </button>
            ))}
          </nav>
          {tab === "city" && summary?.festival && (
            <div className="card festival">
              <h2>Today is {summary.festival.name}</h2>
              <p>
                In {summary.city}, {summary.festival.text}. {summary.festival.faith} families fill their places of worship all day.
              </p>
            </div>
          )}
          {tab === "city" && tips.length > 0 && (
            <div className="card advisor">
              <h2>City advisor</h2>
              <ul>
                {tips.map((t) => (
                  <li key={t.title} className={t.tone}>
                    <b>{t.title}</b>
                    {t.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {tab === "city" && (
            <div className="card">
              <h2>Right now</h2>
              <ul className="legend-list">
                {city?.activities.map((a, i) => (
                  <li key={a}>
                    <i style={{ background: hex(ACTIVITY_COLORS[i]) }} /> {a}
                    <b>{frame?.counts[a] ?? 0}</b>
                  </li>
                ))}
              </ul>
              {summary && (
                <p className="muted">
                  {summary.couples} couples · {summary.retired} retired · {summary.unemployed} looking for work · {summary.vacancies} open jobs · {summary.free_homes} free homes. Each person
                  has {summary.social.avg_ties} ties on average. Last step took {summary.step_ms} ms.
                </p>
              )}
              {summary?.religions && (
                <>
                  <h3>Communities</h3>
                  <ul className="faiths">
                    {Object.entries(summary.religions).map(([label, n]) => (
                      <li key={label}>
                        <span>{label}</span>
                        <i style={{ width: `${Math.max(1, (100 * n) / summary.population)}%` }} />
                        <b>{n}</b>
                      </li>
                    ))}
                  </ul>
                </>
              )}
              <h3>Find a person</h3>
              <input placeholder="Type a name" value={query} onChange={(e) => setQuery(e.target.value)} />
              <div className="people">
                {results.map((r) => (
                  <button key={r.id} className="link" onClick={() => pickPerson(r.id)}>
                    {r.name} <small>{r.age}</small>
                  </button>
                ))}
              </div>
              <p className="muted small">Click any dot on the map to follow that person, or any building to see who is inside.</p>
            </div>
          )}
          {tab === "person" && (person ? <PersonPanel card={person} net={net && net.center === person.id ? net : null} onPick={pickPerson} /> : <div className="card muted">Click a person on the map.</div>)}
          {tab === "place" && (building ? <BuildingPanel card={building} onPick={pickPerson} /> : <div className="card muted">Click a building on the map.</div>)}
          {tab === "economy" && (econ ? <EconomyPanel econ={econ} onPickBuilding={pickBuilding} /> : <div className="card muted">Loading the books...</div>)}
          {tab === "records" && (
            <div className="card">
              <h2>City records</h2>
              <select value={eventKind} onChange={(e) => setEventKind(e.target.value)}>
                <option value="">Everything</option>
                <option value="birth">Births</option>
                <option value="death">Deaths</option>
                <option value="couple">Couples</option>
                <option value="hired">Hires</option>
                <option value="moved">Moving in together</option>
                <option value="moved_out">Leaving home</option>
                <option value="school_start">Starting school</option>
                <option value="graduated">Graduations</option>
                <option value="retired">Retirements</option>
                <option value="arrived">Arrivals</option>
                <option value="festival">Festivals</option>
                <option value="loan">Loans</option>
                <option value="laid_off">Lay-offs</option>
                <option value="default">Defaults</option>
                <option value="left">Departures</option>
                <option value="day_summary">Daily reports</option>
              </select>
              <ul className="events">
                {events.length === 0 && <li className="muted">Nothing yet. Let the city run for a day.</li>}
                {events.map((e) => (
                  <li key={e.id}>
                    <time>{e.when}</time> {e.text}
                    {e.people.length > 0 && e.kind !== "day_summary" && (
                      <button className="link" onClick={() => pickPerson(e.people[0])}>
                        open
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {tab === "charts" && (
            <div className="card">
              <h2>People</h2>
              <LineChart days={chart.days} series={chart.people} />
              <h2>Births, deaths and migration per day</h2>
              <LineChart days={chart.days} series={chart.life} height={130} />
              <h2>Money</h2>
              <LineChart days={chart.days} series={chart.money} height={120} />
              <LineChart days={chart.days} series={chart.budget} height={130} />
              <h2>Social graph</h2>
              <LineChart days={chart.days} series={chart.ties} />
              <LineChart days={chart.days} series={chart.social} height={120} />
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
