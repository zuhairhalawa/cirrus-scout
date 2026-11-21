import type { Counter, Meta, Overview, Phase, Replay, Scout, Side } from './types'

// Live mode talks to `python -m scout serve`. Static mode (the hosted demo) reads the
// aggregate-only JSON written by `python -m scout export` into ./data.
let mode: 'live' | 'static' | null = null

async function getJSON<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`Request failed (${r.status})`)
  return r.json() as Promise<T>
}

export async function loadMeta(): Promise<Meta> {
  try {
    const m = await getJSON<Meta>('/api/meta')
    mode = 'live'
    return m
  } catch {
    mode = 'static'
    return getJSON<Meta>('./data/meta.json')
  }
}

export const isLive = () => mode === 'live'

const slug = (s: string) => s.replace(/[^a-zA-Z0-9_-]/g, '_')

export function loadScout(team: string, map: string, side: Side, since: string, period: 'recent' | 'all', phase: Phase): Promise<Scout> {
  if (mode === 'live') {
    const q = new URLSearchParams({ team, map, side, since, phase })
    return getJSON(`/api/scout?${q}`)
  }
  return getJSON(`./data/scout/${slug(team)}/${map}-${side}${period === 'all' ? '-all' : ''}.json`)
}

export function loadOverview(team: string): Promise<Overview> {
  if (mode === 'live') return getJSON(`/api/overview?team=${encodeURIComponent(team)}`)
  return getJSON(`./data/overview/${slug(team)}.json`)
}

export function loadCounter(map: string, x: number, y: number, ability: string, id: string): Promise<Counter | null> {
  if (mode === 'live') return getJSON(`/api/counter?map=${map}&x=${x}&y=${y}&ability=${encodeURIComponent(ability)}`)
  return getJSON<Counter>(`./data/counter/${map}/${slug(id)}.json`).catch(() => null)
}

export function loadReplay(game: string, round: number): Promise<Replay | null> {
  if (mode === 'live') return getJSON(`/api/replay?game=${game}&round=${round}`)
  return getJSON<Replay>(`./data/replays/${game}_${round}.json`).catch(() => null)
}
