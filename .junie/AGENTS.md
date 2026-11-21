# Cirrus — Agent Guidelines

## 1. What the project is

Cirrus turns official GRID VALORANT match feeds into opponent scouting for Cloud9 coaches.
Pipeline: `extract.py` (stream GRID .jsonl.zst files) → `build.py` (columnar store + vector floor plans)
→ `analysis.py` (spots, Operator profile, setups, counters, findings) → `server.py` (JSON API)
→ `web/` (React + TypeScript SPA with SVG map and 2D replay).
`export.py` writes an aggregate-only static version for the hosted demo.

## 2. Commands

- **Install:** `pip install -r requirements.txt` then `cd web && npm install && npm run build && cd ..`
- **Extract + build:** `python -m scout all` (or `extract` then `build` separately)
- **Serve locally:** `python -m scout serve` (port 8765)
- **Export demo data:** `python -m scout export` → writes to `web/public/data/`
- **Web dev mode:** `cd web && npm run dev` (proxies `/api` to Python server)
- **Web production build:** `cd web && npm run build` → `web/dist/`
- **Tests:** `python -m pytest` (58 tests; unit tests run anywhere, data tests need the built store)
- **CI workflow:** `.github/workflows/demo.yml` — fetches data, runs unit tests, extracts, builds, runs all tests, exports, builds web, deploys to GitHub Pages.

## 3. Data rules

GRID data is licensed for the hackathon only. It lives outside the repository in `../stl-hackathon-2026-grid-starter/`
(configurable via `STL_DATA_DIR`). Extracts live in `derived/` and `web/public/data/`.
None of it may be committed, copied into source files, pasted into documentation, or printed in bulk.
`.gitignore` excludes `derived/`, `web/public/data/`, and all `.zst`/`.jsonl` files.
`scripts/check_no_data.py` guards commits — install with `python scripts/check_no_data.py --install`.
Never open or list files inside `derived/` or `web/public/data/`.

## 4. Analysis conventions

- **Percentages:** `pct_int(k, n)` in `scout/analysis.py` is the single place a share becomes a whole percentage.
  Every screen must use it so the headline, map marker, and list row always agree.
- **Evidence strength:** `strength(k, n)` uses a Wilson interval (z=1.64). Strong: 15+ rounds, lower bound ≥ 40%.
  Moderate: 8+ rounds, lower bound ≥ 20%. Thin: anything else.
- **Final-setup rule:** For recallable devices (Trapwire, Spycam, Turret, etc.), only a player's last placement
  in the buy phase counts, up to the charge count. Superseded casts are marked via the `final` column.
- **Excluded rounds:** One map is dropped (score gate — rebuilt rounds don't match official score).
  Three rounds are dropped (outcome gate — result contradicts sides). `round_ok` mask enforces this.
- **Excluded maps and sides:** Setups are only computed for defense (`side == 1`).
  On attack, the buy phase is spent in spawn, so only utility used once the round is live is shown.
- **Recountability:** Every number must be recountable from the store. Spot shares are defined on the cluster
  centre (4.5 m radius), not on membership. Evidence rounds are listed for every finding.

## 5. Testing

- `tests/test_units.py` — pure helper tests (cluster, Wilson, strength, pct_int, formatting, floor plan).
  Run without data: `python -m pytest tests/test_units.py`.
- `tests/test_data_integrity.py` — needs the built store and GRID data. Checks: official scores, outcome gates,
  ability catalogue, callout alignment, hotspot recounts, percentage consistency, Operator possession,
  counter arms, and a raw-file recount.
- `tests/test_subtitles.py` — checks demo video captions match narration.
- A new feature should add unit tests for any pure helper and, where feasible, a data-integrity check
  that recounts the new number independently.

## 6. Front-end conventions (web/src/)

- React + TypeScript, Vite. Entry: `main.tsx` → `App.tsx`.
- Components in `components/`: `MapView.tsx` (SVG map), `ReplayPlayer.tsx` (2D replay), `ui.tsx` (shared primitives).
- Types in `types.ts`. API calls in `api.ts`.
- Hash-based routing (`#team=...&map=...&side=...`). State is stored in React state + localStorage for theme.
- No external UI library — all styling is custom CSS. Icons are inline SVGs.
- The app reads from `/api` endpoints served by `scout/server.py`. In dev mode, Vite proxies to port 8765.

## 7. What an agent must not do

- Never commit, copy, or print GRID data or its extracts.
- Never run `git commit`, `git push`, or any command that changes git history.
- Never modify files in `derived/` or `web/public/data/`.
- Never introduce external UI libraries or change the build system (Vite, npm, pip).
- Never bypass the `pct_int()` function for percentage display or the `strength()` function for evidence labels.
- Never add data to the repository, even as test fixtures. Use the existing `_store()` helper in test_units.py
  for small synthetic cast tables instead.
