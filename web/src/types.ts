export type Side = 'defense' | 'attack'
export type Strength = 'strong' | 'moderate' | 'thin'
export type Phase = 'all' | 'setup' | 'mid' | 'postplant'
export type Placement = 'placed' | 'ranged' | 'thrown' | 'wall' | 'self' | 'global'

export interface TeamRow {
  id: string
  name: string
  maps_played: number
  circuit: string
  last_played: string
  maps: Record<string, number>
  events: string[]
}

export interface Callout { name: string; region: string; u: number; v: number; x: number; y: number }
export interface Site { x: number; y: number; u: number; v: number; n: number; site: string }
export interface MapMeta {
  callouts: Callout[]
  sites: Site[]
  samples: number
  bbox: [number, number, number, number]
  path: string
}

export interface Dataset {
  series: number; maps: number; rounds: number; casts: number; kills: number; teams: number
  range_label: string; excluded_maps: number; excluded_rounds: number; built: string
}

export interface Meta {
  teams: TeamRow[]
  maps: Record<string, MapMeta>
  dataset: Dataset
  mode: 'live' | 'static'
  exported?: { team: string; map: string; side: Side }[]
  replays?: string[]
}

export interface Heat { size: number; max: number; cells: [number, number, number][] }

export interface Hotspot {
  id: string
  ability: string
  ability_name: string
  agent: string
  category: string
  category_label: string
  placement: Placement
  x: number; y: number; u: number; v: number
  aim: [number, number] | null
  aim_fit: number
  casts: number
  k: number
  n: number
  pct: number
  p: number
  strength: Strength
  median_t: number
  buy_phase_pct: number
  when: string
  spread_m: number
  callout: string
  players: { name: string; casts: number }[]
  evidence: number[]
}

export interface GlobalUse {
  ability: string; ability_name: string; agent: string; category: string
  k: number; n: number; pct: number; p: number; per_round: number; first_t: number
}

export interface Utility {
  map: string; side: Side; phase: Phase; rounds: number; casts: number; radius_m: number
  hotspots: Hotspot[]; heat: Heat | null; global: GlobalUse[]
}

export interface OpArea {
  x: number; y: number; u: number; v: number
  callout: string; site: string | null; style: string; forwardness: number
  k: number; n: number; pct: number; window_share: number[]; median_t: number
  players: { name: string; samples: number }[]; evidence: number[]
  open_k: number; open_n: number; open_pct: number; open_p: number; open_evidence: number[]
}

export interface KillLine { from: [number, number]; to: [number, number]; t: number; first: boolean; round: number }

export interface Operator {
  weapon: string; rounds: number; map: string; side: Side
  buy_rounds: number; held_rounds: number; buy_pct: number; buy_p: number; transfer_pct: number; transfer_p: number; opening_rounds: number
  holders: { player: string; rounds: number; share: number; p: number; agents: string[] }[]
  areas: OpArea[]
  kills: { total: number; opening: number; opening_pct: number; opening_p: number; median_t: number | null; per_op_round: number; lines: KillLine[] }
  heat: Heat | null
  windows_heat: (Heat & { from: number; to: number })[]
  buy_round_ids: number[]
}

export interface SetupSpot { id: string; ability_name: string; agent: string; callout: string; u: number; v: number }
export interface Setup {
  rounds: number; setup_casts: number; predictability: number | null
  recurring: (SetupSpot & { pct: number; k: number; n: number })[]
  setups: { k: number; n: number; pct: number; p: number; strength: Strength; spots: SetupSpot[]; evidence: number[] }[]
  league?: number[]
}

export interface Finding {
  kind: 'utility' | 'operator' | 'setup'
  title: string
  sub: string
  k: number
  n: number
  pct: number
  unit: string
  strength: Strength
  text: string
  detail: string
  evidence: number[]
  focus: { u: number; v: number } | null
  hotspot: string | null
}

export interface RoundRef {
  round: number; game_id: string; n: number; series_id: string; map: string; date: string; date_label: string
  event: string; opponent: string; won: boolean; side: Side; result: string; live_utc: string; game_number: number
}

export interface Sample {
  rounds: number; maps: number; series: number; from: string | null; to: string | null; range_label: string
  low_rate_maps: number; median_moved_m: number | null; setup_moved_m: number | null; superseded: number
}

export interface PlanCounter {
  rounds: number | null
  contested_rounds: number | null
  uncontested_rounds: number | null
  won_contested: number | null
  won_uncontested: number | null
  win_contested: number | null
  win_uncontested: number | null
  delta: number | null
  z: number | null
  signal: 'clear' | 'some' | 'noise' | null
  tools: { ability: string; ability_name: string; agent: string; uses: number }[] | null
  contest_before: number | null
  enough: boolean | null
}

export interface PlanItem {
  id: string
  ability_name: string
  agent: string
  callout: string
  x: number
  y: number
  u: number
  v: number
  k: number
  n: number
  p: number
  strength: Strength
  advice: 'hit' | 'leave' | 'no_edge' | 'untested'
  counter: PlanCounter
}

export interface Scout {
  team: { id: string; name: string }
  sample: Sample
  utility: Utility
  operator: Operator
  setup: Setup | null
  insights: Finding[]
  plan: PlanItem[]
  rounds: Record<string, RoundRef>
}

export interface Counter {
  rounds: number; enough: boolean; contest_before: number
  contested_rounds: number; uncontested_rounds: number
  won_contested?: number; won_uncontested?: number
  win_contested?: number; win_uncontested?: number; delta?: number; z?: number
  signal?: 'clear' | 'some' | 'noise'
  tools: { ability: string; ability_name: string; agent: string; uses: number }[]
}

export interface Overview {
  team: string
  by_map: { map: string; side: Side; rounds: number; won: number; win_pct: number }[]
  recent: { date: string; date_label: string; map: string; opponent: string; score: string; won: boolean; event: string }[]
}

export interface Replay {
  game_id: string; round: number; map: string; series_id: string; date: string; date_label: string; event: string
  winner: string; result: string; duration: number
  players: { name: string; team: string; side: string; agent: string }[]
  frames: (number | [number, number, number])[][]
  casts: { t: number; p: number; ability: string; agent: string; cat: string; at: [number, number] | null; aim: [number, number] | null }[]
  kills: { t: number; killer: number | null; victim: number | null; weapon: string; from: [number, number] | null; to: [number, number] | null }[]
  events: { t: number; type: string; p: number | null; at: [number, number] | null }[]
}
