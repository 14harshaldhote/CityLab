import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { CityMap as City, Frame } from "../api/types";
import { daylight, hash01 } from "../engine/art";
import { buildingModel, outskirtsModel, streetModel, type Part, type Shape, type Win } from "../engine/models";
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
    reset();

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
    parts.push(...streets.parts, ...outskirtsModel(city));

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

      if (next.t !== lastT) {
        lastT = next.t;
        const night = sky(next);
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
        const driving = pl < 0 && next.car?.[i] === 1;
        const side = pl < 0 ? (driving ? 5 : 13) : 0;
        const x = pos.x[i] + hz * side;
        const z = pos.y[i] - hx * side;
        prevPos.set(id, [x, z]);
        if (driving) {
          const cs = Math.max(1.2, S * 0.55);
          place(carBody, nc, x, 0.3, z, cs, cs, cs, -h);
          place(carTop, nc, x, 0.3, z, cs, cs, cs, -h);
          carBody.setColorAt(nc, col.setHex(CAR_COLORS[id % CAR_COLORS.length]));
          nc++;
        } else {
          const child = next.age[i] < 13 ? 0.7 : 1;
          const s = S * child;
          const bob = pl < 0 ? Math.abs(Math.sin(time * 9 + id)) * 0.35 * s : 0;
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
      for (const m of [bodies, heads, carBody, carTop]) {
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
      const thing = ray.intersectObjects(pickable, false).find((h) => h.instanceId !== undefined && meshBids.get(h.object as THREE.InstancedMesh)![h.instanceId!] >= 0);
      if (person && person.instanceId !== undefined && (!thing || person.distance <= thing.distance + 20)) return { person: shown[person.instanceId] };
      if (thing) return { building: meshBids.get(thing.object as THREE.InstancedMesh)![thing.instanceId!] };
      return {};
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
      const text = hit.building !== undefined ? city.buildings[hit.building]?.name : hit.person !== undefined ? "Click to follow this person" : null;
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
