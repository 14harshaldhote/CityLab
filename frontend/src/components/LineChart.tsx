import * as d3 from "d3";
import { useEffect, useRef } from "react";

interface Series {
  label: string;
  color: string;
  values: number[];
}

/** A small multi-series line chart over simulated days. */
export default function LineChart({ days, series, height = 150 }: { days: number[]; series: Series[]; height?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const svg = d3.select(ref.current!);
    const width = ref.current!.clientWidth || 320;
    const m = { t: 10, r: 10, b: 22, l: 40 };
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);
    if (days.length < 2) {
      svg.append("text").attr("x", width / 2).attr("y", height / 2).attr("text-anchor", "middle").attr("class", "muted-svg").text("Charts fill in after the first simulated days");
      return;
    }
    const x = d3.scaleLinear().domain(d3.extent(days) as [number, number]).range([m.l, width - m.r]);
    const all = series.flatMap((s) => s.values);
    const y = d3.scaleLinear().domain([Math.min(0, d3.min(all) ?? 0), (d3.max(all) ?? 1) * 1.08]).nice().range([height - m.b, m.t]);
    svg.append("g").attr("transform", `translate(0,${height - m.b})`).call(d3.axisBottom(x).ticks(5).tickFormat((d) => `day ${d}`));
    svg.append("g").attr("transform", `translate(${m.l},0)`).call(d3.axisLeft(y).ticks(4).tickFormat(d3.format("~s")));
    for (const s of series) {
      const line = d3.line<number>().x((_, i) => x(days[i])).y((v) => y(v));
      svg.append("path").attr("d", line(s.values)).attr("fill", "none").attr("stroke", s.color).attr("stroke-width", 2);
    }
  }, [days, series, height]);
  return (
    <div>
      <svg ref={ref} className="chart" height={height} />
      <div className="legend">
        {series.map((s) => (
          <span key={s.label}>
            <i style={{ background: s.color }} /> {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
