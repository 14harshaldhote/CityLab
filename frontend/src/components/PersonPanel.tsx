import type { PersonCard, PersonRef } from "../api/types";
import EgoGraph, { type Network } from "./EgoGraph";

export const fmt = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 0 });

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

const PLACE_OF_WORSHIP: Record<string, string> = {
  Hindu: "the mandir",
  Muslim: "the masjid",
  Christian: "church",
  Sikh: "the gurudwara",
  Buddhist: "the Buddha vihar",
  Jain: "the derasar",
  Parsi: "the agiary",
};

function faithLine(card: PersonCard): string | null {
  const place = PLACE_OF_WORSHIP[card.religion];
  if (!place || card.age < 6) return null;
  const how = card.devotion > 0.6 ? "often" : card.devotion > 0.35 ? "now and then" : "mostly on festival days";
  return `Goes to ${place} ${how}.`;
}

const TOPICS: [string, string][] = [
  ["taxes", "Taxes"],
  ["police", "The police"],
  ["hospital", "The hospital"],
  ["buses", "The buses"],
  ["jobs", "Finding work"],
  ["council", "The council"],
];

function opinionWord(v: number): string {
  return v < -0.5 ? "very unhappy" : v < -0.15 ? "unhappy" : v < 0.15 ? "fine" : v < 0.5 ? "happy" : "very happy";
}

function InnerLife({ card }: { card: PersonCard }) {
  const mind = card.mind;
  if (!mind || !card.alive) return null;
  const f = mind.feelings;
  return (
    <>
      <h3>Inner life · happiness {Math.round((card.happiness ?? 0) * 100)}</h3>
      <p>
        Feels <b>{mind.feeling}</b>.
        {mind.known_for && ` Known around town as ${mind.known_for.startsWith("a ") || mind.known_for.startsWith("known") ? "" : "someone who "}${mind.known_for}.`}
        {card.illness && ` Has ${card.illness.what} (${card.illness.how})${card.illness.seen_doctor ? ", seen a doctor" : ""}.`}
        {card.cash_job && " Paid cash in hand, so no income tax is taken."}
      </p>
      <div className="cols">
        <div>
          <Bar label="joy" value={f.joy} />
          <Bar label="sadness" value={f.sadness} />
          <Bar label="anger" value={f.anger} />
          <Bar label="fear" value={f.fear} />
          <Bar label="thinks for self" value={mind.independence} />
        </div>
        <div>
          {TOPICS.map(([k, label]) => (
            <div className="bar" key={k} title={`${(5 + 5 * (mind.opinions[k] ?? 0)).toFixed(1)} out of 10`}>
              <span>{label}</span>
              <div>
                <i style={{ width: `${Math.round(50 + 50 * (mind.opinions[k] ?? 0))}%` }} />
              </div>
              <b>{opinionWord(mind.opinions[k] ?? 0)}</b>
            </div>
          ))}
        </div>
      </div>
      <p className="muted small">Feelings follow what happens to them and fade back to their nature. Opinions come from their own life, then from friends; the more independent they are, the less friends sway them.</p>
    </>
  );
}

export default function PersonPanel({ card, net, onPick }: { card: PersonCard; net: Network | null; onPick: (id: number) => void }) {
  return (
    <div className="card">
      <h2>{card.name}</h2>
      <p className="muted">
        {card.sex === "F" ? "Woman" : "Man"}, {Math.floor(card.age)} ({card.stage}) · {card.religion} · lives at {card.home.name}
        {card.home.name.includes(card.home.district) ? "" : `, ${card.home.district}`}
        {!card.alive && " · no longer in the city"}
      </p>
      {card.alive && faithLine(card) && <p className="muted small">{faithLine(card)}</p>}
      {card.alive && (
        <p className="now">
          Now <b>{card.travel ? card.travel[0].toLowerCase() + card.travel.slice(1) : card.activity}</b>
          {card.place ? ` at ${card.place}` : card.heading_to ? `, going to ${card.heading_to}` : ""}
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
      {card.in_jail_until && <p className="warn">In jail until {card.in_jail_until}.</p>}
      {!card.in_jail_until && (card.convictions ?? 0) > 0 && (
        <p className="muted small">
          Has been found guilty of theft {card.convictions === 1 ? "once" : `${card.convictions} times`}. Hard times make it more tempting to slip again.
        </p>
      )}

      <h3>Money</h3>
      <p>
        Bank balance <b>{fmt(card.money.balance)}</b> · credit score {card.money.credit_score}
        {card.money.debt > 0 && (
          <>
            {" "}
            · owes {fmt(card.money.debt)} on {card.money.loans.length} loan{card.money.loans.length > 1 ? "s" : ""}
            {card.money.loans.some((l) => l.missed > 0) && <span className="warn"> (behind on payments)</span>}
          </>
        )}
      </p>

      <InnerLife card={card} />

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

      {net && net.nodes.length > 1 && (
        <>
          <h3>Their corner of the social graph</h3>
          <EgoGraph net={net} onPick={onPick} />
          <p className="muted small">Pink: partner, blue: parents and children, purple: siblings, grey: friends. Thicker means closer.</p>
        </>
      )}

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
