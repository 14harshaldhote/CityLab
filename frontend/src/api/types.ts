export interface CityNode {
  id: number;
  x: number;
  y: number;
}

export interface Building {
  id: number;
  kind: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  district: string;
  central?: boolean;
  households: number;
  jobs: number;
  status?: "open" | "construction";
  progress?: number;
  owner?: string;
  opened_day?: number;
  planned?: number;
}

export interface Plot {
  x: number;
  y: number;
  w: number;
  h: number;
  zone: "residential" | "commercial" | "industrial";
  district: string;
}

export interface BusLine {
  number: string;
  name: string;
  color: string;
  nodes: number[];
  stops: number[];
}

export interface BusStop {
  id: number;
  name: string;
  x: number;
  y: number;
  node: number;
  lines: string[];
}

export interface CityMap {
  name: string;
  transit?: { lines: BusLine[]; stops: BusStop[] };
  wide?: [number, number][];
  cameras?: Camera[];
  widening?: [number, number][];
  version?: number;
  plots?: Plot[];
  roadworks?: { x: number; y: number; w: number; h: number }[];
  size: number;
  spacing: number;
  nodes: CityNode[];
  edges: [number, number][];
  buildings: Building[];
  districts: string[];
  activities: string[];
}

export interface WeatherNow {
  temperature_c: number;
  rain_mm_h: number;
  cloud_pct: number;
  sun_elevation_deg: number;
  sun_azimuth_deg: number;
  phase: number;
}

export interface Frame {
  t: number;
  label: string;
  day: number;
  minute_of_day: number;
  weather: WeatherNow;
  ids: number[];
  x: number[];
  y: number[];
  activity: number[];
  age: number[];
  place: number[];
  move?: number[]; // 0 not travelling, 1 walking, 2 driving, 3 on a bus, 4 in an auto, 5 waiting
  buses?: [number, number, number, number, number, number][]; // id, x, y, heading, route, riders
  traffic?: [number, number, number][]; // corner, corner, how full (1 = jammed)
  police?: [number, number, number, number][]; // id, x, y, heading
  crimes?: [number, number, number, number, number][]; // x, y, minutes ago, kind (0 pickpocket, 1 shoplift, 2 burglary), solved
  city_version?: number;
  sites?: [number, number][];
  counts: Record<string, number>;
  playing: boolean;
  speed: number;
}

export interface Summary {
  t: number;
  label: string;
  population: number;
  households: number;
  employed: number;
  unemployed: number;
  pupils: number;
  retired: number;
  couples: number;
  vacancies: number;
  free_homes: number;
  social: { people: number; ties: number; friendships: number; avg_ties: number };
  events: number;
  city: string;
  religions: Record<string, number>;
  festival: { name: string; faith: string; text: string } | null;
  playing: boolean;
  speed: number;
  step_ms: number;
  seed: number;
}

export interface PersonRef {
  id: number;
  name: string;
  age: number;
  alive: boolean;
}

export interface CityEvent {
  id: number;
  t: number;
  when: string;
  kind: string;
  text: string;
  people: number[];
  place: number | null;
}

export interface PersonCard {
  id: number;
  name: string;
  sex: string;
  age: number;
  stage: string;
  alive: boolean;
  home: { building: number; name: string; district: string };
  household: (PersonRef | null)[];
  partner: PersonRef | null;
  parents: (PersonRef | null)[];
  children: (PersonRef | null)[];
  job: { building: number; place: string; kind: string; wage_per_day: number; shift: string; since_day: number } | null;
  school: string | null;
  retired: boolean;
  unemployed: boolean;
  religion: string;
  devotion: number;
  personality: Record<string, number>;
  needs: Record<string, number>;
  mood: number;
  health: number;
  skill: number;
  activity: string;
  place: string | null;
  heading_to: string | null;
  travel?: string | null;
  convictions?: number;
  in_jail_until?: string | null;
  until: string | null;
  friends: { id: number; name: string; strength: number }[];
  friend_count: number;
  money: { balance: number; credit_score: number; debt: number; loans: { balance: number; rate: number; instalment: number; missed: number }[] };
  life: CityEvent[];
}

