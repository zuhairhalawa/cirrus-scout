import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { isLive, loadCounter, loadMeta, loadOverview, loadReplay, loadScout } from './api'
import { MapView } from './components/MapView'
import { ReplayFeed, ReplayPlayer } from './components/ReplayPlayer'
import { CAT_LABEL, CAT_ORDER, GlyphIcon, Icon, Seg, ShareBar, StrengthChip, cap, clock } from './components/ui'
import type { Counter, Finding, Hotspot, Meta, OpArea, Overview, Phase, Replay, RoundRef, Scout, Side, TeamRow } from './types'

type Mode = 'utility' | 'operator' | 'setup' | 'replay'
type Period = 'recent' | 'all'
type Evidence = { title: string; rounds: number[] }

const MODES: { id: Mode; label: string }[] = [
  { id: 'utility', label: 'Utility' },
  { id: 'operator', label: 'Operator' },
  { id: 'setup', label: 'Setups' },
  { id: 'replay', label: 'Replay' },
]
const WINDOWS = ['0–20s', '20–40s', '40s+']
const TOP_SPOTS = 10
const PLACEMENT_NOTE: Record<string, string> = {
  placed: 'The marker is where the device sits, to within a couple of metres.',
  ranged: 'The marker is where the player stood. The device sits further along the dotted aim line.',
  thrown: 'The marker is where it was thrown from. The dotted line is the aim; the data has no landing point.',
  wall: 'The marker is where it starts. The line shows its direction.',
}

function readHash() {
  const h = new URLSearchParams(location.hash.slice(1))
  return {
    team: h.get('team') ?? undefined, map: h.get('map') ?? undefined,
    side: (h.get('side') as Side) ?? undefined, mode: (h.get('mode') as Mode) ?? undefined,
    period: (h.get('period') as Period) ?? undefined,
  }
}

function sinceFor(team: TeamRow | undefined, period: Period) {
  if (!team || period === 'all') return ''
  const d = new Date(team.last_played + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() - 183)
  return d.toISOString().slice(0, 10)
}

const store = {
  get: (k: string) => { try { return localStorage.getItem(k) } catch { return null } },
  set: (k: string, v: string) => { try { localStorage.setItem(k, v) } catch { /* private mode */ } },
}

function Brand() {
  return (
    <div className="brand">
      <svg className="brand-mark" viewBox="0 0 32 32" aria-hidden="true">
        <rect width="32" height="32" rx="7" fill="var(--ink)" />
        <path d="M7 20c0-3.3 2.6-6 5.8-6 .8-2.6 3.2-4.4 6-4.4 3.5 0 6.2 2.8 6.2 6.2 0 .2 0 .4-.1.6 1.3.5 2.1 1.7 2.1 3.1 0 1.9-1.5 3.5-3.4 3.5H10.4C8.5 23 7 21.6 7 20z" fill="var(--sky-fill)" />
        <circle cx="21" cy="17" r="2.2" fill="var(--coral)" />
      </svg>
      <span className="brand-name">Cirrus</span>
      <span className="brand-sub">VALORANT scouting</span>
    </div>
  )
}

function FindingRow({ f, active, onClick }: { f: Finding; active: boolean; onClick: () => void }) {
  return (
    <li>
      <button type="button" className="finding" aria-pressed={active} onClick={onClick}>
        <span className="finding-pct num">{f.pct}%</span>
        <span className="finding-body">
          <span className="finding-title">{f.title}</span>
          <span className="finding-sub">{f.sub}</span>
          <span className="finding-meta">
            <ShareBar pct={f.pct} />
            <StrengthChip s={f.strength} />
          </span>
        </span>
      </button>
      {active && <p className="finding-detail">{f.detail}</p>}
    </li>
  )
}

