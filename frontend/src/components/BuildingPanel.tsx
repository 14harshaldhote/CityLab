import type { BuildingCard } from "../api/types";

export default function BuildingPanel({ card, onPick }: { card: BuildingCard; onPick: (id: number) => void }) {
  return (
    <div className="card">
      <h2>{card.name}</h2>
      <p className="muted">
        {card.kind.replace("_", " ")} in {card.district} · {card.open ? "open now" : "closed now"}
      </p>
      <p>
        {card.households > 0 && `${card.residents} residents in ${card.households} homes. `}
        {card.jobs > 0 && `${card.workers} of ${card.jobs} jobs filled. `}
        {card.pupils > 0 && `${card.pupils} pupils. `}
        {card.inside_count} people inside right now.
      </p>
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
