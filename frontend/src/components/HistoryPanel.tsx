import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import type { CityReport, History, WhatIfJob } from "../api/types";
import { simLabel } from "../engine/view";
import LineChart from "./LineChart";

const DAY = 1440;
const SAME = "#8a8f98";
const CHANGED = "#c4572e";

/** A lever's setting in words, the same way the city council would put it. */
export function describe(lever: string, v: number): string {
  if (lever === "income_tax" || lever === "base_rate") return `${Math.round(v * 100)}%`;
  if (lever === "patrols") return v === 0 ? "none" : `${v}×`;
  return `₹${v.toLocaleString("en-IN")}`;
}

const fmt = (v: number) => Math.round(v).toLocaleString("en-IN");

function Jumps({ data, onTravel }: { data: History; onTravel: (t: number) => Promise<unknown> }) {
  const h = data.horizon;
  const jumps: [string, number][] = [
    ["An hour ago", h - 60],
    ["This morning", Math.floor(h / DAY) * DAY + 8 * 60],
    ["Yesterday", h - DAY],
    ["A week ago", h - 7 * DAY],
    ["A month ago", h - 30 * DAY],
    ["The very start", 0],
  ];
  const seen = new Set<number>();
  return (
    <div className="chips">
      {jumps
        .filter(([, t]) => t >= 0 && t <= h && !seen.has(t) && seen.add(t))
        .map(([label, t]) => (
          <button key={label} onClick={() => onTravel(t)} title={simLabel(t)}>
            {label}
          </button>
        ))}
    </div>
  );
}

