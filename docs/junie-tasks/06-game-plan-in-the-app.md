# Task 6: review of the game plan, then show it in the app

## Part A: review findings on task 5

An independent check re-derived every advice value from the counter on six real defense views and all of them matched, and the plan holds exactly the eligible spots in the right order. The analysis is right. These points are not:

1. **Section order in the brief.** The task asked for "Game plan" directly after "Key findings". It is after "Operator".
2. **A coach cannot tell two lines apart.** One view printed "Vyse Razorvine at C Site: no reliable edge either way" twice, for two different spots with the same callout. Every line must also say how often the team sets that spot, from the item's own `k` and `n` (for example "set in 71 of 157 rounds"). That also tells the coach how much the line matters.
3. **Tools without agents.** "Common tools: Prowler, Paint Shells, Boom Bot" drops the agent. Write "Fade Prowler, Raze Paint Shells, Raze Boom Bot", as the app does.
4. **The closing sentence is glued to the list.** There is no blank line before it, so Markdown renders it as part of the last bullet.
5. **Large numbers.** Round counts above 999 need a thousands separator, as in the app ("1,098 league rounds").
6. **Code.** In `scout/analysis.py`:
   - The memoised function hands the same dictionary object to every caller. Any caller that changes it would corrupt the cache for everyone. Return a copy from the public function (including the `tools` list), and add a unit test that proves a caller cannot change what the next caller sees.
   - `counter_for_hotspot_uncached` is public but exists only for the cache. Make it private.
   - `game_plan` writes the list of counter field names out twice. Name the fields once and build the object from that.

Fix all six and update the tests that encode the old wording or order.

## Part B: the game plan in the app

Show the plan in the web app. Read `web/src/App.tsx`, `web/src/types.ts`, `web/src/api.ts`, `web/src/components/ui.tsx` and `web/src/styles.css` first, and follow what is there.

### Data

Add the plan to the TypeScript types (`Scout.plan`, a `PlanItem` type that mirrors the payload exactly). The payload already carries it in both live and static modes; `api.ts` should need no new request.

### Where and what

In the findings column, between "Key findings" and "Recent maps", add a "Game plan" section. It appears only on defense views that have a plan.

- **Hit and leave items** are rows a coach can act on. Each row shows, in this order of importance: the instruction ("Hit early" or "Leave alone"), the spot ("Vyse Shear at C Main"), the size of the edge in points of attack win rate with its sign (the counter's `delta`), and the signal in words ("Clear signal" or "Some signal"). A second line gives the plain numbers the way the existing counter block words them: won X% (a of b) when hit early, Y% (c of d) when left. Clicking a row selects that spot exactly as clicking it in the utility list does, so the map focuses on it and the existing counter panel opens. Find the existing handler and reuse it; do not write a second selection path. If the app is on another tab, switch to Utility first, the way findings already do.
- **No-edge and untested items** are not rows. Summarise each group in one sentence that names the spots: "No reliable edge either way: Razorvine at C Site, Shear at B Site." and "Too few league rounds to tell: Turret at Mid Boiler."
- **When nothing is a hit or a leave**, say so plainly as the first line of the section ("No setup here has a reliable edge from being hit early.") and still show the two summary sentences. Do not hide the section: knowing there is no free counter is useful.
- End the section with the existing caveat wording: an association across the league, not proof of cause.

### How it must look

- Reuse the existing tokens, type sizes and row patterns in `styles.css` (the finding rows and the counter block are the closest relatives). No new colours, no new fonts, no icons library, no cards with shadows. The existing "up" and "down" colours of the counter figure are the only colour that carries meaning here.
- The row is a real `<button>` with a visible keyboard focus, like the finding rows.
- It must hold at phone width (the existing breakpoints are in `styles.css`), in the dark theme, and in the printed brief (`@media print`), where rows print as plain text.
- Numbers use the same number styling class the rest of the app uses.

### Help

Add one sentence to the existing help dialog explaining what the game plan is and that it is tested across the league.

### Checks

- `cd web && npm run build` must pass with no TypeScript errors.
- `python -m pytest` must pass. Report the count.
- Add nothing to `web/public/`.

## Constraints

- Follow `.junie/AGENTS.md`.
- Do not change the analysis numbers, `scout/server.py` or `scout/export.py`.
- Do not read the data folders or `derived/` directly. Do not paste real output into any file.
- Do not run `git commit`, `git push` or any command that changes git history.
