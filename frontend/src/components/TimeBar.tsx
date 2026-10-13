import type { Frame } from "../api/types";
import { SPEEDS } from "../engine/view";

interface Props {
  frame: Frame | null;
  connected: boolean;
  onPlay: (playing: boolean) => void;
  onSpeed: (speed: number) => void;
  onSkip: (minutes: number) => void;
}

const PHASES = ["Night", "Twilight", "Golden hour", "Day"];

export default function TimeBar({ frame, connected, onPlay, onSpeed, onSkip }: Props) {
  const w = frame?.weather;
  return (
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
      <button onClick={() => onSkip(60)} title="Advance one hour now">+1 h</button>
      <button onClick={() => onSkip(24 * 60)} title="Advance one day now">+1 day</button>
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
  );
}