function CounterBlock({ counter, mapName }: { counter: Counter | null | 'loading'; mapName: string }) {
  if (counter === 'loading') return <p className="muted">Checking every round on {mapName} where a defense used this spot.</p>
  if (!counter) return null
  if (counter.rounds === 0) return <p className="muted">No other round in the data has a defense using this exact spot.</p>
  if (!counter.enough) {
    return (
      <p className="muted">
        Attackers put utility on this spot early in only {counter.contested_rounds} of {counter.rounds.toLocaleString()} league rounds
        with this setup. That is too few to compare.
      </p>
    )
  }
  const d = counter.delta ?? 0
  const reliable = counter.signal !== 'noise'
  return (
    <>
      <p className="counter-figure">
        <span className={`num counter-delta ${reliable ? (d >= 0 ? 'up' : 'down') : ''}`}>{d >= 0 ? '+' : '−'}{Math.abs(d)}</span>
        <span>points of attack win rate when attackers hit it early</span>
      </p>
      <p>
        Across {counter.rounds.toLocaleString()} league rounds with this setup, attackers who put utility on it in the first{' '}
        {counter.contest_before} seconds won <strong>{counter.win_contested}%</strong> ({counter.won_contested} of{' '}
        {counter.contested_rounds}). When they left it alone they won <strong>{counter.win_uncontested}%</strong> (
        {counter.won_uncontested} of {counter.uncontested_rounds}).
      </p>
      <p className="signal" data-signal={counter.signal}>
        {counter.signal === 'clear' ? 'Clear signal.' : counter.signal === 'some' ? 'Some signal.' : 'Within noise: no reliable edge either way.'}{' '}
        <span className="faint">z = {counter.z}. An association across the league, not proof of cause.</span>
      </p>
      {counter.tools.length > 0 && (
        <p className="muted">Used on it most: {counter.tools.slice(0, 3).map((t) => `${t.agent} ${t.ability_name}`).join(', ')}.</p>
      )}
    </>
  )
}

function HelpDialog({ open, onClose, meta }: { open: boolean; onClose: () => void; meta: Meta }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  const ds = meta.dataset
  return (
    <dialog ref={ref} className="help" onClose={onClose} aria-labelledby="help-title">
      <header>
        <h2 id="help-title">How to read Cirrus</h2>
        <button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><Icon name="close" /></button>
      </header>
      <dl>
        <dt>Spot</dt>
        <dd>A place where a team used the same ability within 4.5 m in at least two rounds. Its percentage is the share of rounds on that map and side with the ability inside that circle.</dd>
        <dt>Evidence strength</dt>
        <dd>Strong: 15+ rounds and at least 40% of them even on a cautious estimate. Moderate: 8+ rounds and at least 20%. Thin: anything less. Treat thin findings as leads to check.</dd>
        <dt>What a marker shows</dt>
        <dd>Where the player stood when the ability was used. Traps and turrets sit there. Thrown utility shows its origin and aim; the data has no landing points. Smokes aimed on a tactical map are listed, not drawn.</dd>
        <dt>Setup</dt>
        <dd>Traps and cams still standing when the round goes live, plus anything placed in the first 20 seconds. A device picked up and placed again counts once, where it ended up.</dd>
        <dt>Operator opening</dt>
        <dd>For each round with an Operator, the one area where its holder spent most of the first 20 seconds.</dd>
        <dt>Counter</dt>
        <dd>For a defensive spot, every round in the data where any team used it. Attack win rate when attackers put recon, damage, flash or stall utility on it in the first 25 seconds, against when they did not.</dd>
        <dt>Data</dt>
        <dd>Official GRID match feeds: {ds.series.toLocaleString()} series, {ds.maps.toLocaleString()} maps, {ds.rounds.toLocaleString()} rounds, {ds.range_label}. {ds.excluded_maps > 0 ? `${ds.excluded_maps} map was left out because its rebuilt score did not match the official one. ` : ''}{ds.excluded_rounds > 0 ? `${ds.excluded_rounds} rounds were left out because their result contradicted their sides. ` : ''}Processed {ds.built}.</dd>
      </dl>
    </dialog>
  )
}

