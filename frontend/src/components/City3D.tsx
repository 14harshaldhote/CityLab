import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CityMap as City, Frame } from "../api/types";
import { daylight, hash01 } from "../engine/art";
import { buildingModel, cameraModel, outskirtsModel, plotModel, siteHeight, streetModel, transitModel, type Part, type Shape, type Win } from "../engine/models";
import { skyAt } from "../engine/sky";
import { lerpFrames } from "../engine/view";

interface Props {
  city: City;
  frames: React.MutableRefObject<{ prev: Frame | null; next: Frame | null; at: number }>;
  selectedPerson: number | null;
  selectedBuilding: number | null;
  onPickPerson: (id: number) => void;
  onPickBuilding: (id: number) => void;
}

const TICK_MS = 200;
const SLEEPING = 0;
const SKIN = [0x8d5524, 0xa86b3c, 0xc68642, 0xb07a4f, 0x7a4a2a, 0xd29a6a];
const SHIRTS = [0xe3672f, 0x2c7fb8, 0xd9467f, 0x2f9a52, 0xe7b53b, 0x8a4fc6, 0x149c8f, 0xf2f2f2, 0xd2463c, 0x5b6c9e];
const CAR_COLORS = [0xf2f2f2, 0xd2463c, 0x3f63a5, 0x2d2d2d, 0xe7b53b, 0x9aa3ad, 0x3f8f6a];
// how each traveller is moving (see the server's routing.py)
const DRIVING = 2;
const ON_BUS = 3;
const IN_AUTO = 4;
const WAITING = 5;
const ON_SCOOTER = 6;
const SCOOTER_COLORS = [0x2d2d2d, 0xd2463c, 0x3f63a5, 0xf2f2f2, 0x149c8f, 0x8a4fc6];
const JAM = [
  [0.9, 0xf2b32a],
  [1.2, 0xe0602f],
  [1.6, 0xb3261e],
] as const;

/** One unit-sized shape per part kind, with its origin at the middle of its base. */
function shapes(): Record<Shape, THREE.BufferGeometry> {
  const up = (g: THREE.BufferGeometry, dy: number) => g.translate(0, dy, 0);
  const tri = new THREE.Shape([new THREE.Vector2(-0.5, 0), new THREE.Vector2(0.5, 0), new THREE.Vector2(0, 1)]);
  const roof = new THREE.ExtrudeGeometry(tri, { depth: 1, bevelEnabled: false }).translate(0, 0, -0.5);
  return {
    box: up(new THREE.BoxGeometry(1, 1, 1), 0.5),
    roof,
    pyramid: up(new THREE.ConeGeometry(Math.SQRT1_2, 1, 4).rotateY(Math.PI / 4), 0.5),
    cone: up(new THREE.ConeGeometry(0.5, 1, 14), 0.5),
    cyl: up(new THREE.CylinderGeometry(0.5, 0.5, 1, 16), 0.5),
    dome: new THREE.SphereGeometry(0.5, 20, 10, 0, Math.PI * 2, 0, Math.PI / 2).scale(1, 2, 1),
    ball: up(new THREE.IcosahedronGeometry(0.5, 1), 0.5),
  };
}

/** Cel shading in four soft steps: the toy-town look. */
function toonRamp(): THREE.DataTexture {
  const steps = new Uint8Array([90, 160, 215, 255]);
  const tex = new THREE.DataTexture(steps, steps.length, 1, THREE.RedFormat);
  tex.minFilter = tex.magFilter = THREE.NearestFilter;
  tex.needsUpdate = true;
  return tex;
}

const CRIME_NAMES = ["A pickpocketing", "Shoplifting", "A burglary"];

const m4 = new THREE.Matrix4();
const q = new THREE.Quaternion();
const v = new THREE.Vector3();
const sv = new THREE.Vector3();
const yAxis = new THREE.Vector3(0, 1, 0);
const col = new THREE.Color();

function place(mesh: THREE.InstancedMesh, i: number, x: number, y: number, z: number, sx: number, sy: number, sz: number, ry = 0) {
  q.setFromAxisAngle(yAxis, ry);
  m4.compose(v.set(x, y, z), q, sv.set(sx, sy, sz));
  mesh.setMatrixAt(i, m4);
}

/**
 * The city in 3D, drawn with three.js: toy-like buildings for every kind of place,
 * streets with zebra crossings and lamps, farmland around the edge, the real sun
 * moving across the sky with soft shadows, lit windows at night, and the people
 * themselves walking the pavements or driving, coloured by what they are doing.
 */
