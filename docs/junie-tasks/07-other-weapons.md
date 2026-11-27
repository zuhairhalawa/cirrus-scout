# Task 7: the other tracked weapons (run in JetBrains Air)

The hackathon brief asks for a profiler of "high-impact weapons like the Operator (or the Odin)". Cirrus tracks four weapons through buys, drops, pickups and deaths (`TRACKED_WEAPONS` in `scout/config.py`: Operator, Outlaw, Marshal, Odin), and `operator_profile` in `scout/analysis.py` already accepts a `weapon` argument. The app only ever asks for the Operator. A coach cannot see that a team buys an Odin on a map every other round.

Show the other weapons, compactly. This is a summary, not three more copies of the Operator tab.

## What to build

### 1. `weapon_summary` in `scout/analysis.py`

```
weapon_summary(team, map_name, side, *, events=None, since=None) -> list[dict]
```

- For each tracked weapon other than the Operator, call `operator_profile(..., weapon=w)` and keep a small summary: `weapon`, `rounds`, `buy_rounds`, `buy_p`, `held_rounds`, the primary holder (`player`, `rounds`, `p`, or `None`), and the top opening area (`callout`, `open_k`, `open_n`, `open_p`, `u`, `v`, or `None` when no area has `open_k` above 0).
- Add a `strength` for the buy rate, from the existing `strength(buy_rounds, rounds)`.
- Keep only weapons with at least one buy round. Order by `buy_rounds`, most first.
- Read every number from the profile. Do not recompute a percentage, do not add a threshold, do not change `operator_profile`.

### 2. Payload

Add a `"weapons"` key to the result of `scout()`, for both sides. It is an added key; nothing existing may change. Mind the cost: this runs `operator_profile` three more times per view, so measure one view before and after and report the times. If it is more than a few hundred milliseconds slower, say so and propose how to avoid it; do not silently accept it.

### 3. Brief

In `scout/brief.py`, add the other weapons to the "Operator" section as extra lines, one per weapon: bought in k of n rounds, mostly by whom, and where it opens. Rename nothing. When the list is empty, add nothing.

### 4. The app

In the Operator tab's side panel, below the existing Operator content, add a short "Other tracked weapons" list from `scout.weapons`: one line per weapon with its name, "k of n rounds", the holder and the opening area. Reuse the row and number styles already in `web/src/styles.css`; no new colours, no upper-case labels, no boxes or badges, and it must hold at phone width and in the dark theme. When the list is empty, show one muted line saying none of the other tracked weapons was bought here. Add the type to `web/src/types.ts`.

### 5. Documentation

Add a short paragraph to the Operator section of `docs/METHODOLOGY.md` and one bullet under "What a coach gets" in `README.md`. Update the test count where the documentation states it.

## Tests

- Unit tests with hand-written profiles for the summary's selection and ordering. Make the part that turns one profile into one summary row a small pure function so this needs no data.
- Unit tests for the new brief lines, including the empty list.
- Data tests, skipped without the store like the others: for one real view, every summary row equals the corresponding fields of `operator_profile(..., weapon=w)`; the existing payload keys are unchanged.

## Checks before you finish

- `python -m pytest` passes. Report the count.
- `cd web && npm run build` passes with no TypeScript errors.

## Constraints

- Follow `.junie/AGENTS.md`.
- Do not change `scout/server.py`, `scout/export.py` or any existing number.
- Do not read the data folders or `derived/` directly; use the Python API. Do not paste real output into any file.
- Do not run `git commit`, `git push` or any command that changes git history.