export default function App() {
  const init = useMemo(readHash, [])
  const [meta, setMeta] = useState<Meta | null>(null)
  const [fatal, setFatal] = useState<string | null>(null)
  const [teamId, setTeamId] = useState<string | undefined>(init.team)
  const [map, setMap] = useState<string | undefined>(init.map)
  const [side, setSide] = useState<Side>(init.side ?? 'defense')
  const [period, setPeriod] = useState<Period>(init.period ?? 'recent')
  const [mode, setMode] = useState<Mode>(init.mode ?? 'utility')
  const [phase, setPhase] = useState<Phase>('all')
  const [view, setView] = useState<'spots' | 'heat'>('spots')
  const [showAll, setShowAll] = useState(false)
  const [scout, setScout] = useState<Scout | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [reload, setReload] = useState(0)
  const [overview, setOverview] = useState<Overview | null>(null)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [active, setActive] = useState<Hotspot | null>(null)
  const [counter, setCounter] = useState<Counter | null | 'loading'>(null)
  const [activeFinding, setActiveFinding] = useState<number | null>(null)
  const [evidence, setEvidence] = useState<Evidence | null>(null)
  const [focus, setFocus] = useState<{ u: number; v: number } | null>(null)
  const [opWindow, setOpWindow] = useState<number | null>(null)
  const [activeArea, setActiveArea] = useState<string | null>(null)
  const [setupIdx, setSetupIdx] = useState(0)
  const [replay, setReplay] = useState<Replay | null>(null)
  const [replayRef, setReplayRef] = useState<RoundRef | null>(null)
  const [replayLoading, setReplayLoading] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => (store.get('cirrus-theme') === 'dark' ? 'dark' : 'light'))

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    store.set('cirrus-theme', theme)
  }, [theme])

  useEffect(() => {
    loadMeta().then(setMeta).catch((e) => setFatal(String(e.message ?? e)))
    const onHash = () => {
      const h = readHash()
      if (h.team) setTeamId(h.team)
      if (h.map) setMap(h.map)
      if (h.side) setSide(h.side)
      if (h.mode) setMode(h.mode)
      if (h.period) setPeriod(h.period)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const exported = useMemo(() => new Set((meta?.exported ?? []).map((e) => `${e.team}|${e.map}|${e.side}`)), [meta])
  const teams = useMemo(() => {
    if (!meta) return []
    if (meta.mode !== 'static') return meta.teams
    const ids = new Set((meta.exported ?? []).map((e) => e.team))
    return meta.teams.filter((t) => ids.has(t.id))
  }, [meta])
  const team = useMemo(() => teams.find((t) => t.id === teamId) ?? teams[0], [teams, teamId])

  const teamMaps = useMemo(() => {
    if (!team || !meta) return []
    return Object.entries(team.maps)
      .filter(([m]) => meta.maps[m]?.path)
      .filter(([m]) => meta.mode !== 'static' || exported.has(`${team.id}|${m}|defense`) || exported.has(`${team.id}|${m}|attack`))
      .sort((a, b) => b[1] - a[1])
  }, [team, meta, exported])

  useEffect(() => {
    if (!team) return
    if (!map || !teamMaps.some(([m]) => m === map)) setMap(teamMaps[0]?.[0])
  }, [team, teamMaps, map])

  useEffect(() => {
    if (!team || !map) return
    const h = new URLSearchParams({ team: team.id, map, side, mode, period })
    history.replaceState(null, '', `#${h.toString()}`)
  }, [team, map, side, mode, period])

  const since = sinceFor(team, period)
  const livePhase: Phase = isLive() ? phase : 'all'

  const clearSelection = useCallback(() => {
    setActive(null); setCounter(null); setActiveFinding(null); setEvidence(null); setFocus(null); setActiveArea(null)
  }, [])

  useEffect(() => {
    if (!team || !map) return
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    clearSelection()
    setSetupIdx(0)
    loadScout(team.id, map, side, since, period, livePhase)
      .then((s) => { if (!cancelled) setScout(s) })
      .catch((e) => { if (!cancelled) { setScout(null); setLoadError(String(e.message ?? e)) } })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [team, map, side, since, period, livePhase, reload, clearSelection])

  useEffect(() => {
    if (!team) return
    loadOverview(team.id).then(setOverview).catch(() => setOverview(null))
  }, [team])

  const selectHotspot = useCallback((h: Hotspot) => {
    if (!map) return
    setActive(h)
    setActiveArea(null)
    setFocus({ u: h.u, v: h.v })
    setEvidence({ title: `${h.agent} ${h.ability_name}, ${h.callout}`, rounds: h.evidence })
    if (side === 'defense' && (h.category === 'trap' || h.category === 'sentinel')) {
      setCounter('loading')
      loadCounter(map, h.x, h.y, h.ability, h.id).then(setCounter).catch(() => setCounter(null))
    } else {
      setCounter(null)
    }
  }, [map, side])

  const selectArea = useCallback((a: OpArea) => {
    setActiveArea(a.callout)
    setActive(null)
    setFocus({ u: a.u, v: a.v })
    setEvidence(a.open_k
      ? { title: `Operator opens at ${a.callout}`, rounds: a.open_evidence }
      : { title: `Operator seen at ${a.callout}`, rounds: a.evidence })
  }, [])

  const selectFinding = useCallback((f: Finding, i: number) => {
    if (activeFinding === i) { clearSelection(); return }
    setActiveFinding(i)
    setEvidence({ title: f.title, rounds: f.evidence })
    setFocus(f.focus)
    if (f.kind === 'operator') {
      setMode('operator'); setActive(null); setOpWindow(null)
      const a = scout?.operator.areas.find((x) => f.focus && Math.abs(x.u - f.focus.u) < 1e-6)
      setActiveArea(a?.callout ?? null)
    } else if (f.kind === 'setup') {
      setMode('setup'); setSetupIdx(0); setActive(null); setActiveArea(null)
    } else {
      setMode('utility'); setView('spots')
      const h = scout?.utility.hotspots.find((x) => x.id === f.hotspot)
      if (h) { selectHotspot(h); setActiveFinding(i); setEvidence({ title: f.title, rounds: f.evidence }) }
    }
  }, [activeFinding, clearSelection, scout, selectHotspot])

  const openRound = useCallback((ref: RoundRef) => {
    setReplayRef(ref)
    setReplayLoading(true)
    setMode('replay')
    loadReplay(ref.game_id, ref.n)
      .then((r) => setReplay(r))
      .catch(() => setReplay(null))
      .finally(() => setReplayLoading(false))
  }, [])

  const changeMode = (m: Mode) => { setMode(m); setFocus(null) }

  if (fatal && !meta) {
    return (
      <div className="splash">
        <Brand />
        <p>Cirrus could not load its data ({fatal}).</p>
        <p className="muted">Start the local server with <code>python -m scout serve</code>, then reload this page.</p>
      </div>
    )
  }
  if (!meta || !team) return <div className="splash" aria-busy="true"><Brand /><p className="muted">Loading scouting data</p></div>

  const mm = map ? meta.maps[map] : undefined
  const u = scout?.utility
  const op = scout?.operator
  const fp = scout?.setup
  const sm = scout?.sample
  const mapName = map ? cap(map) : ''
  const sideRounds = `${side} rounds`

  const allSpots = (u?.hotspots ?? []).filter((h) => !hidden.has(h.category))
  const visibleSpots = showAll ? allSpots : allSpots.slice(0, TOP_SPOTS)
  const mapSpots = active && !visibleSpots.some((h) => h.id === active.id) ? [...visibleSpots, active] : visibleSpots
  const catCounts: Record<string, number> = {}
  for (const h of u?.hotspots ?? []) catCounts[h.category] = (catCounts[h.category] ?? 0) + 1

  const evRefs: RoundRef[] = (evidence?.rounds ?? []).map((r) => scout?.rounds[String(r)]).filter(Boolean) as RoundRef[]
  evRefs.sort((a, b) => (a.date === b.date ? b.n - a.n : a.date < b.date ? 1 : -1))
  const canReplay = (ref: RoundRef) => isLive() || (meta.replays ?? []).includes(`${ref.game_id}_${ref.n}`)
  const setupSpots = fp?.setups[setupIdx]?.spots ?? []
  const ds = meta.dataset

  return (
    <div className="app">
      <header className="topbar">
        <Brand />
        <label className="field">
          <span className="field-label">Scouting</span>
          <select className="select" value={team.id} onChange={(e) => { setTeamId(e.target.value); setMap(undefined); setReplay(null); setReplayRef(null) }}>
            {['VCT', 'Game Changers'].map((circuit) => (
              <optgroup key={circuit} label={circuit}>
                {teams.filter((t) => t.circuit === circuit).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        <Seg label="Side" value={side} onChange={setSide} options={[{ id: 'defense', label: 'Defense' }, { id: 'attack', label: 'Attack' }]} />
        <Seg label="Period" value={period} onChange={setPeriod}
             options={[{ id: 'recent', label: 'Last 6 months', title: "Counted back from the team's most recent match in the data" }, { id: 'all', label: 'All matches' }]} />
        <div className="spacer" />
        <button type="button" className="icon-btn" onClick={() => setHelpOpen(true)} aria-label="How to read Cirrus" title="How to read Cirrus"><Icon name="help" /></button>
        <button type="button" className="icon-btn" onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
                aria-label={theme === 'light' ? 'Switch to dark theme' : 'Switch to light theme'} title={theme === 'light' ? 'Dark theme' : 'Light theme'}>
          <Icon name={theme === 'light' ? 'moon' : 'sun'} />
        </button>
        <button type="button" className="btn primary" onClick={() => window.print()}><Icon name="print" /> Print brief</button>
      </header>

      <nav className="mapbar" aria-label="Map">
        {teamMaps.map(([m, n]) => (
          <button key={m} type="button" className="map-tab" aria-pressed={m === map} title={`${n} maps played in the data`}
                  onClick={() => { setMap(m); setReplay(null); setReplayRef(null); if (mode === 'replay') setMode('utility') }}>
            {cap(m)} <span className="num">{n}</span>
          </button>
        ))}
        <span className="mapbar-note">maps played</span>
      </nav>

      <main className="body">
        <section className="findings" aria-label="Findings">
          <h1>{team.name}<span>{mapName} {side}</span></h1>
          {sm ? (
            <p className="sample">
              <strong>{sm.rounds} {sideRounds}</strong> from {sm.maps} {sm.maps === 1 ? 'map' : 'maps'}, {sm.range_label}
            </p>
          ) : (
            <p className="sample">{loadError ? 'No data loaded' : 'Loading'}</p>
          )}
          {sm && sm.low_rate_maps > 0 && sm.setup_moved_m !== null && (
            <p className="quality">
              Position tracking is once per second in {sm.low_rate_maps} of these {sm.maps} maps, so a marker can be off
              by about {sm.setup_moved_m.toFixed(1)} m.
            </p>
          )}

          {loadError && (
            <div className="notice" role="alert">
              <p>This view could not be loaded ({loadError}).</p>
              <button type="button" className="btn" onClick={() => setReload((x) => x + 1)}>Try again</button>
            </div>
          )}

          {loading && !scout && <div className="skeleton" aria-hidden="true"><i /><i /><i /></div>}

          {scout && (
            <>
              <h2>Key findings</h2>
              {scout.insights.length === 0 ? (
                <p className="muted">Too few rounds here to call a pattern. Try All matches, or another map.</p>
              ) : (
                <ol className="finding-list" data-loading={loading}>
                  {scout.insights.map((f, i) => (
                    <FindingRow key={f.title} f={f} active={activeFinding === i} onClick={() => selectFinding(f, i)} />
                  ))}
                </ol>
              )}
            </>
          )}

          {overview && (
            <>
              <h2>Recent maps</h2>
              <ul className="recent">
                {overview.recent.slice(0, 6).map((r, i) => (
                  <li key={i}>
                    <span className="recent-date">{r.date_label}</span>
                    <span>{cap(r.map)} vs {r.opponent}</span>
                    <span className={`num ${r.won ? 'won' : 'lost'}`}>{r.score}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>

        <section className="stage" aria-label="Map">
          <div className="stage-bar">
            <div className="tabs" role="tablist" aria-label="View">
              {MODES.map((m) => (
                <button key={m.id} type="button" role="tab" className="tab" aria-selected={mode === m.id} onClick={() => changeMode(m.id)}>
                  {m.label}
                </button>
              ))}
            </div>
            <div className="stage-tools">
              {mode === 'utility' && (
                <>
                  {isLive() && (
                    <Seg label="Round phase" value={phase} onChange={setPhase} options={[
                      { id: 'all', label: 'Whole round' },
                      { id: 'setup', label: 'Setup', title: 'Buy phase and the first 20 seconds' },
                      { id: 'mid', label: 'Mid-round', title: 'After 20 seconds, before the plant' },
                      { id: 'postplant', label: 'Post-plant' },
                    ]} />
                  )}
                  <Seg label="Map display" value={view} onChange={setView} options={[{ id: 'spots', label: 'Spots' }, { id: 'heat', label: 'Heatmap' }]} />
                </>
              )}
              {mode === 'operator' && (
                <Seg label="Round time" value={opWindow === null ? 'open' : String(opWindow)} onChange={(v) => setOpWindow(v === 'open' ? null : Number(v))}
                     options={[{ id: 'open', label: 'Opening area', title: 'Where the Operator spends most of the first 20 seconds' }, ...WINDOWS.map((w, i) => ({ id: String(i), label: w }))]} />
              )}
            </div>
          </div>

          <div className="stage-map" data-loading={loading}>
            {mode === 'replay' ? (
              replay && meta.maps[replay.map] ? (
                <ReplayPlayer replay={replay} meta={meta.maps[replay.map]} theme={theme} autoPlay />
              ) : (
                <div className="empty">
                  <h3>{replayLoading ? 'Building the replay' : 'Replay a round'}</h3>
                  <p>{replayLoading
                    ? 'Reading this round from the GRID feed.'
                    : 'Select a finding, then pick a round from the evidence strip below. It replays in 2D: every player, every ability and every kill.'}</p>
                </div>
              )
            ) : mm && map ? (
              <MapView
                map={map}
                meta={mm}
                mode={mode}
                theme={theme}
                hotspots={view === 'heat' ? mapSpots.slice(0, 3) : mapSpots}
                heat={u?.heat}
                showHeat={view === 'heat'}
                activeId={active?.id}
                onHotspot={selectHotspot}
                operator={op}
                opWindow={opWindow}
                activeArea={activeArea}
                onArea={selectArea}
                recurring={fp?.recurring}
                setupSpots={setupSpots}
                focus={focus}
                onResetFocus={() => setFocus(null)}
              />
            ) : null}
          </div>
          <p className="stage-note">
            {mode === 'utility' && view === 'heat' && (
              <>
                <span className="ramp" aria-hidden="true"><i>Less</i><b /><i>More</i></span>
                utility used from that area. The three most repeated spots stay marked.
              </>
            )}
            {mode === 'utility' && view !== 'heat' && 'Each marker is a repeated utility spot; bigger means more rounds. A solid line is a wall’s direction.'}
            {mode === 'operator' && 'Blue circles: where the Operator is held. Lines: its kills, shooter to victim. Red lines are opening picks.'}
            {mode === 'setup' && 'Filled squares: the selected setup. Grey squares: other spots the team reuses.'}
            {mode === 'replay' && replay && 'Blue: defenders. Red: attackers. Positions update about once a second with game events; movement between is interpolated.'}
          </p>
        </section>

        <aside className="rail" aria-label="Details">
          {mode === 'utility' && u && (
            <>
              <h2>Utility spots</h2>
              <p className="lede">
                Where {team.name} used the same ability within {u.radius_m} m in two or more {sideRounds}. Percentages are the share of {sideRounds}.
              </p>

              {active ? (
                <section className="detail">
                  <header>
                    <GlyphIcon cat={active.category} size={20} />
                    <div>
                      <h3>{active.agent} {active.ability_name}</h3>
                      <p>{active.callout}</p>
                    </div>
                    <button type="button" className="icon-btn" onClick={clearSelection} aria-label="Clear selection"><Icon name="close" /></button>
                  </header>
                  <p className="figure"><span className="num">{active.p}%</span><span>{active.k} of {active.n} {sideRounds}</span></p>
                  <StrengthChip s={active.strength} />
                  <dl className="facts">
                    <dt>When</dt><dd>{cap(active.when)}</dd>
                    <dt>Who</dt><dd>{active.players.map((p) => p.name).join(', ')}</dd>
                    <dt>Tightness</dt><dd>Within {active.spread_m} m of the marker (median)</dd>
                  </dl>
                  <p className="muted">{PLACEMENT_NOTE[active.placement]}</p>
                  {side === 'defense' && (active.category === 'trap' || active.category === 'sentinel') && (
                    <section className="counter">
                      <h3>Does hitting it early pay off?</h3>
                      <CounterBlock counter={counter} mapName={mapName} />
                    </section>
                  )}
                </section>
              ) : (
                <>
                  <ul className="filters" aria-label="Utility types">
                    {CAT_ORDER.filter((c) => catCounts[c]).map((c) => (
                      <li key={c}>
                        <button type="button" aria-pressed={!hidden.has(c)}
                                onClick={() => setHidden((s) => { const n = new Set(s); if (n.has(c)) n.delete(c); else n.add(c); return n })}>
                          <GlyphIcon cat={c} />
                          <span>{CAT_LABEL[c]}</span>
                          <span className="num">{catCounts[c]}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                  {allSpots.length === 0 ? (
                    <p className="muted">No repeated utility spots in this phase. Try Whole round or All matches.</p>
                  ) : (
                    <>
                      <h3>Most repeated</h3>
                      <ol className="spot-list">
                        {allSpots.slice(0, 8).map((h) => (
                          <li key={h.id}>
                            <button type="button" onClick={() => selectHotspot(h)}>
                              <GlyphIcon cat={h.category} />
                              <span className="spot-name"><strong>{h.ability_name}</strong> {h.callout}</span>
                              <ShareBar pct={h.pct} />
                              <span className="num">{h.p}%</span>
                            </button>
                          </li>
                        ))}
                      </ol>
                      {allSpots.length > TOP_SPOTS && (
                        <button type="button" className="btn quiet" onClick={() => setShowAll((x) => !x)}>
                          {showAll ? `Show only the top ${TOP_SPOTS} on the map` : `Show all ${allSpots.length} spots on the map`}
                        </button>
                      )}
                    </>
                  )}
                  {u.global.length > 0 && (
                    <>
                      <h3>Used from anywhere</h3>
                      <p className="muted">Aimed on a tactical map, so the caster’s position says nothing about where it lands.</p>
                      <ul className="plain-list">
                        {u.global.slice(0, 5).map((g) => (
                          <li key={g.ability}>
                            <span><strong>{g.agent} {g.ability_name}</strong></span>
                            <span className="muted">{g.p}% of rounds, first at {g.first_t < 0 ? 'buy phase' : clock(g.first_t)}</span>
                          </li>
                        ))}
                      </ul>
                    </>
                  )}
                </>
              )}
            </>
          )}

          {mode === 'operator' && op && (
            <>
              <h2>Operator</h2>
              <p className="figure"><span className="num">{op.buy_p}%</span><span>of {sideRounds} start with an Operator ({op.buy_rounds} of {op.rounds})</span></p>
              {op.holders.length > 0 && (
                <>
                  <h3>Who carries it</h3>
                  <ul className="bar-list">
                    {op.holders.map((h) => (
                      <li key={h.player}>
                        <span>{h.player}</span>
                        <ShareBar pct={h.share} tone="sky" />
                        <span className="num">{h.p}%</span>
                      </li>
                    ))}
                  </ul>
                  {op.transfer_pct > 0 && <p className="muted">It changes hands mid-round in {op.transfer_p}% of the rounds where it is seen.</p>}
                </>
              )}
              {op.areas.length > 0 ? (
                <>
                  <h3>Where it opens</h3>
                  <p className="muted">The area where the Operator spends most of the first 20 seconds, out of {op.opening_rounds} rounds.</p>
                  <ol className="area-list">
                    {op.areas.filter((a, i) => a.open_k > 0 || i < 3).slice(0, 6).map((a) => (
                      <li key={a.callout}>
                        <button type="button" aria-pressed={activeArea === a.callout} onClick={() => (activeArea === a.callout ? clearSelection() : selectArea(a))}>
                          <span className="area-name"><strong>{a.callout}</strong><span className="tag">{a.style}</span></span>
                          <span className="num">{a.open_k} of {a.open_n}</span>
                          <span className="tri" title="Share of sightings here by round time" aria-label={`Sightings by round time: ${a.window_share.map((w, i) => `${WINDOWS[i]} ${Math.round(w)}%`).join(', ')}`}>
                            {a.window_share.map((w, i) => <i key={i} data-on={opWindow === i} style={{ flexGrow: Math.max(w, 2) }}><b>{Math.round(w)}%</b></i>)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ol>
                  <p className="tri-key"><span>0–20s</span><span>20–40s</span><span>40s+</span></p>
                </>
              ) : (
                <p className="muted">Too few Operator rounds here to map where it is held.</p>
              )}
              {op.kills.total > 0 && (
                <>
                  <h3>Operator kills</h3>
                  <dl className="facts">
                    <dt>Kills</dt><dd className="num">{op.kills.total}</dd>
                    <dt>Opening picks</dt><dd className="num">{op.kills.opening} ({op.kills.opening_p}%)</dd>
                    <dt>Median kill time</dt><dd className="num">{op.kills.median_t !== null ? clock(op.kills.median_t) : 'none'}</dd>
                    <dt>Kills per Operator round</dt><dd className="num">{op.kills.per_op_round}</dd>
                  </dl>
                </>
              )}
            </>
          )}

          {mode === 'setup' && (
            <>
              <h2>Setups</h2>
              {side === 'attack' || !fp ? (
                <p className="lede">Setups describe how a team places traps and cams on defense. Switch to Defense to see them.</p>
              ) : fp.setups.length === 0 ? (
                <p className="lede">{team.name} did not repeat a trap or cam setup often enough here to show one.</p>
              ) : (
                <>
                  <p className="lede">Traps and cams standing when the round goes live, or placed in the first 20 seconds.</p>
                  <p className="figure"><span className="num">{fp.predictability}%</span><span>of placements land on a spot they reuse</span></p>
                  {fp.league && fp.league.length > 2 && fp.predictability !== null && (
                    <figure className="strip">
                      <div className="strip-track">
                        {fp.league.map((v, i) => <i key={i} style={{ left: `${v}%` }} />)}
                        <b style={{ left: `${fp.predictability}%` }} />
                      </div>
                      <figcaption><span>Varied</span><span>{fp.league.length} teams on {mapName}</span><span>Predictable</span></figcaption>
                    </figure>
                  )}
                  <h3>Most repeated setups</h3>
                  <ol className="setup-list">
                    {fp.setups.map((s, i) => (
                      <li key={i}>
                        <button type="button" aria-pressed={setupIdx === i}
                                onClick={() => { setSetupIdx(i); setEvidence({ title: `Setup: ${s.spots.map((x) => `${x.ability_name} at ${x.callout}`).join(' + ')}`, rounds: s.evidence }) }}>
                          <span className="num">{s.p}%</span>
                          <span>
                            <strong>{s.spots.map((x) => `${x.ability_name} at ${x.callout}`).join(' + ')}</strong>
                            <span className="muted">{s.k} of {s.n} {sideRounds}</span>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </>
              )}
            </>
          )}

          {mode === 'replay' && (
            <>
              <h2>{replay ? `Round ${replay.round}, ${cap(replay.map)}` : 'Round replay'}</h2>
              {replay && replayRef ? (
                <>
                  <p className="lede">
                    {team.name} {replayRef.side === 'defense' ? 'defending' : 'attacking'} against {replayRef.opponent}, {replay.date_label}.{' '}
                    {replayRef.won ? 'Won' : 'Lost'}: {replay.result}.
                  </p>
                  <ul className="key">
                    <li data-side="defender">Defenders</li>
                    <li data-side="attacker">Attackers</li>
                  </ul>
                  <h3>Round events</h3>
                  <ReplayFeed replay={replay} />
                  <p className="muted">To find it in the VOD: the round went live at {replayRef.live_utc} UTC.</p>
                </>
              ) : (
                <p className="lede">Pick a round from the evidence strip to watch it.</p>
              )}
            </>
          )}
        </aside>
      </main>

      <footer className="evidence" aria-label="Evidence">
        <div className="evidence-head">
          <h2>Evidence</h2>
          {evidence ? (
            <p><strong>{evidence.title}</strong> <span className="muted">{evRefs.length} {evRefs.length === 1 ? 'round' : 'rounds'}, newest first</span></p>
          ) : (
            <p className="muted">Select a finding or a marker to list the rounds behind it. Each round replays in 2D.</p>
          )}
          <p className="provenance">Official GRID data: {ds.series.toLocaleString()} series, {ds.rounds.toLocaleString()} rounds</p>
        </div>
        {evRefs.length > 0 && (
          <ol className="rounds">
            {evRefs.slice(0, 60).map((r) => (
              <li key={r.round}>
                <button type="button" className="round" aria-pressed={replayRef?.round === r.round} disabled={!canReplay(r)}
                        title={canReplay(r) ? 'Replay this round' : 'Every round replays in the local app; the hosted demo carries a few'}
                        onClick={() => openRound(r)}>
                  <span className="round-top">
                    {canReplay(r) && <Icon name="play" size={12} />}
                    <strong>Round {r.n}</strong> vs {r.opponent}
                    <b className={r.won ? 'won' : 'lost'}>{r.won ? 'Won' : 'Lost'}</b>
                  </span>
                  <span className="round-sub">{r.date_label}, map {r.game_number}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </footer>

      <HelpDialog open={helpOpen} onClose={() => setHelpOpen(false)} meta={meta} />
    </div>
  )
}
