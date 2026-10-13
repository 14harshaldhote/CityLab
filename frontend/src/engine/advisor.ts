import type { DailyRow, Economy, Summary } from "../api/types";

/**
 * The city advisor: reads the numbers and says what deserves attention, in plain words.
 * Today it is a set of transparent rules; the local AI model can take over the same
 * slot later, with these rules as its fallback.
 */

export type Tone = "good" | "watch" | "act";

export interface Insight {
  tone: Tone;
  title: string;
  detail: string;
}

const pct = (a: number, b: number) => (b > 0 ? Math.round((100 * a) / b) : 0);

function change(rows: DailyRow[], key: keyof DailyRow, days: number): number | null {
  if (rows.length < days + 1) return null;
  const now = rows[rows.length - 1][key] as number;
  const then = rows[rows.length - 1 - days][key] as number;
  return now - then;
}

export function advise(summary: Summary | null, econ: Economy | null, daily: DailyRow[]): Insight[] {
  if (!summary) return [];
  const out: Insight[] = [];
  const workforce = summary.employed + summary.unemployed;
  const jobless = pct(summary.unemployed, workforce);
  const homes = summary.households + summary.free_homes;

  if (summary.free_homes < Math.max(5, homes * 0.05)) {
    out.push({ tone: "act", title: "Homes are almost full", detail: `Only ${summary.free_homes} free homes are left, so newcomers and grown-up children have nowhere to go.` });
  } else if (summary.vacancies > 2 * Math.max(1, summary.unemployed)) {
    out.push({ tone: "good", title: "Jobs are waiting", detail: `${summary.vacancies} jobs are open and ${summary.free_homes} homes are free, so the city will keep attracting newcomers.` });
  }
  if (jobless >= 8) {
    out.push({ tone: "act", title: `${jobless}% are out of work`, detail: `${summary.unemployed} people are looking for work. Watch for households giving up and leaving.` });
  } else if (workforce > 0) {
    out.push({ tone: "good", title: `Only ${jobless}% out of work`, detail: `${summary.employed} people have jobs.` });
  }

  const budget = change(daily, "city", 7);
  if (budget !== null && econ) {
    if (budget < 0 && econ.city + budget * 8 < 0) {
      out.push({ tone: "act", title: "City budget heading for the red", detail: `It fell by ${Math.round(-budget).toLocaleString()} this week; at this pace the city will need a loan within two months.` });
    } else if (budget < 0) {
      out.push({ tone: "watch", title: "City budget shrinking", detail: `Down ${Math.round(-budget).toLocaleString()} this week, still ${Math.round(econ.city).toLocaleString()} in the bank.` });
    } else {
      out.push({ tone: "good", title: "City budget growing", detail: `Up ${Math.round(budget).toLocaleString()} this week.` });
    }
  }
  if (econ && econ.in_debt > summary.population * 0.03) {
    out.push({ tone: "watch", title: `${econ.in_debt} people are overdrawn`, detail: `City Bank has ${econ.loans} loans worth ${Math.round(econ.loans_outstanding).toLocaleString()} outstanding.` });
  }
  if (econ && econ.struggling_companies.length > 0) {
    const c = econ.struggling_companies[0];
    out.push({ tone: "watch", title: `${econ.struggling_companies.length} companies losing money`, detail: `${c.name} is the worst, ${Math.round(c.balance).toLocaleString()} in the red. Lay-offs may follow.` });
  }

  if (daily.length >= 7) {
    const last = daily.slice(-30);
    const births = last.reduce((s, r) => s + r.births, 0);
    const deaths = last.reduce((s, r) => s + r.deaths, 0);
    const arrived = last.reduce((s, r) => s + r.arrived, 0);
    const left = last.reduce((s, r) => s + r.left, 0);
    const grow = births + arrived - deaths - left;
    out.push({
      tone: grow >= 0 ? "good" : "watch",
      title: grow >= 0 ? `Population up ${grow} lately` : `Population down ${-grow} lately`,
      detail: `Over the last ${last.length} days: ${births} born, ${deaths} died, ${arrived} moved in, ${left} moved away.`,
    });
  }
  const order: Record<Tone, number> = { act: 0, watch: 1, good: 2 };
  return out.sort((a, b) => order[a.tone] - order[b.tone]).slice(0, 5);
}