export interface BuildingCard extends Building {
  open: boolean;
  inside: { id: number; name: string; activity: string }[];
  inside_count: number;
  residents: number;
  workers: number;
  pupils: number;
  company: { public: boolean; funded_by?: string; balance?: number; credit_score?: number; debt?: number } | null;
}

export interface Agencies {
  day: number;
  departments: { key: string; name: string; sector: "government" | "private"; does: string; watching: string; head: { id: number; name: string } | null; spent: number; done: number }[];
  projects: { building: number; name: string; kind: string; district: string; owner: string; progress: number; started_day: number; days_left: number; crew: number; crew_needed: number; why: string }[];
  roadworks: { district?: string; zone?: string; street?: string; progress: number; why: string }[];
  plots: Record<string, number>;
  finished: { building: number; name: string; kind: string; owner: string; day: number; district: string }[];
}

export interface CompanyRow {
  id: number;
  name: string;
  kind: string;
  balance: number;
  workers: number;
  jobs: number;
  debt: number;
}

export interface Economy {
  money_people: number;
  money_companies: number;
  median_balance: number;
  in_debt: number;
  city: number;
  bank: number;
  loans_outstanding: number;
  loans: number;
  base_rate: number;
  savings_rate: number;
  loan_rate_typical: number;
  gdp: number;
  tax: number;
  flows: Record<string, number>;
  richest_companies: CompanyRow[];
  struggling_companies: CompanyRow[];
}

export interface DailyRow {
  day: number;
  population: number;
  employed: number;
  unemployed: number;
  births: number;
  deaths: number;
  arrived: number;
  left: number;
  couples: number;
  new_friendships: number;
  ties: number;
  clustering: number;
  median_balance: number;
  city: number;
  loans_outstanding: number;
  gdp: number;
  tax: number;
  in_debt: number;
  trips_walk?: number;
  trips_car?: number;
  trips_bus?: number;
  trips_auto?: number;
  commute_min?: number;
  late?: number;
  bus_riders?: number;
  worst_jam_kmh?: number | null;
  crimes?: number;
  crimes_reported?: number;
  deterred?: number;
  arrests?: number;
  convicted?: number;
  acquitted?: number;
  stolen?: number;
  cameras?: number;
  in_jail?: number;
}

export interface Transport {
  now: { walking: number; driving: number; on_buses: number; in_autos: number; waiting: number; buses: number };
  jams: { street: string; ratio: number; speed_kmh: number }[];
  lines: { number: string; name: string; color: string; stops: number; km: number; buses_now: number; riders_now: number; riders_today: number; every: number | null }[];
  today: { trips: Record<string, number>; commute_min: number; late: number; fares: number; bus_km: number };
  history: DailyRow[];
  fares: { bus: number; auto_min: number; auto_per_km: number; petrol_per_km: number };
  widened: string[];
}

export interface Camera {
  node: number;
  x: number;
  y: number;
  name: string;
}

export interface CrimeCase {
  id: number;
  kind: string;
  when: string;
  day: number;
  place: string;
  building: number | null;
  victim: string;
  victim_id: number | null;
  value: number;
  evidence: number;
  cctv: boolean;
  witnesses: number;
  status: string;
  caught_in_the_act: boolean;
  verdict: string;
  hearing: string | null;
  suspect: { id: number; name: string } | null;
}

export interface Safety {
  today: { crimes_reported: number; arrests: number; deterred: number; convicted: number; acquitted: number };
  month: { crimes: number; reported: number; solved: number; with_cctv: number; solved_with_cctv: number; stolen: number };
  police: { on_duty: number; patrols: number; cameras: number };
  cases: CrimeCase[];
  court: CrimeCase[];
  verdicts: CrimeCase[];
  in_jail: { id: number; name: string; until: string }[];
  cameras: Camera[];
  history: DailyRow[];
}
