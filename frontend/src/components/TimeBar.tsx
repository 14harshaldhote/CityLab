import { useState } from "react";
import type { Frame } from "../api/types";
import { SPEEDS, agoLabel, simLabel } from "../engine/view";

interface Props {
  frame: Frame | null;
  connected: boolean;
  onPlay: (playing: boolean) => void;
  onSpeed: (speed: number) => void;
  onSkip: (minutes: number) => void;
  onTravel: (t: number) => Promise<unknown>;
}

const PHASES = ["Night", "Twilight", "Golden hour", "Day"];

export default function TimeBar({ frame, connected, onPlay, onSpeed, onSkip, onTravel }: Props) {
  const w = frame?.weather;
  const [drag, setDrag] = useState<number | null>(null);
  const [going, setGoing] = useState<number | null>(null);
  const horizon = Math.max(frame?.horizon ?? 0, frame?.t ?? 0);
  const now = frame?.t ?? 0;
  const inPast = horizon - now > 1;
  const go = (t: number) => {
    setGoing(t);
    onTravel(t).finally(() => {
      setGoing(null);
      setDrag(null);
    });
  };
  const shown = drag ?? going ?? now;
  return (
    <div className="timebar-wrap">
      <div className="timebar">
        <button className="primary" onClick={() => onPlay(!frame?.playing)} disabled={!frame}>
          {frame?.playing ? "Pause" : "Play"}
        </button>
        <div className="speeds" role="group" aria-label="Speed">
          {SPEEDS.map((s) => (
            <button key={s.value} className={frame?.speed === s.value ? "on" : ""} onClick={() => onSpeed(s.value)}>
              {s.label}
            </button>
          ))}
        </div>
        <button onClick={() => onSkip(60)} title="Advance one hour now">
          +1 h
        </button>
        <button onClick={() => onSkip(24 * 60)} title="Advance one day now">
          +1 day
        </button>
        <div className="clock">
          <strong>{frame ? frame.label : "connecting..."}</strong>
          {w && (
            <span className="muted">
              {PHASES[w.phase]} · {w.temperature_c.toFixed(1)} °C · {w.rain_mm_h > 0.2 ? `rain ${w.rain_mm_h.toFixed(1)} mm/h` : `cloud ${w.cloud_pct}%`}
            </span>
          )}
        </div>
        <span className={`dot ${connected ? "live" : ""}`} title={connected ? "Live" : "Reconnecting"} />
      </div>
      {horizon >= 60 && (
        <div className={`history-bar ${inPast ? "past" : ""}`}>
          <span className="history-icon" title="Time machine">
            ⟲
          </span>
          <input
            type="range"
            min={0}
            max={horizon}
            step={10}
            value={shown}
            disabled={going !== null}
            aria-label="Go back in time"
            onChange={(e) => setDrag(Number(e.target.value))}
            onPointerUp={() => drag !== null && go(drag)}
            onKeyUp={() => drag !== null && go(drag)}
          />
          <span className="history-label">
            {going !== null
              ? `Travelling to ${simLabel(going)}...`
              : drag !== null
                ? `${simLabel(drag)} · ${horizon - drag > 1 ? agoLabel(horizon - drag) : "now"}`
                : inPast
                  ? `Back in time, ${agoLabel(horizon - now)}`
                  : "Drag back to visit the past"}
          </span>
          {inPast && going === null && (
            <button className="small" onClick={() => go(horizon)}>
              Return to the latest
            </button>
          )}
        </div>
      )}
    </div>
  );
}
