import type { CrimeCase, Safety } from "../api/types";

const STATUS: Record<string, [label: string, color: string]> = {
  investigating: ["detectives on it", "#e0a21b"],
  "awaiting trial": ["awaiting trial", "#2c7fb8"],
  convicted: ["guilty", "#b3261e"],
  acquitted: ["not guilty", "#5f8a4a"],
  unsolved: ["case gone cold", "#8a8f98"],
};

function Badge({ status }: { status: string }) {
  const [label, color] = STATUS[status] ?? [status, "#8a8f98"];
  return (
    <span className="badge" style={{ background: color }}>
      {label}
    </span>
  );
}

function CaseRow({ c, onPick, onPickBuilding }: { c: CrimeCase; onPick: (id: number) => void; onPickBuilding: (id: number) => void }) {
  return (
    <li>
      <div>
        <b>{c.kind}</b> at{" "}
        {c.building !== null ? (
          <button className="link" onClick={() => onPickBuilding(c.building as number)}>
            {c.place}
          </button>
        ) : (
          c.place
        )}{" "}
        <Badge status={c.status} />
      </div>
      <small className="muted">
        {c.when} · ₹{c.value.toLocaleString("en-IN")} taken from{" "}
        {c.victim_id !== null ? (
          <button className="link" onClick={() => onPick(c.victim_id as number)}>
            {c.victim}
          </button>
        ) : (
          c.victim
        )}
        {c.caught_in_the_act && " · caught red-handed"}
        {c.cctv && " · on camera"}
        {c.witnesses > 0 && ` · ${c.witnesses} ${c.witnesses === 1 ? "witness" : "witnesses"}`}
      </small>
      {c.suspect && (
        <small>
          Suspect:{" "}
          <button className="link" onClick={() => onPick(c.suspect!.id)}>
            {c.suspect.name}
          </button>
          {c.hearing && c.status === "awaiting trial" && ` · in court ${c.hearing}`}
        </small>
      )}
      {c.verdict && <small>{c.verdict}</small>}
    </li>
  );
}

/** Police, thefts, cameras and the District Court. */
export default function SafetyPanel({ data, onPick, onPickBuilding }: { data: Safety; onPick: (id: number) => void; onPickBuilding: (id: number) => void }) {
  const m = data.month;
  const solvedPct = m.reported ? Math.round((100 * m.solved) / m.reported) : 0;
  const camPct = m.with_cctv ? Math.round((100 * m.solved_with_cctv) / m.with_cctv) : null;
  return (
    <>
      <div className="card">
        <h2>Today</h2>
        <ul className="moving">
          <li>
            <b>{data.today.crimes_reported}</b> thefts reported
          </li>
          <li>
            <b>{data.today.deterred}</b> put off by a passing patrol
          </li>
          <li>
            <b>{data.today.arrests}</b> arrests
          </li>
          <li>
            <b>{data.today.convicted}</b> found guilty
          </li>
          <li>
            <b>{data.police.patrols}</b> police cars out
          </li>
          <li>
            <b>{data.police.cameras}</b> CCTV cameras
          </li>
        </ul>
        <p className="muted small">
          In the last 30 days: {m.crimes} thefts, ₹{m.stolen.toLocaleString("en-IN")} taken, and {solvedPct}% of reported cases solved
          {camPct !== null && ` (${camPct}% when a camera saw it)`}.
        </p>
        <p className="muted small">
          Nobody in Kamalnagar is born a thief. People are tempted when money runs out, debts pile up or a job is lost, and a little more if they have
          been in trouble before. Faith, name and neighbourhood make no difference at all.
        </p>
      </div>

      <div className="card">
        <h2>District Court</h2>
        {data.court.length === 0 ? (
          <p className="muted">No cases waiting. The court sits on weekdays at 3 in the afternoon.</p>
        ) : (
          <ul className="cases">
            {data.court.map((c) => (
              <CaseRow key={c.id} c={c} onPick={onPick} onPickBuilding={onPickBuilding} />
            ))}
          </ul>
        )}
        {data.verdicts.length > 0 && (
          <>
            <h3>Recent verdicts</h3>
            <ul className="cases">
              {data.verdicts.map((c) => (
                <CaseRow key={c.id} c={c} onPick={onPick} onPickBuilding={onPickBuilding} />
              ))}
            </ul>
          </>
        )}
      </div>

      <div className="card">
        <h2>Case files</h2>
        {data.cases.length === 0 ? (
          <p className="muted">All quiet. Let the city run for a day or two.</p>
        ) : (
          <ul className="cases">
            {data.cases.map((c) => (
              <CaseRow key={c.id} c={c} onPick={onPick} onPickBuilding={onPickBuilding} />
            ))}
          </ul>
        )}
        <p className="muted small">
          Detectives work on reported thefts each morning. A camera or a witness makes the evidence stronger, and stronger evidence makes a guilty verdict
          more likely. Cases nobody can crack go cold after three weeks.
        </p>
      </div>

      <div className="card">
        <h2>Behind bars</h2>
        {data.in_jail.length === 0 ? (
          <p className="muted">Nobody is in jail right now.</p>
        ) : (
          <ul className="jail">
            {data.in_jail.map((p) => (
              <li key={p.id}>
                <button className="link" onClick={() => onPick(p.id)}>
                  {p.name}
                </button>{" "}
                <small className="muted">until {p.until}</small>
              </li>
            ))}
          </ul>
        )}
        <h3>CCTV cameras</h3>
        <ul className="jail">
          {data.cameras.map((c) => (
            <li key={c.node}>{c.name}</li>
          ))}
        </ul>
        <p className="muted small">
          When thefts keep happening around the same corner, the police put up another camera there, as long as the city can afford it.
        </p>
      </div>
    </>
  );
}
