import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Answer, AskStatus } from "../api/types";

export const SUGGESTIONS = [
  "How many babies were born last week?",
  "Why were there thefts in Shivaji Nagar?",
  "Which street has the worst traffic?",
  "How is the city doing?",
  "What happened yesterday?",
  "When did it last rain?",
];

export type AskTurn = { question: string; answer?: Answer; error?: string };

/** "Lots of jobs [1] and a theft [3]" -> text with the numbers as little buttons. */
export function citations(text: string): (string | number)[] {
  return text.split(/\[(\d+)\]/).map((part, i) => (i % 2 ? Number(part) : part)).filter((p) => p !== "");
}

const ATTACKS: Record<string, string> = {
  exposure: "asking for its secret instructions",
  injection: "trying to override its rules",
  jailbreak: "role-play to get round its rules",
  hijack: "steering it off the city",
  poisoning: "planted orders in the records",
};

function Shield({ status }: { status: AskStatus }) {
  const total = Object.values(status.blocked).reduce((a, b) => a + b, 0);
  if (!total) return null;
  return (
    <details className="ask-shield">
      <summary>
        Shield: {total} tricky {total === 1 ? "question" : "questions"} stopped
      </summary>
      <ul>
        {status.incidents.slice(0, 6).map((x, i) => (
          <li key={i}>
            <b>{ATTACKS[x.kind] ?? x.kind}</b> (in the {x.where}): <q>{x.question}</q>
          </li>
        ))}
      </ul>
    </details>
  );
}

function Badge({ status }: { status: AskStatus | null }) {
  if (!status) return null;
  if (status.can_write)
    return (
      <p className="ask-badge on">
        Free AI on: <b>{status.chat_model}</b> is running on this computer. {status.can_embed && `${status.embedded.toLocaleString("en-IN")} of ${status.records.toLocaleString("en-IN")} records read for meaning.`}
      </p>
    );
  return (
    <details className="ask-badge">
      <summary>Answering from the records. Start the free AI for answers in its own words.</summary>
      <p>
        The city can use a free, open-source language model that runs on your own computer, with no account and no key. Install{" "}
        <a href="https://ollama.com" target="_blank" rel="noreferrer">
          Ollama
        </a>
        , then run <code>ollama pull {status.chat_model}</code> and <code>ollama pull {status.embed_model}</code>. With Docker, it is just{" "}
        <code>docker compose --profile ai up</code>.
      </p>
      {status.running && !status.can_write && <p>Ollama is running, but {status.chat_model} hasn't been downloaded yet.</p>}
    </details>
  );
}

function Reply({ turn, onPickPerson, onPickBuilding, onTravel }: {
  turn: AskTurn;
  onPickPerson: (id: number) => void;
  onPickBuilding: (id: number) => void;
  onTravel: (t: number) => unknown;
}) {
  const [lit, setLit] = useState<number | null>(null);
  const a = turn.answer;
  if (turn.error) return <div className="ask-a error">The city couldn't answer: {turn.error}</div>;
  if (!a) return <div className="ask-a muted">Looking through the records...</div>;
  const u = a.understood;
  const heard = [u.about.length ? u.about.join(", ").replace(/_/g, " ") : null, u.when, u.where.join(", ") || null, u.who.join(", ") || null].filter(Boolean);
  return (
    <div className="ask-a">
      <p>
        {citations(a.answer).map((p, i) =>
          typeof p === "number" ? (
            <button key={i} className="cite" onMouseEnter={() => setLit(p)} onMouseLeave={() => setLit(null)} onClick={() => setLit(p)}>
              {p}
            </button>
          ) : (
            <span key={i}>{p}</span>
          ),
        )}
      </p>
      {a.guard && <p className="ask-guard">Shield: {ATTACKS[a.guard.kind] ?? a.guard.kind} spotted in the {a.guard.where}. {a.guard.where === "records" ? "That record was left out." : "The free AI never got to act on it."}</p>}
      <p className="ask-how muted">
        {a.mode === "ai" ? `Written by ${a.model}, a free AI on this computer, from the records below.` : "Put together straight from the city's records."}
        {heard.length > 0 && ` Looked for: ${heard.join(" · ")}.`}
      </p>
      {a.sources.length > 0 && (
        <ol className="sources">
          {a.sources.map((s) => (
            <li key={s.id} className={lit === s.n ? "lit" : ""}>
              <span className="n">{s.n}</span>
              <div>
                <time>{s.when}</time> {s.text}
                <div className="links">
                  {s.people.map((p) => (
                    <button key={p.id} className="link" onClick={() => onPickPerson(p.id)}>
                      {p.name}
                    </button>
                  ))}
                  {s.place && (
                    <button className="link" onClick={() => onPickBuilding(s.place!.id)}>
                      {s.place.name}
                    </button>
                  )}
                  <button className="link" title="Travel back to this moment" onClick={() => onTravel(s.t)}>
                    go there
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

export default function AskPanel({ log, setLog, onPickPerson, onPickBuilding, onTravel }: {
  log: AskTurn[];
  setLog: (f: (log: AskTurn[]) => AskTurn[]) => void;
  onPickPerson: (id: number) => void;
  onPickBuilding: (id: number) => void;
  onTravel: (t: number) => unknown;
}) {
  const [text, setText] = useState("");
  const [status, setStatus] = useState<AskStatus | null>(null);
  const busy = log.length > 0 && !log[log.length - 1].answer && !log[log.length - 1].error;
  const logBox = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    const load = () => api.askStatus().then((s) => live && setStatus(s), () => undefined);
    load();
    const id = setInterval(load, 10000);
    return () => {
      live = false;
      clearInterval(id);
    };
  }, []);
  useEffect(() => {
    // keep the newest answer in view without scrolling the whole side panel
    const box = logBox.current;
    if (box) box.scrollTop = box.scrollHeight;
  }, [log]);

  const ask = (question: string) => {
    question = question.trim();
    if (!question || busy) return;
    setText("");
    setLog((l) => [...l.slice(-19), { question }]);
    const settle = (patch: Partial<AskTurn>) => setLog((l) => l.map((t, i) => (i === l.length - 1 ? { ...t, ...patch } : t)));
    api.ask(question).then(
      (answer) => {
        settle({ answer });
        if (answer.guard) api.askStatus().then(setStatus, () => undefined);
      },
      (e) => settle({ error: String(e) }),
    );
  };

  return (
    <div className="card ask">
      <h2>Ask the city</h2>
      <p className="muted">Ask anything about Kamalnagar in plain words. The city looks it up in its own records and shows you where the answer came from.</p>
      <Badge status={status} />
      {status && <Shield status={status} />}
      <div className="ask-log" ref={logBox}>
        {log.map((turn, i) => (
          <div key={i} className="ask-turn">
            <div className="ask-q">{turn.question}</div>
            <Reply turn={turn} onPickPerson={onPickPerson} onPickBuilding={onPickBuilding} onTravel={onTravel} />
          </div>
        ))}
      </div>
      <form
        className="ask-box"
        onSubmit={(e) => {
          e.preventDefault();
          ask(text);
        }}
      >
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="How many people found a job this week?" maxLength={300} />
        <button type="submit" disabled={busy || !text.trim()}>
          Ask
        </button>
      </form>
      <div className="chips">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => ask(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
