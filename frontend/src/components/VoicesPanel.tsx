import type { Worries } from "../api/types";

/** The newest things people said, always in view over the city: each line is read off that person's own life. */
export function VoiceTicker({ worries, onPick }: { worries: Worries | null; onPick: (id: number) => void }) {
  const said = worries?.said.slice(0, 3) ?? [];
  if (!said.length) return null;
  return (
    <div className="voice-ticker" aria-live="polite">
      <b className="ticker-head">People are saying</b>
      {said.map((v) => (
        <p key={`${v.t}-${v.id}`}>
          <button className="link" onClick={() => onPick(v.id)}>
            {v.name}
          </button>{" "}
          <span className="muted">{`(${v.feeling}, ${v.district})`}</span>
          {`: “${v.text}”`}
        </p>
      ))}
    </div>
  );
}

/** What is making people unhappy right now, counted person by person, and what they have said lately. */
export function WorriesCard({ worries, onPick }: { worries: Worries | null; onPick: (id: number) => void }) {
  if (!worries) return null;
  const top = worries.reasons[0]?.count || 1;
  return (
    <div className="card worries">
      <h2>What's bothering people</h2>
      <p>
        <b>{worries.unhappy.toLocaleString("en-IN")}</b> of {worries.adults.toLocaleString("en-IN")} adults are unhappy right now (
        {Math.round((100 * worries.unhappy) / Math.max(1, worries.adults))}%). Each one is counted under the thing weighing on them most, read from
        their own life:
      </p>
      <ul className="worry-bars">
        {worries.reasons.map((r) => (
          <li key={r.about} title={`${r.example.name}: “${r.example.text}”`}>
            <span>{r.about}</span>
            <div>
              <i style={{ width: `${Math.round((100 * r.count) / top)}%` }} />
            </div>
            <b>{r.count}</b>
          </li>
        ))}
      </ul>
      <h3>In their own words</h3>
      {worries.said.length === 0 ? (
        <p className="muted small">Nobody has spoken up yet. People only say something once it gets to them.</p>
      ) : (
        <ul className="voices">
          {worries.said.slice(0, 12).map((v) => (
            <li key={`${v.t}-${v.id}`}>
              <time>
                {v.when} · {v.feeling} · about {v.about}
              </time>
              <button className="link" onClick={() => onPick(v.id)}>
                {v.name}
              </button>
              {`, ${v.district}: “${v.text}”`}
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">
        Nobody writes these lines: each comes from what the town did to that person. Everyone has their own limits, so the same bad week leaves one
        neighbour fuming and the next one calm, and people only speak up once a feeling passes their own limit.
      </p>
    </div>
  );
}
