import type { CompanyRow, Economy } from "../api/types";
import { fmt } from "./PersonPanel";

function Companies({ rows, onPick }: { rows: CompanyRow[]; onPick: (id: number) => void }) {
  return (
    <table className="table">
      <tbody>
        {rows.map((c) => (
          <tr key={c.id}>
            <td>
              <button className="link" onClick={() => onPick(c.id)}>
                {c.name}
              </button>
            </td>
            <td className="num">
              {c.workers}/{c.jobs}
            </td>
            <td className={`num ${c.balance < 0 ? "warn" : ""}`}>{fmt(c.balance)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function EconomyPanel({ econ, onPickBuilding }: { econ: Economy; onPickBuilding: (id: number) => void }) {
  const flows = Object.entries(econ.flows).filter(([k]) => k !== "opening balances");
  return (
    <div className="card">
      <h2>City Bank</h2>
      <p>
        Base rate <b>{(econ.base_rate * 100).toFixed(1)}%</b>, savings earn {(econ.savings_rate * 100).toFixed(1)}%, a typical loan costs{" "}
        {(econ.loan_rate_typical * 100).toFixed(1)}%. {econ.loans} loans outstanding worth <b>{fmt(econ.loans_outstanding)}</b>. Reserves {fmt(econ.bank)}.
      </p>
      <p>
        Residents hold <b>{fmt(econ.money_people)}</b> (median {fmt(econ.median_balance)}, {econ.in_debt} overdrawn). Companies hold {fmt(econ.money_companies)}.
      </p>
      <h2>City budget</h2>
      <p>
        The city has <b>{fmt(econ.city)}</b>.
      </p>
      <h3>Money moved today so far</h3>
      <ul className="legend-list one">
        {flows.length === 0 && <li className="muted">The books are settled at midnight; daytime meals and shopping show up here.</li>}
        {flows.map(([k, v]) => (
          <li key={k}>
            {k} <b>{fmt(v)}</b>
          </li>
        ))}
      </ul>
      <h3>Richest companies (staff, cash)</h3>
      <Companies rows={econ.richest_companies} onPick={onPickBuilding} />
      {econ.struggling_companies.length > 0 && (
        <>
          <h3>In trouble</h3>
          <Companies rows={econ.struggling_companies} onPick={onPickBuilding} />
        </>
      )}
    </div>
  );
}