function Result({ job, onAdopt }: { job: WhatIfJob; onAdopt: () => void }) {
  const r = job.result!;
  const days = r.same_rows.map((row) => row.day);
  const pair = (key: keyof (typeof r.same_rows)[number], label: string) => [
    { label: `${label}, as it is`, color: SAME, values: r.same_rows.map((row) => Number(row[key] ?? 0)) },
    { label: `${label}, what if`, color: CHANGED, values: r.changed_rows.map((row) => Number(row[key] ?? 0)) },
  ];
  const charts = useMemo(() => {
    const pick: Record<string, [keyof (typeof r.same_rows)[number], string][]> = {
      bus_fare: [["trips_bus", "bus rides"], ["trips_auto", "auto rides"]],
      income_tax: [["city", "city budget"], ["median_balance", "typical balance"]],
      benefit: [["crimes", "thefts"], ["median_balance", "typical balance"]],
      patrols: [["crimes", "thefts"], ["arrests", "arrests"]],
      base_rate: [["loans_outstanding", "money owed to the bank"], ["median_balance", "typical balance"]],
    };
    return (pick[job.lever] ?? [["population", "people"]]).map(([k, label]) => ({ label, series: pair(k, label) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.id]);
  return (
    <>
      <p>{r.story}</p>
      <div className="ripple">
        <b>{Math.round(r.ripple * 100)}%</b>
        <span className="small">
          of people's lives turned out a little differently ({fmt(r.touched)} of {fmt(r.people)}). That's the butterfly effect: one changed rule
          nudges a few people, they nudge the people they meet, pay and buy from, and the ripples spread through the city.
        </span>
      </div>
      <table className="compare">
        <thead>
          <tr>
            <th />
            <th>As it is</th>
            <th>What if</th>
            <th>Change</th>
          </tr>
        </thead>
        <tbody>
          {r.measures.map((m) => (
            <tr key={m.key}>
              <td>
                {m.label}
                {m.how === "sum" && <small className="muted"> (total)</small>}
              </td>
              <td>{fmt(m.same)}</td>
              <td>{fmt(m.changed)}</td>
              <td className={m.better === true ? "good" : m.better === false ? "bad" : ""}>
                {m.diff === 0 ? "same" : `${m.diff > 0 ? "+" : ""}${fmt(m.diff)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {charts.map((c) => (
        <LineChart key={c.label} days={days} series={c.series} height={120} />
      ))}
      {r.stories.length > 0 && (
        <>
          <h3>Meanwhile, in the what-if city</h3>
          <ul className="events">
            {r.stories.slice(0, 6).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        </>
      )}
      <button className="primary" onClick={onAdopt}>
        Make it the rule from now on
      </button>
    </>
  );
}

/** The time machine: go back to any moment, try a "what if?", and read the city's reports. */
export default function HistoryPanel({ onTravel }: { onTravel: (t: number) => Promise<unknown> }) {
  const [data, setData] = useState<History | null>(null);
  const [lever, setLever] = useState("bus_fare");
  const [value, setValue] = useState<number | null>(null);
  const [days, setDays] = useState(7);
  const [job, setJob] = useState<WhatIfJob | null>(null);
  const [by, setBy] = useState<"month" | "year">("month");
  const [reports, setReports] = useState<CityReport[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () =>
      api.history().then((h) => {
        setData(h);
        setJob(h.whatif);
      }, () => undefined);
    load();
    const id = setInterval(load, job?.status === "running" ? 1000 : 3000);
    return () => clearInterval(id);
  }, [job?.status]);

  useEffect(() => {
    const load = () => api.reports(by).then(setReports, () => undefined);
    load();
    const id = setInterval(load, 10000);
    return () => clearInterval(id);
  }, [by]);

  if (!data) return <div className="card muted">Winding up the time machine...</div>;
  const info = data.levers[lever];
  const now = data.rules[lever];
  const choice = value ?? info.options.find((o) => o !== now) ?? now;
  const run = () => {
    setError(null);
    api.whatIf(lever, choice, days).then(setJob, (e) => setError(String(e)));
  };
  const adopt = () => {
    if (!job) return;
    api.setRule(job.lever, job.value).then(() => api.history().then(setData), (e) => setError(String(e)));
  };
  const back = data.horizon - data.t > 1;

  return (
    <>
      <div className="card">
        <h2>Time machine</h2>
        <p>
          {back ? (
            <>
              You're visiting <b>{data.label}</b>. The latest moment is {data.horizon_label}. Press Play to watch history repeat itself exactly,
              or change a rule to send it down a different path.
            </>
          ) : (
            <>Kamalnagar remembers everything since it was founded. Drag the slider under the city, or jump straight to a moment:</>
          )}
        </p>
        <Jumps data={data} onTravel={onTravel} />
        <p className="muted small">
          The city takes a snapshot of itself every midnight ({data.snapshots} so far, {data.megabytes} MB). Going back loads the snapshot just
          before and replays the minutes in between. Because the city follows its rules exactly, the replay comes out the same every time.
        </p>
      </div>

      <div className="card">
        <h2>What if?</h2>
        <p className="small">
          Run two copies of the city side by side from <b>{data.label}</b>: one as it is, one with a single rule changed. Then compare.
        </p>
        <div className="chips">
          {Object.entries(data.levers).map(([k, l]) => (
            <button
              key={k}
              className={lever === k ? "on" : ""}
              onClick={() => {
                setLever(k);
                setValue(null);
              }}
            >
              {l.name}
            </button>
          ))}
        </div>
        <p className="muted small">
          {info.story} Right now: <b>{describe(lever, now)}</b>
          {lever === "patrols" && now === 0 ? "" : ` ${info.unit}`}.
        </p>
        <div className="chips" aria-label="Try">
          <span className="small">Try</span>
          {info.options
            .filter((o) => o !== now)
            .map((o) => (
              <button key={o} className={choice === o ? "on" : ""} onClick={() => setValue(o)}>
                {describe(lever, o)}
              </button>
            ))}
        </div>
        <div className="chips" aria-label="For">
          <span className="small">for</span>
          {data.whatif_days.map((d) => (
            <button key={d} className={days === d ? "on" : ""} onClick={() => setDays(d)}>
              {d} days
            </button>
          ))}
        </div>
        <button className="primary" onClick={run} disabled={job?.status === "running"}>
          Run both cities
        </button>
        {error && <p className="warn small">{error}</p>}
        {job && (
          <div className="whatif">
            <h3>
              {job.lever_name}: {describe(job.lever, job.was)} → {describe(job.lever, job.value)}, {job.days} days from {job.from}
            </h3>
            {job.status === "running" && (
              <>
                <div className="progress">
                  <i style={{ width: `${Math.round(job.progress * 100)}%` }} />
                </div>
                <p className="muted small">Both cities are living through day {Math.min(job.days, Math.floor(job.progress * job.days) + 1)}...</p>
              </>
            )}
            {job.status === "failed" && <p className="warn">Something went wrong: {job.error}</p>}
            {job.status === "cancelled" && <p className="muted">Stopped.</p>}
            {job.status === "done" && job.result && <Result job={job} onAdopt={adopt} />}
          </div>
        )}
      </div>

      <div className="card">
        <h2>City reports</h2>
        <div className="chips">
          <button className={by === "month" ? "on" : ""} onClick={() => setBy("month")}>
            Monthly
          </button>
          <button className={by === "year" ? "on" : ""} onClick={() => setBy("year")}>
            Yearly
          </button>
        </div>
        {reports.length === 0 && <p className="muted">The first report comes out after the first day.</p>}
        {reports.map((r) => (
          <div className="report" key={r.key}>
            <h3>
              {r.period}
              {!r.complete && <small className="muted"> · so far ({r.days} days)</small>}
            </h3>
            <p className="small">{r.text}</p>
            <div className="figures">
              <span>
                {fmt(r.population_start)} → {fmt(r.population)} people
              </span>
              <span>{fmt(r.births)} born</span>
              <span>{fmt(r.crimes)} thefts</span>
              <span>{fmt(r.trips_bus)} bus rides</span>
              <span>₹{fmt(r.tax)} tax</span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
