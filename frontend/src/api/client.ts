import type { Network } from "../components/EgoGraph";
import type { Agencies, Answer, AskStatus, CityReport, History, Safety, WhatIfJob, Transport, BuildingCard, CityEvent, Economy, CityMap, DailyRow, Frame, PersonCard, Summary } from "./types";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

const TOKEN_KEY = "citylab-admin-token";

function savedToken(): string {
  try {
    return localStorage.getItem(TOKEN_KEY) ?? "";
  } catch {
    return "";
  }
}

async function post<T>(path: string, body: unknown, retry = true): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const token = savedToken();
  if (token) headers["X-CityLab-Token"] = token;
  const res = await fetch(path, { method: "POST", headers, body: JSON.stringify(body) });
  if (res.status === 401 && retry) {
    // the owner set an admin token for actions that wipe or rewrite the city
    const given = window.prompt("This needs the city's admin token (CITYLAB_ADMIN_TOKEN):");
    if (given) {
      try {
        localStorage.setItem(TOKEN_KEY, given);
      } catch {
        /* private mode: just use it once */
      }
      return post<T>(path, body, false);
    }
  }
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  city: () => get<CityMap>("/api/city"),
  summary: () => get<Summary>("/api/summary"),
  person: (id: number) => get<PersonCard>(`/api/people/${id}`),
  network: (id: number) => get<Network>(`/api/people/${id}/network`),
  building: (id: number) => get<BuildingCard>(`/api/buildings/${id}`),
  search: (q: string) => get<{ id: number; name: string; age: number; alive: boolean; activity: string | null }[]>(`/api/people?q=${encodeURIComponent(q)}&limit=30`),
  events: (kind?: string, limit = 60) => get<CityEvent[]>(`/api/events?limit=${limit}${kind ? `&kind=${kind}` : ""}`),
  economy: () => get<Economy>("/api/economy"),
  agencies: () => get<Agencies>("/api/agencies"),
  transport: () => get<Transport>("/api/transport"),
  safety: () => get<Safety>("/api/safety"),
  history: () => get<History>("/api/history"),
  travel: (t: number) => post<{ t: number; label: string; seconds: number }>("/api/travel", { t }),
  setRule: (lever: string, value: number) => post<Record<string, number>>("/api/rules", { lever, value }),
  whatIf: (lever: string, value: number, days: number) => post<WhatIfJob>("/api/whatif", { lever, value, days }),
  whatIfJob: (id: number) => get<WhatIfJob>(`/api/whatif/${id}`),
  reports: (by: "month" | "year") => get<CityReport[]>(`/api/reports?by=${by}`),
  ask: (question: string) => post<Answer>("/api/ask", { question }),
  askStatus: () => get<AskStatus>("/api/ask/status"),
  daily: () => get<DailyRow[]>("/api/stats/daily"),
  control: (body: { playing?: boolean; speed?: number; advance_minutes?: number }) => post<{ playing: boolean; speed: number; t: number }>("/api/control", body),
  reset: (seed: number, population: number) => post<{ seed: number; population: number }>("/api/reset", { seed, population }),
};

/** Live frames over a WebSocket, reconnecting with backoff if the server restarts. */
export function liveFrames(onFrame: (f: Frame) => void, onStatus: (connected: boolean) => void): () => void {
  let socket: WebSocket | null = null;
  let closed = false;
  let delay = 500;
  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${proto}://${location.host}/api/ws`);
    socket.onopen = () => {
      delay = 500;
      onStatus(true);
    };
    socket.onmessage = (m) => onFrame(JSON.parse(m.data) as Frame);
    socket.onclose = () => {
      onStatus(false);
      if (!closed) setTimeout(connect, (delay = Math.min(delay * 2, 8000)));
    };
  };
  connect();
  return () => {
    closed = true;
    socket?.close();
  };
}
