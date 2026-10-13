import * as d3 from "d3";
import { useEffect, useRef } from "react";

export interface Network {
  center: number;
  nodes: { id: number; name: string; age: number }[];
  links: { source: number; target: number; strength: number; kind: string }[];
}

type N = d3.SimulationNodeDatum & { id: number; name: string; age: number };
type L = d3.SimulationLinkDatum<N> & { strength: number; kind: string };

const KIND_COLOR: Record<string, string> = { partner: "#d4508a", parent: "#2f7fb0", child: "#2f7fb0", sibling: "#8a5cc4", friend: "#9aa8a0" };

/** The person's corner of the social graph, laid out with a D3 force simulation. */
export default function EgoGraph({ net, onPick }: { net: Network; onPick: (id: number) => void }) {
  const ref = useRef<SVGSVGElement>(null);
  useEffect(() => {
    const width = ref.current!.clientWidth || 340;
    const height = 260;
    const svg = d3.select(ref.current!).attr("viewBox", `0 0 ${width} ${height}`);
    svg.selectAll("*").remove();
    const nodes: N[] = net.nodes.map((n) => ({ ...n }));
    const links: L[] = net.links.map((l) => ({ ...l }));
    const sim = d3
      .forceSimulation(nodes)
      .force("link", d3.forceLink<N, L>(links).id((d) => d.id).distance((l) => 110 - 45 * l.strength))
      .force("charge", d3.forceManyBody().strength(-90))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(9))
      .stop();
    for (let i = 0; i < 200; i++) sim.tick();
    const clampX = (x: number) => Math.max(8, Math.min(width - 8, x));
    const clampY = (y: number) => Math.max(8, Math.min(height - 8, y));
    svg
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("x1", (l) => clampX((l.source as N).x!))
      .attr("y1", (l) => clampY((l.source as N).y!))
      .attr("x2", (l) => clampX((l.target as N).x!))
      .attr("y2", (l) => clampY((l.target as N).y!))
      .attr("stroke", (l) => KIND_COLOR[l.kind] ?? "#9aa8a0")
      .attr("stroke-opacity", (l) => 0.25 + 0.7 * l.strength)
      .attr("stroke-width", (l) => 0.5 + 2.5 * l.strength);
    const g = svg
      .append("g")
      .selectAll("g")
      .data(nodes)
      .join("g")
      .attr("transform", (d) => `translate(${clampX(d.x!)},${clampY(d.y!)})`)
      .style("cursor", "pointer")
      .on("click", (_, d) => onPick(d.id));
    g.append("circle")
      .attr("r", (d) => (d.id === net.center ? 8 : 5))
      .attr("fill", (d) => (d.id === net.center ? "#d9480f" : d.age < 18 ? "#8a5cc4" : "#2f7d55"));
    g.append("title").text((d) => `${d.name}, ${d.age}`);
  }, [net, onPick]);
  return <svg ref={ref} className="chart" height={260} />;
}
