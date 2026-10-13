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
  households: number;
  jobs: number;
}

export interface CityMap {
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
  personality: Record<string, number>;
  needs: Record<string, number>;
  mood: number;
  health: number;
  skill: number;
  activity: string;
  place: string | null;
  heading_to: string | null;
  until: string | null;
  friends: { id: number; name: string; strength: number }[];
  friend_count: number;
  life: CityEvent[];
}

export interface BuildingCard extends Building {
  open: boolean;
  inside: { id: number; name: string; activity: string }[];
  inside_count: number;
  residents: number;
  workers: number;
  pupils: number;
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
}
