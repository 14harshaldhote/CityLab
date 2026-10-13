import type { Agencies } from "../api/types";
import { fmt } from "./PersonPanel";

const KIND_LABEL: Record<string, string> = {
  home: "homes",
  office: "office",
  shop: "shops",
  restaurant: "restaurant",
  factory: "factory",
  school: "school",
  park: "park",
  temple: "mandir",
  mosque: "masjid",
  church: "church",
  gurudwara: "gurudwara",
  vihara: "Buddha vihar",
  derasar: "Jain derasar",
  agiary: "agiary",
};

/** Who runs and builds the city: departments, what they are watching, and every project under way. */
export default function AgenciesPanel({ data, onPickPerson, onPickBuilding }: { data: Agencies; onPickPerson: (id: number) => void; onPickBuilding: (id: number) => void }) {
  const gov = data.departments.filter((d) => d.sector === "government");
  const priv = data.departments.filter((d) => d.sector === "private");
  return (
    <>
      <div className="card">
        <h2>Under construction</h2>
        {data.projects.length === 0 && data.roadworks.length === 0 && (
          <p className="muted">Nothing is being built right now. When homes, jobs or school seats run short, Town Planning zones land and builders get to work.</p>
        )}
        <ul className="projects">
          {data.roadworks.map((r, k) => (
            <li key={`r${k}`}>
              <div>
                {r.street ? (
                  <b>Widening {r.street}</b>
                ) : (
                  <>
                    <b>New streets in {r.district}</b> <small>for a {r.zone} block</small>
                  </>
                )}
                <div className="bar">
                  <i style={{ width: `${Math.round(r.progress * 100)}%` }} />
                </div>
                <small className="muted">Public Works Department · {r.why}</small>
              </div>
            </li>
          ))}
          {data.projects.map((p) => (
            <li key={p.building}>
              <div>
                <button className="link" onClick={() => onPickBuilding(p.building)}>
                  <b>{p.name}</b>
                </button>{" "}
                <small>
                  {KIND_LABEL[p.kind] ?? p.kind} · {Math.round(p.progress * 100)}% · about {p.days_left} days left
                </small>
                <div className="bar">
                  <i style={{ width: `${Math.round(p.progress * 100)}%` }} />
                </div>
                <small className="muted">
                  By {p.owner}.{" "}
                  {p.crew > 0 ? `${p.crew} of the ${p.crew_needed} workers live in the city; the rest come from outside.` : "Everyone in the city is busy, so the crew comes from outside."}{" "}
                  {p.why}
                </small>
              </div>
            </li>
          ))}
        </ul>
        <p className="muted small">
          Plots zoned and waiting: {data.plots.residential ?? 0} for homes, {data.plots.commercial ?? 0} for shops and offices,{" "}
          {data.plots.industrial ?? 0} for factories.
        </p>
      </div>

      <div className="card">
        <h2>Municipal corporation</h2>
        <ul className="depts">
          {gov.map((d) => (
            <li key={d.key}>
              <b>{d.name}</b>
              <span className="muted">{d.does}</span>
              {d.head && (
                <span>
                  Led by{" "}
                  <button className="link" onClick={() => onPickPerson(d.head!.id)}>
                    {d.head.name}
                  </button>
                </span>
              )}
              {d.watching && <span className="watching">{d.watching}</span>}
              {(d.spent > 0 || d.done > 0) && (
                <small className="muted">
                  {d.spent > 0 && `Spent ${fmt(d.spent)}. `}
                  {d.done > 0 && `${d.done} project${d.done > 1 ? "s" : ""} finished.`}
                </small>
              )}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Builders and trusts</h2>
        <ul className="depts">
          {priv.map((d) => (
            <li key={d.key}>
              <b>{d.name}</b>
              <span className="muted">{d.does}</span>
              <small className="muted">{d.done > 0 ? `${d.done} building${d.done > 1 ? "s" : ""} finished so far.` : "Nothing finished yet."}</small>
            </li>
          ))}
        </ul>
        {data.finished.length > 0 && (
          <>
            <h3>Recently opened</h3>
            <div className="people">
              {data.finished.map((f) => (
                <button key={f.building} className="link" onClick={() => onPickBuilding(f.building)}>
                  {f.name} <small>day {f.day}</small>
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    </>
  );
}
