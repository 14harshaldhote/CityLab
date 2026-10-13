import type { Transport } from "../api/types";

const MODES: [key: string, label: string, color: string][] = [
  ["walk", "on foot", "#5f8a4a"],
  ["bus", "by bus", "#2c7fb8"],
  ["auto", "by auto", "#e0a21b"],
  ["car", "by car", "#d2463c"],
];

const jamColor = (r: number) => (r >= 1.6 ? "#b3261e" : r >= 1.2 ? "#e0602f" : r >= 0.7 ? "#f2b32a" : "#8fb35a");

/** How Kamalnagar gets around: who is on the move, where it is jammed, and the city buses. */
export default function RoadsPanel({ data }: { data: Transport }) {
  const now = data.now;
  const trips = data.today.trips;
  const total = Object.values(trips).reduce((a, b) => a + b, 0);
  return (
    <>
      <div className="card">
        <h2>On the move right now</h2>
        <ul className="moving">
          <li>
            <b>{now.walking}</b> walking
          </li>
          <li>
            <b>{now.driving}</b> driving
          </li>
          <li>
            <b>{now.in_autos}</b> in autos
          </li>
          <li>
            <b>{now.on_buses}</b> on {now.buses} buses
          </li>
          <li>
            <b>{now.waiting}</b> waiting at stops
          </li>
        </ul>
        <h3>Today so far</h3>
        {total > 0 ? (
          <>
            <div className="modes">
              {MODES.map(([k, label, color]) =>
                trips[k] ? <i key={k} style={{ width: `${(100 * trips[k]) / total}%`, background: color }} title={`${trips[k]} trips ${label}`} /> : null,
              )}
            </div>
            <ul className="modes-key">
              {MODES.map(([k, label, color]) => (
                <li key={k}>
                  <i style={{ background: color }} /> {Math.round((100 * (trips[k] ?? 0)) / total)}% {label}
                </li>
              ))}
            </ul>
            <p className="muted small">
              The trip to work or school takes {data.today.commute_min.toFixed(0)} minutes on average, and {data.today.late}{" "}
              {data.today.late === 1 ? "person has" : "people have"} been late for work.
            </p>
          </>
        ) : (
          <p className="muted">Nobody has gone anywhere yet today.</p>
        )}
      </div>

      <div className="card">
        <h2>Traffic</h2>
        {data.jams.length === 0 ? (
          <p className="muted">The streets are clear. Come back between 8 and 10 in the morning, or 5 and 8 in the evening.</p>
        ) : (
          <ul className="jams">
            {data.jams.map((j) => (
              <li key={j.street}>
                <span>{j.street}</span>
                <b style={{ color: jamColor(j.ratio) }}>{j.speed_kmh} km/h</b>
                <div className="jam-bar">
                  <i style={{ width: `${Math.min(100, (100 * j.ratio) / 2)}%`, background: jamColor(j.ratio) }} />
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="muted small">
          A street slows down sharply once it is nearly full, so a few more cars at 9 o'clock can turn a quick drive into a crawl. When a street jams day
          after day, the Public Works Department widens it.
        </p>
        {data.widened.length > 0 && <p className="small">Widened to four lanes: {data.widened.join(", ")}.</p>}
      </div>

      <div className="card">
        <h2>City buses</h2>
        <ul className="lines">
          {data.lines.map((l) => (
            <li key={l.number}>
              <span className="line-badge" style={{ background: l.color }}>
                {l.number}
              </span>
              <div>
                <b>{l.name}</b>
                <small className="muted">
                  {l.stops} stops, {l.km} km · {l.every ? `a bus every ${l.every} minutes` : "not running now"}
                </small>
                <small>
                  {l.buses_now} on the road with {l.riders_now} aboard · {l.riders_today} rides today
                </small>
              </div>
            </li>
          ))}
        </ul>
        <p className="muted small">
          A ride costs ₹{data.fares.bus} (half price for seniors, free for children under 12). Autos start at ₹{data.fares.auto_min} and add ₹
          {data.fares.auto_per_km} a kilometre. Hover over a bus in the 3D city to see how full it is.
        </p>
      </div>
    </>
  );
}
