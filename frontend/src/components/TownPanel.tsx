import type { Town } from "../api/types";

/** 2,00,000 written the Indian way. */
export const lakh = (v: number) => Math.round(v).toLocaleString("en-IN");

const show = (v: number | null, unit: string) => (v == null ? "–" : unit === "₹" ? `₹${lakh(v)}` : `${v.toLocaleString("en-IN")}${unit}`);

/** How close a figure is to the real one: green within 15%, amber within 40%, red beyond. */
function closeness(ours: number | null, real: number): string {
  if (ours == null || real === 0) return "";
  const off = Math.abs(ours - real) / Math.abs(real);
  return off <= 0.15 ? "near" : off <= 0.4 ? "off" : "far";
}

/** The whole town: who lives in it, and how it measures up against a real Indian town of the same size. */
export default function TownPanel({ town }: { town: Town }) {
  const ages = Object.entries(town.ages);
  const most = Math.max(1, ...ages.map(([, n]) => n));
  return (
    <div className="card town">
      <h2>The whole town · {lakh(town.population)} people</h2>
      <p className="muted small">
        {lakh(town.on_map)} live on the map, where you can follow each one. The other {lakh(town.in_books)} are counted in the town's books,
        neighbourhood by neighbourhood, like a census: they are born, grow up, work, fall ill, pay taxes and move in, at the rates the people on the map
        and real Indian towns show. About {lakh(town.households)} households.
      </p>
      <ul className="faiths">
        {ages.map(([label, n]) => (
          <li key={label}>
            <span>{label}</span>
            <i style={{ width: `${Math.max(1, (100 * n) / most)}%` }} />
            <b>{lakh(n)}</b>
          </li>
        ))}
      </ul>
      <p className="muted small">
        {town.women_per_1000_men} women for every 1,000 men · about {lakh(town.services.police)} police, {lakh(town.services.doctors)} doctors and{" "}
        {lakh(town.services.teachers)} teachers
      </p>
      <h3>Kamalnagar and a real Indian town</h3>
      <table className="compare">
        <thead>
          <tr>
            <th />
            <th>Kamalnagar</th>
            <th>Real</th>
          </tr>
        </thead>
        <tbody>
          {town.compare.map((c) => (
            <tr key={c.label} title={c.source}>
              <td>{c.label}</td>
              <td className={closeness(c.kamalnagar, c.real)}>{show(c.kamalnagar, c.unit)}</td>
              <td className="muted">{show(c.real, c.unit)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="muted small">Real figures: Census 2011, SRS, PLFS 2023-24, NFHS-5, NCRB 2022, BPR&amp;D and the World Happiness Report. Hover a row for its source.</p>
    </div>
  );
}
