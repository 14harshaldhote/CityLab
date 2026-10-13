import type { PersonCard, PersonRef } from "../api/types";

const TRAITS: [string, string][] = [
  ["openness", "Curious"],
  ["conscientiousness", "Organised"],
  ["extraversion", "Outgoing"],
  ["agreeableness", "Kind"],
  ["neuroticism", "Anxious"],
];

function Bar({ label, value }: { label: string; value: number }) {
  return (
    <div className="bar">
      <span>{label}</span>
      <div>
        <i style={{ width: `${Math.round(value * 100)}%` }} />
      </div>
      <b>{Math.round(value * 100)}</b>
    </div>
  );
}

function Who({ p, onPick }: { p: PersonRef | null; onPick: (id: number) => void }) {
  if (!p) return null;
  return (
    <button className="link" onClick={() => onPick(p.id)}>
      {p.name} ({p.age}
      {p.alive ? "" : ", died"})
    </button>
  );
}

export default function PersonPanel({ card, onPick }: { card: PersonCard; onPick: (id: number) => void }) {
  return (
    <div className="card">
      <h2>{card.name}</h2>
      <p className="muted">
        {card.sex === "F" ? "Woman" : "Man"}, {Math.floor(card.age)} ({card.stage}) · lives at {card.home.name}, {card.home.district}
        {!card.alive && " · no longer in the city"}
      </p>
      {card.alive && (
        <p className="now">
          Now <b>{card.activity}</b>
          {card.place ? ` at ${card.place}` : card.heading_to ? ` to ${card.heading_to}` : ""}
          {card.until ? ` until ${card.until.slice(-5)}` : ""}
        </p>
      )}
      <p>
        {card.job
          ? `Works at ${card.job.place}, shift ${card.job.shift}, earns ${card.job.wage_per_day.toFixed(0)} a day.`
          : card.school
            ? `Pupil at ${card.school}.`
            : card.retired
              ? "Retired."
              : card.unemployed
                ? "Looking for work."
                : "Not working."}
      </p>

      <h3>Family</h3>
      <div className="people">
        {card.partner && (
          <span>
            Partner: <Who p={card.partner} onPick={onPick} />
          </span>
        )}
        {card.parents.filter(Boolean).length > 0 && (
          <span>
            Parents:{" "}
            {card.parents.map((p, i) => (
              <Who key={i} p={p} onPick={onPick} />
            ))}
          </span>
        )}
        {card.children.length > 0 && (
          <span>
            Children:{" "}
            {card.children.map((p, i) => (
              <Who key={i} p={p} onPick={onPick} />
            ))}
          </span>
        )}
        {card.household.length > 0 && (
          <span>
            Lives with:{" "}
            {card.household.map((p, i) => (
              <Who key={i} p={p} onPick={onPick} />
            ))}
          </span>
        )}
      </div>

      <div className="cols">
        <div>
          <h3>Needs · mood {Math.round(card.mood * 100)}</h3>
          {Object.entries(card.needs).map(([k, v]) => (
            <Bar key={k} label={k} value={v} />
          ))}
          <Bar label="health" value={card.health} />
          <Bar label="skill" value={card.skill} />
        </div>
        <div>
          <h3>Personality</h3>
          {TRAITS.map(([k, label]) => (
            <Bar key={k} label={label} value={card.personality[k]} />
          ))}
        </div>
      </div>

      <h3>Friends ({card.friend_count})</h3>
      <div className="people">
        {card.friends.length === 0 && <span className="muted">No close friends yet.</span>}
        {card.friends.map((f) => (
          <button key={f.id} className="link" onClick={() => onPick(f.id)} title={`tie strength ${f.strength}`}>
            {f.name} <small>{Math.round(f.strength * 100)}</small>
          </button>
        ))}
      </div>

      <h3>Life story</h3>
      <ul className="events">
        {card.life.length === 0 && <li className="muted">Nothing recorded yet.</li>}
        {card.life.map((e) => (
          <li key={e.id}>
            <time>{e.when}</time> {e.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