export default function City3D({ city, frames, selectedPerson, selectedBuilding, onPickPerson, onPickBuilding }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; text: string } | null>(null);
  const sel = useRef({ person: selectedPerson, building: selectedBuilding });
  sel.current = { person: selectedPerson, building: selectedBuilding };
  const picks = useRef({ onPickPerson, onPickBuilding });
  picks.current = { onPickPerson, onPickBuilding };
  const api = useRef<{ reset: () => void; follow: (on: boolean) => void } | null>(null);
  const [following, setFollowing] = useState(false);
  const [traffic, setTraffic] = useState(true);
  const showTraffic = useRef(traffic);
  showTraffic.current = traffic;
  const saved = useRef<{ pos: THREE.Vector3; target: THREE.Vector3 } | null>(null); // keep the view when the city grows

  useEffect(() => {
    const el = host.current!;
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(el.clientWidth, el.clientHeight);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const size = city.size;
    const centre = new THREE.Vector3(size / 2, 0, size / 2);
    scene.fog = new THREE.Fog(0xcfe3ef, size * 1.2, size * 3.2);

    const camera = new THREE.PerspectiveCamera(38, el.clientWidth / el.clientHeight, 5, size * 8);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.maxPolarAngle = 1.38;
    controls.minDistance = 40;
    controls.maxDistance = size * 2.6;
    controls.screenSpacePanning = false;
    controls.zoomToCursor = true;
    const reset = () => {
      controls.target.copy(centre);
      camera.position.set(size * 0.5, size * 0.45, size * 1.2);
      controls.update();
    };
    if (saved.current) {
      camera.position.copy(saved.current.pos);
      controls.target.copy(saved.current.target);
      controls.update();
    } else reset();

    // light: a sky dome, the sun (or moon) with shadows, and a soft fill
    const hemi = new THREE.HemisphereLight(0xdbeeff, 0xb59a6a, 1.2);
    scene.add(hemi);
    const sun = new THREE.DirectionalLight(0xfff3d8, 2.4);
    sun.castShadow = true;
    sun.shadow.mapSize.set(4096, 4096);
    const sc = sun.shadow.camera;
    sc.left = sc.bottom = -size * 0.62;
    sc.right = sc.top = size * 0.62;
    sc.near = 100;
    sc.far = size * 4;
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.6;
    sun.target.position.copy(centre);
    scene.add(sun, sun.target);

    const ground = new THREE.Mesh(new THREE.PlaneGeometry(size * 12, size * 12), new THREE.MeshLambertMaterial({ color: 0xd2c99e }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(size / 2, -0.05, size / 2);
    ground.receiveShadow = true;
    scene.add(ground);

    // ---- the static city: every part of every model, one instanced mesh per shape ----------
    const geo = shapes();
    const ramp = toonRamp();
    const solid = new THREE.MeshToonMaterial({ gradientMap: ramp });
    const flatMat = new THREE.MeshLambertMaterial();
    const glowMat = new THREE.MeshBasicMaterial({ toneMapped: false });
    const parts: Part[] = [];
    const windows: Win[] = [];
    for (const b of city.buildings) {
      const m = buildingModel(b);
      parts.push(...m.parts);
      windows.push(...m.windows);
    }
    const streets = streetModel(city);
    parts.push(...streets.parts, ...outskirtsModel(city), ...plotModel(city), ...transitModel(city), ...cameraModel(city));

    const pickable: THREE.InstancedMesh[] = [];
    const meshBids = new Map<THREE.InstancedMesh, Int32Array>();
    const groups = new Map<string, Part[]>();
    for (const p of parts) {
      const key = `${p.s}|${p.glow ? "glow" : p.flat ? "flat" : "solid"}`;
      (groups.get(key) ?? groups.set(key, []).get(key)!).push(p);
    }
    for (const [key, list] of groups) {
      const [s, kind] = key.split("|") as [Shape, string];
      const mat = kind === "glow" ? glowMat : kind === "flat" ? flatMat : solid;
      const mesh = new THREE.InstancedMesh(geo[s], mat, list.length);
      const bids = new Int32Array(list.length);
      list.forEach((p, i) => {
        place(mesh, i, p.x, p.y, p.z, p.w, p.h, p.d, p.ry ?? 0);
        mesh.setColorAt(i, col.setHex(p.c));
        bids[i] = p.bid;
      });
      mesh.castShadow = kind === "solid";
      mesh.receiveShadow = kind !== "glow";
      mesh.instanceMatrix.needsUpdate = true;
      mesh.computeBoundingSphere();
      scene.add(mesh);
      pickable.push(mesh);
      meshBids.set(mesh, bids);
    }

    // windows: dark glass by day, warm light at night where people are awake inside
    const winMesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ toneMapped: false }), Math.max(1, windows.length));
    windows.forEach((w, i) => place(winMesh, i, w.x, w.y + w.h / 2, w.z, w.w, w.h, 1, w.ry));
    winMesh.instanceMatrix.needsUpdate = true;
    winMesh.computeBoundingSphere();
    scene.add(winMesh);

    // pools of lamplight on the street at night
    const pool = new THREE.InstancedMesh(
      new THREE.CircleGeometry(1, 20).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0xffc766, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }),
      streets.lamps.length,
    );
    streets.lamps.forEach((l, i) => place(pool, i, l.x - 4, 0.5, l.z - 4, 16, 1, 16));
    pool.instanceMatrix.needsUpdate = true;
    pool.computeBoundingSphere();
    scene.add(pool);

    // ---- people and cars ------------------------------------------------------------------
    const MAX = 6000;
    const bodyGeo = new THREE.CapsuleGeometry(0.34, 0.9, 4, 8).translate(0, 0.8, 0);
    const headGeo = new THREE.SphereGeometry(0.27, 10, 8).translate(0, 1.86, 0);
    const bodies = new THREE.InstancedMesh(bodyGeo, solid, MAX);
    const heads = new THREE.InstancedMesh(headGeo, solid, MAX);
    const carBody = new THREE.InstancedMesh(new THREE.BoxGeometry(4.2, 1.1, 1.9).translate(0, 0.85, 0), solid, MAX);
    const carTop = new THREE.InstancedMesh(new THREE.BoxGeometry(2.2, 0.85, 1.7).translate(-0.3, 1.82, 0), solid, MAX);
    for (const m of [bodies, heads, carBody, carTop]) {
      m.castShadow = true;
      m.frustumCulled = false;
      m.count = 0;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(m);
    }
    for (let i = 0; i < MAX; i++) carTop.setColorAt(i, col.setHex(0x5b7590));

    // auto-rickshaws: green below, a yellow canopy on top
    const autoBody = new THREE.InstancedMesh(new THREE.BoxGeometry(2.6, 1.0, 1.5).translate(0.1, 0.75, 0), solid, 2000);
    const autoTop = new THREE.InstancedMesh(new THREE.BoxGeometry(2.1, 1.0, 1.55).translate(-0.15, 1.75, 0), solid, 2000);
    // city buses: a long body in the route's colour, a band of windows and a white roof
    const BUSES = 300;
    const busBody = new THREE.InstancedMesh(new THREE.BoxGeometry(12, 2.8, 3).translate(0, 1.9, 0), solid, BUSES);
    const busWin = new THREE.InstancedMesh(new THREE.BoxGeometry(10.6, 1.0, 3.08).translate(0.4, 2.55, 0), solid, BUSES);
    const busRoof = new THREE.InstancedMesh(new THREE.BoxGeometry(11.6, 0.35, 2.8).translate(0, 3.45, 0), solid, BUSES);
    // scooters and motorbikes, the town's favourite way to get about: a low body under its rider
    const scooter = new THREE.InstancedMesh(new THREE.BoxGeometry(2.0, 0.8, 0.7).translate(0, 0.55, 0), solid, 2000);
    for (const m of [autoBody, autoTop, busBody, busWin, busRoof, scooter]) {
      m.castShadow = true;
      m.frustumCulled = false;
      m.count = 0;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(m);
    }
    for (let i = 0; i < 2000; i++) {
      autoBody.setColorAt(i, col.setHex(0x2f8f4a));
      autoTop.setColorAt(i, col.setHex(0xf2c12e));
    }
    for (let i = 0; i < BUSES; i++) {
      busWin.setColorAt(i, col.setHex(0x2b3a4a));
      busRoof.setColorAt(i, col.setHex(0xf4f1e8));
    }
    // police cars: white with a blue band and a light bar that flashes red and blue
    const COPS = 40;
    const copBody = new THREE.InstancedMesh(new THREE.BoxGeometry(4.4, 1.15, 2).translate(0, 0.85, 0), solid, COPS);
    const copTop = new THREE.InstancedMesh(new THREE.BoxGeometry(2.3, 0.85, 1.8).translate(-0.3, 1.85, 0), solid, COPS);
    const copBand = new THREE.InstancedMesh(new THREE.BoxGeometry(4.45, 0.35, 2.05).translate(0, 0.95, 0), solid, COPS);
    const copLights = new THREE.InstancedMesh(new THREE.BoxGeometry(0.5, 0.35, 0.8).translate(0, 2.45, 0), glowMat, COPS * 2);
    for (const m of [copBody, copTop, copBand, copLights]) {
      m.castShadow = m !== copLights;
      m.frustumCulled = false;
      m.count = 0;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(m);
    }
    for (let i = 0; i < COPS; i++) {
      copBody.setColorAt(i, col.setHex(0xf7f4ec));
      copTop.setColorAt(i, col.setHex(0xf7f4ec));
      copBand.setColorAt(i, col.setHex(0x2f55a8));
    }
    for (let i = 0; i < COPS * 2; i++) copLights.setColorAt(i, col.setHex(0xd2463c));
    // a fresh theft: a red pin bobbing over the spot for three hours, blue once someone is arrested
    const PINS = 60;
    const pin = new THREE.InstancedMesh(new THREE.ConeGeometry(1, 2.2, 12).rotateX(Math.PI).translate(0, 1.1, 0), glowMat, PINS);
    const pinHead = new THREE.InstancedMesh(new THREE.SphereGeometry(1, 14, 10).translate(0, 2.6, 0), glowMat, PINS);
    const pinRing = new THREE.InstancedMesh(
      new THREE.RingGeometry(0.75, 1, 40).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.75, depthWrite: false, toneMapped: false }),
      PINS,
    );
    for (const m of [pin, pinHead, pinRing]) {
      m.frustumCulled = false;
      m.count = 0;
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      scene.add(m);
    }
    const lineColor = new Map((city.transit?.lines ?? []).map((l) => [Number(l.number), parseInt(l.color.slice(1), 16)]));
    const lineName = new Map((city.transit?.lines ?? []).map((l) => [Number(l.number), l.name]));
    let busInfo: { route: number; riders: number }[] = [];
    let crimeInfo: string[] = [];

    // traffic: streets glow amber when busy and red when jammed
    const nodeAt = new Map(city.nodes.map((nd) => [nd.id, nd]));
    const wideSet = new Set((city.wide ?? []).map(([a, b]) => (a < b ? `${a}-${b}` : `${b}-${a}`)));
    const jam = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0),
      new THREE.MeshBasicMaterial({ transparent: true, opacity: 0.45, depthWrite: false }),
      Math.max(1, city.edges.length),
    );
    jam.count = 0;
    jam.frustumCulled = false;
    jam.renderOrder = 2;
    scene.add(jam);
    const paintTraffic = (frame: Frame) => {
      let k = 0;
      if (showTraffic.current) {
        for (const [a, b, r] of frame.traffic ?? []) {
          if (r < JAM[0][0]) continue;
          const na = nodeAt.get(a);
          const nb = nodeAt.get(b);
          if (!na || !nb) continue;
          const len = Math.hypot(nb.x - na.x, nb.y - na.y);
          const wide = wideSet.has(`${a}-${b}`);
          place(jam, k, (na.x + nb.x) / 2, 0.4, (na.y + nb.y) / 2, len - 22, 0.12, wide ? 27 : 17, Math.atan2(-(nb.y - na.y), nb.x - na.x));
          jam.setColorAt(k, col.setHex(JAM.filter(([at]) => r >= at).pop()![1]));
          k++;
        }
      }
      jam.count = k;
      jam.instanceMatrix.needsUpdate = true;
      if (jam.instanceColor) jam.instanceColor.needsUpdate = true;
    };

    // building sites: the structure rises day by day inside its bamboo scaffolding
    const sites = city.buildings.filter((b) => b.status === "construction");
    const siteCore = new THREE.InstancedMesh(geo.box, solid, Math.max(1, sites.length));
    const siteScaffold = new THREE.InstancedMesh(
      new THREE.BoxGeometry(1, 1, 1).translate(0, 0.5, 0),
      new THREE.MeshBasicMaterial({ color: 0xa7814a, wireframe: true }),
      Math.max(1, sites.length),
    );
    siteCore.count = siteScaffold.count = sites.length;
    siteCore.castShadow = true;
    sites.forEach((b, i) => siteCore.setColorAt(i, col.setHex(b.kind === "home" ? 0xd7cbb8 : 0xc9c4ba)));
    scene.add(siteCore, siteScaffold);
    const raise = (frame: Frame) => {
      const progress = new Map(frame.sites ?? []);
      sites.forEach((b, i) => {
        const p = progress.get(b.id) ?? b.progress ?? 0;
        const h = Math.max(1.5, siteHeight(b) * p);
        const cx = b.x + b.w / 2;
        const cz = b.y + b.h / 2;
        place(siteCore, i, cx, 1.4, cz, b.w * 0.6, h, b.h * 0.55);
        place(siteScaffold, i, cx, 1.4, cz, b.w * 0.6 + 3, h + 3, b.h * 0.55 + 3);
      });
      siteCore.instanceMatrix.needsUpdate = siteScaffold.instanceMatrix.needsUpdate = true;
      siteCore.computeBoundingSphere();
    };
    meshBids.set(siteCore, Int32Array.from(sites.map((b) => b.id)));
    pickable.push(siteCore);

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(0.82, 1, 48).rotateX(-Math.PI / 2),
      new THREE.MeshBasicMaterial({ color: 0xd9480f, transparent: true, opacity: 0.9, depthTest: false }),
    );
    ring.renderOrder = 10;
    ring.visible = false;
    scene.add(ring);

    // ---- per frame ---------------------------------------------------------------------------
    const pos = { x: new Float32Array(0), y: new Float32Array(0) };
    const heading = new Map<number, number>();
    const prevPos = new Map<number, [number, number]>();
    let shown: number[] = []; // body instance -> person id
    let lastT = -1;
    let painted = "";
    let lastNight = -1;
    let follow = false;
    const awake = new Map<number, number>();
    const parkIds = new Set(city.buildings.filter((b) => b.kind === "park").map((b) => b.id));

    const lightUp = (frame: Frame, night: number) => {
      awake.clear();
      for (let i = 0; i < frame.ids.length; i++) {
        const pl = frame.place?.[i] ?? -1;
        if (pl >= 0 && frame.activity[i] !== SLEEPING) awake.set(pl, (awake.get(pl) ?? 0) + 1);
      }
      windows.forEach((w, i) => {
        const share = Math.min(1, (awake.get(w.bid) ?? 0) / 4);
        const on = night > 0.3 && hash01(w.bid * 7919 + w.key, 9) < share * 0.85;
        if (on) col.setHex(0xffd27a);
        else col.setHex(night > 0.3 ? 0x2a3142 : 0x46566b).lerp(col.clone().setHex(0x9ab3c9), hash01(w.bid + w.key, 3) * 0.25 * (1 - night));
        winMesh.setColorAt(i, col);
      });
      if (winMesh.instanceColor) winMesh.instanceColor.needsUpdate = true;
    };

    const sky = (frame: Frame) => {
      const w = frame.weather;
      const night = 1 - daylight(w.sun_elevation_deg, w.cloud_pct);
      const s = skyAt(w.sun_elevation_deg, w.cloud_pct);
      const horizon = new THREE.Color(s.horizon);
      scene.background = horizon;
      (scene.fog as THREE.Fog).color.copy(horizon);
      const up = w.sun_elevation_deg > 0;
      // the moon stands in for the sun at night, low and blue
      const el = THREE.MathUtils.degToRad(up ? Math.max(4, w.sun_elevation_deg) : 38);
      const az = THREE.MathUtils.degToRad((w.sun_azimuth_deg ?? 180) + (up ? 0 : 180));
      sun.position.set(centre.x + Math.sin(az) * Math.cos(el) * size * 2, Math.sin(el) * size * 2, centre.z - Math.cos(az) * Math.cos(el) * size * 2);
      sun.color.set(up ? s.sunColor : "#9fb4ff");
      sun.intensity = up ? 0.6 + 2.2 * (1 - night) * (1 - 0.5 * (w.cloud_pct / 100)) : 0.35;
      hemi.intensity = 0.45 + 1.0 * (1 - night);
      hemi.color.set(up ? "#dbeeff" : "#6d7fb8");
      glowMat.color.setScalar(night > 0.3 ? 1 : 0.75);
      (pool.material as THREE.MeshBasicMaterial).opacity = Math.max(0, night - 0.35) * 0.45;
      return night;
    };

    const update = () => {
      const { prev, next, at } = frames.current;
      if (!next) return;
      const n = next.ids.length;
      if (pos.x.length !== n) {
        pos.x = new Float32Array(n);
        pos.y = new Float32Array(n);
      }
      const f = Math.min(1, (performance.now() - at) / TICK_MS);
      lerpFrames(prev ?? next, next, prev ? f : 1, pos);

      const paintKey = `${next.t}:${showTraffic.current}`;
      if (paintKey !== painted) {
        painted = paintKey;
        paintTraffic(next);
      }
      if (next.t !== lastT) {
        lastT = next.t;
        const night = sky(next);
        raise(next);
        if (Math.abs(night - lastNight) > 0.02 || next.t % 10 === 0 || lastNight < 0) {
          lastNight = night;
          lightUp(next, night);
        }
        // headings from the last two server frames
        if (prev) {
          const idx = new Map<number, number>();
          prev.ids.forEach((id, i) => idx.set(id, i));
          for (let i = 0; i < n; i++) {
            const j = idx.get(next.ids[i]);
            if (j === undefined) continue;
            const dx = next.x[i] - prev.x[j];
            const dz = next.y[i] - prev.y[j];
            if (dx * dx + dz * dz > 0.5) heading.set(next.ids[i], Math.atan2(dz, dx));
          }
        }
      }

      const dist = camera.position.distanceTo(controls.target);
      const S = THREE.MathUtils.clamp(dist / 230, 2.2, 9);
      const time = performance.now() / 1000;
      let nb = 0;
      let nc = 0;
      let na = 0;
      let ns = 0;
      shown = [];
      for (let i = 0; i < n; i++) {
        const pl = next.place?.[i] ?? -1;
        const outside = pl < 0 || parkIds.has(pl);
        if (!outside) continue;
        const id = next.ids[i];
        const h = heading.get(id) ?? hash01(id, 1) * Math.PI * 2;
        const hx = Math.cos(h);
        const hz = Math.sin(h);
        // keep to the left, as traffic does in India: cars in the left lane, walkers on the pavement
        const move = pl < 0 ? (next.move?.[i] ?? 1) : 0;
        if (move === ON_BUS) {
          prevPos.set(id, [pos.x[i], pos.y[i]]);
          continue; // inside the bus
        }
        const driving = move === DRIVING;
        const riding = move === ON_SCOOTER;
        const side = pl < 0 ? (driving || riding || move === IN_AUTO ? 5 : 13) : 0;
        const x = pos.x[i] + hz * side;
        const z = pos.y[i] - hx * side;
        prevPos.set(id, [x, z]);
        if (move === IN_AUTO) {
          const cs = Math.max(1.2, S * 0.55);
          place(autoBody, na, x, 0.3, z, cs, cs, cs, -h);
          place(autoTop, na, x, 0.3, z, cs, cs, cs, -h);
          na++;
        } else if (driving) {
          const cs = Math.max(1.2, S * 0.55);
          place(carBody, nc, x, 0.3, z, cs, cs, cs, -h);
          place(carTop, nc, x, 0.3, z, cs, cs, cs, -h);
          carBody.setColorAt(nc, col.setHex(CAR_COLORS[id % CAR_COLORS.length]));
          nc++;
        } else {
          const child = next.age[i] < 13 ? 0.7 : 1;
          const s = S * child;
          let bob = pl < 0 && move !== WAITING ? Math.abs(Math.sin(time * 9 + id)) * 0.35 * s : 0;
          if (riding) {
            const cs = Math.max(1.2, S * 0.55);
            place(scooter, ns, x, 0.3, z, cs, cs, cs, -h);
            scooter.setColorAt(ns, col.setHex(SCOOTER_COLORS[id % SCOOTER_COLORS.length]));
            ns++;
            bob = 0.9 * cs; // sitting on it, not walking
          }
          place(bodies, nb, x, bob, z, s, s, s, -h);
          place(heads, nb, x, bob, z, s, s, s, -h);
          // out and about, everyone wears their own colours (the flat map colours them by activity)
          bodies.setColorAt(nb, col.setHex(SHIRTS[Math.floor(hash01(id, 2) * SHIRTS.length)]));
          heads.setColorAt(nb, col.setHex(SKIN[id % SKIN.length]));
          shown.push(id);
          nb++;
        }
      }
      bodies.count = heads.count = nb;
      carBody.count = carTop.count = nc;
      autoBody.count = autoTop.count = na;
      scooter.count = ns;

      // buses glide between server frames like everyone else
      const was = new Map((prev?.buses ?? []).map((b) => [b[0], b]));
      const bs = Math.max(1.5, Math.min(S * 0.75, 3.6));
      busInfo = [];
      const list = next.buses ?? [];
      for (let k = 0; k < list.length && k < BUSES; k++) {
        const [id, bx, by, hd, route, riders] = list[k];
        const o = was.get(id);
        const x0 = o && prev ? o[1] + (bx - o[1]) * f : bx;
        const y0 = o && prev ? o[2] + (by - o[2]) * f : by;
        const hx = Math.cos(hd);
        const hz = Math.sin(hd);
        const x = x0 + hz * 5;
        const z = y0 - hx * 5;
        place(busBody, k, x, 0.3, z, bs, bs, bs, -hd);
        place(busWin, k, x, 0.3, z, bs, bs, bs, -hd);
        place(busRoof, k, x, 0.3, z, bs, bs, bs, -hd);
        busBody.setColorAt(k, col.setHex(lineColor.get(route) ?? 0xd2463c));
        busInfo.push({ route, riders });
      }
      busBody.count = busWin.count = busRoof.count = Math.min(list.length, BUSES);
      busBody.computeBoundingSphere();

      const wasCop = new Map((prev?.police ?? []).map((c) => [c[0], c]));
      const cops = next.police ?? [];
      const ps = Math.max(1.3, S * 0.6);
      const flash = Math.floor(time * 3) % 2;
      for (let k = 0; k < cops.length && k < COPS; k++) {
        const [id, px, py, hd] = cops[k];
        const o = wasCop.get(id);
        const x0 = o && prev ? o[1] + (px - o[1]) * f : px;
        const y0 = o && prev ? o[2] + (py - o[2]) * f : py;
        const x = x0 + Math.sin(hd) * 5;
        const z = y0 - Math.cos(hd) * 5;
        place(copBody, k, x, 0.3, z, ps, ps, ps, -hd);
        place(copTop, k, x, 0.3, z, ps, ps, ps, -hd);
        place(copBand, k, x, 0.3, z, ps, ps, ps, -hd);
        for (const side of [0, 1]) {
          const off = (side ? 0.45 : -0.45) * ps;
          place(copLights, 2 * k + side, x - Math.sin(hd) * off, 0.3, z + Math.cos(hd) * off, ps, ps, ps, -hd);
          copLights.setColorAt(2 * k + side, col.setHex(side === flash ? 0xff3b30 : 0x2f7bff));
        }
      }
      copBody.count = copTop.count = copBand.count = Math.min(cops.length, COPS);
      copLights.count = 2 * copBody.count;

      const crimes = next.crimes ?? [];
      let np = 0;
      crimeInfo = [];
      for (const [cx, cy, ago, kind, solved] of crimes) {
        if (np >= PINS) break;
        const fresh = 1 - Math.min(1, ago / 180);
        const ps2 = S * (1.8 + 1.4 * fresh);
        const bob = 16 + Math.sin(time * 3 + cx) * 2;
        const c = solved ? 0x2c7fb8 : 0xe0302a;
        place(pin, np, cx, bob, cy, ps2, ps2, ps2, time);
        place(pinHead, np, cx, bob, cy, ps2 * 0.9, ps2 * 0.9, ps2 * 0.9);
        const pulse = (8 + ((time * 0.8 + np * 0.3) % 1) * 22) * (S / 2.5);
        place(pinRing, np, cx, 0.7, cy, pulse, 1, pulse);
        for (const m of [pin, pinHead, pinRing]) m.setColorAt(np, col.setHex(c));
        crimeInfo.push(`${CRIME_NAMES[kind] ?? "A theft"} ${ago < 60 ? `${ago} min` : `${Math.floor(ago / 60)} h`} ago${solved ? ", suspect arrested" : ""}`);
        np++;
      }
      pin.count = pinHead.count = pinRing.count = np;

      for (const m of [bodies, heads, carBody, carTop, autoBody, autoTop, scooter, busBody, busWin, busRoof, copBody, copTop, copBand, copLights, pin, pinHead, pinRing]) {
        m.instanceMatrix.needsUpdate = true;
        if (m.instanceColor) m.instanceColor.needsUpdate = true;
      }

      // selection ring, and the camera following the chosen person
      const { person, building } = sel.current;
      ring.visible = false;
      if (person !== null) {
        const i = next.ids.indexOf(person);
        if (i >= 0) {
          const p = prevPos.get(person) ?? [pos.x[i], pos.y[i]];
          const pl = next.place?.[i] ?? -1;
          const b = pl >= 0 && !parkIds.has(pl) ? city.buildings[pl] : null;
          const r = b ? Math.max(b.w, b.h) * 0.6 : S * 2.2;
          ring.position.set(b ? b.x + b.w / 2 : p[0], 0.8, b ? b.y + b.h / 2 : p[1]);
          ring.scale.setScalar(r * (1 + 0.08 * Math.sin(time * 4)));
          ring.visible = true;
          if (follow) {
            controls.target.lerp(v.set(ring.position.x, 0, ring.position.z), 0.08);
          }
        }
      } else if (building !== null && city.buildings[building]) {
        const b = city.buildings[building];
        ring.position.set(b.x + b.w / 2, 0.8, b.y + b.h / 2);
        ring.scale.setScalar(Math.max(b.w, b.h) * 0.62 * (1 + 0.05 * Math.sin(time * 4)));
        ring.visible = true;
      }
    };

    // ---- picking ------------------------------------------------------------------------------
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const cast = (cx: number, cy: number) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((cx - r.left) / r.width) * 2 - 1, -((cy - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const person = ray.intersectObject(bodies, false)[0];
      const bus = ray.intersectObject(busBody, false)[0];
      if (bus && bus.instanceId !== undefined && (!person || bus.distance < person.distance)) return { bus: busInfo[bus.instanceId] };
      const cop = ray.intersectObject(copBody, false)[0];
      if (cop && (!person || cop.distance < person.distance)) return { police: true };
      const alert = ray.intersectObject(pinHead, false)[0] ?? ray.intersectObject(pin, false)[0];
      if (alert && alert.instanceId !== undefined) return { crime: crimeInfo[alert.instanceId] };
      const thing = ray.intersectObjects(pickable, false).find((h) => h.instanceId !== undefined && meshBids.get(h.object as THREE.InstancedMesh)![h.instanceId!] >= 0);
      if (person && person.instanceId !== undefined && (!thing || person.distance <= thing.distance + 20)) return { person: shown[person.instanceId] };
      if (thing) return { building: meshBids.get(thing.object as THREE.InstancedMesh)![thing.instanceId!] };
      return {} as { person?: number; building?: number; bus?: { route: number; riders: number }; police?: boolean; crime?: string };
    };
    let down: { x: number; y: number } | null = null;
    const onDown = (e: PointerEvent) => {
      down = { x: e.clientX, y: e.clientY };
    };
    const onUp = (e: PointerEvent) => {
      if (down && Math.abs(e.clientX - down.x) + Math.abs(e.clientY - down.y) < 5) {
        const hit = cast(e.clientX, e.clientY);
        if (hit.person !== undefined) picks.current.onPickPerson(hit.person);
        else if (hit.building !== undefined) picks.current.onPickBuilding(hit.building);
      }
      down = null;
    };
    let lastHover = 0;
    const onMove = (e: PointerEvent) => {
      if (down || performance.now() - lastHover < 120) return;
      lastHover = performance.now();
      const hit = cast(e.clientX, e.clientY);
      const r = el.getBoundingClientRect();
      const text =
        hit.bus !== undefined
          ? `Bus ${hit.bus.route}: ${lineName.get(hit.bus.route) ?? ""} · ${hit.bus.riders} on board`
          : hit.police
            ? "Police patrol"
            : hit.crime
              ? hit.crime
              : hit.building !== undefined
            ? city.buildings[hit.building]?.name
            : hit.person !== undefined
              ? "Click to follow this person"
              : null;
      setHover(text ? { x: e.clientX - r.left, y: e.clientY - r.top, text } : null);
    };
    const onLeave = () => setHover(null);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    controls.addEventListener("start", () => {
      if (follow) {
        follow = false;
        setFollowing(false);
      }
    });

    const resize = new ResizeObserver(() => {
      renderer.setSize(el.clientWidth, el.clientHeight);
      camera.aspect = el.clientWidth / Math.max(1, el.clientHeight);
      camera.updateProjectionMatrix();
    });
    resize.observe(el);

    renderer.setAnimationLoop(() => {
      update();
      controls.update();
      renderer.render(scene, camera);
    });
    api.current = {
      reset: () => {
        follow = false;
        setFollowing(false);
        reset();
      },
      follow: (on) => {
        follow = on;
        if (on) {
          const offset = camera.position.clone().sub(controls.target).setLength(380);
          camera.position.copy(controls.target).add(offset);
        }
      },
    };

    return () => {
      saved.current = { pos: camera.position.clone(), target: controls.target.clone() };
      renderer.setAnimationLoop(null);
      resize.disconnect();
      controls.dispose();
      renderer.domElement.remove();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh) o.geometry.dispose();
      });
      renderer.dispose();
    };
  }, [city, frames]);

  return (
    <div className="map map3d" ref={host}>
      {hover && (
        <div className="hover-tag" style={{ left: hover.x + 14, top: hover.y + 10 }}>
          {hover.text}
        </div>
      )}
      <div className="view-tools">
        <button onClick={() => api.current?.reset()}>Whole city</button>
        <button className={traffic ? "on" : ""} onClick={() => setTraffic(!traffic)} title="Busy streets turn amber, jammed ones red">
          Traffic
        </button>
        {selectedPerson !== null && (
          <button
            className={following ? "on" : ""}
            onClick={() => {
              const on = !following;
              setFollowing(on);
              api.current?.follow(on);
            }}
          >
            {following ? "Following" : "Follow them"}
          </button>
        )}
      </div>
    </div>
  );
}
