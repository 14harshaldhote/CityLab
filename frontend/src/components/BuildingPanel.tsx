import type { BuildingCard } from "../api/types";
import { fmt } from "./PersonPanel";

export default function BuildingPanel({ card, onPick }: { card: BuildingCard; onPick: (id: number) => void }) {
  return (
    <div className="card">
      <h2>{card.name}</h2>
      <p className="muted">
        {card.kind.replace("_", " ")} in {card.district} · {card.open ? "open now" : "closed now"}
      </p>
      {card.status === "construction" && (
        <p className="now">
          Under construction by <b>{card.owner}</b>: {Math.round((card.progress ?? 0) * 100)}% done.
          {card.planned ? ` It will have ${card.planned} homes.` : ""}
        </p>
      )}
      {!!card.opened_day && card.status !== "construction" && <p className="muted small">Built by {card.owner}, opened on day {card.opened_day}.</p>}
      <p>
        {card.households > 0 && `${card.residents} residents in ${card.households} homes. `}
        {card.jobs > 0 && `${card.workers} of ${card.jobs} jobs filled. `}
        {card.pupils > 0 && `${card.pupils} pupils. `}
        {card.inside_count} people inside right now.
      </p>
      {card.company && (
        <p>
          {card.company.public
            ? "A public service, paid for by the city budget."
            : card.company.funded_by
              ? `Run by City Bank (reserves ${fmt(card.company.balance ?? 0)}).`
              : `Company account ${fmt(card.company.balance ?? 0)}${card.company.debt ? `, owes ${fmt(card.company.debt)}` : ""}, credit score ${card.company.credit_score}.`}
        </p>
      )}
      <div className="people">
        {card.inside.map((p) => (
          <button key={p.id} className="link" onClick={() => onPick(p.id)}>
            {p.name} <small>{p.activity}</small>
          </button>
        ))}
      </div>
    </div>
  );
}
