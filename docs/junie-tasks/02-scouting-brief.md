# Task 2: a scouting brief a coach can paste into a prep document

Coaches share prep notes as text in chat and in documents. The app shows its findings on a map, but there is no way to take them away as text. Add one.

## What to build

A new module `scout/brief.py` and a new command:

```
python -m scout brief --team MIBR --map icebox --side defense [--period recent|all] [--out brief.md]
```

It prints (or writes with `--out`) a Markdown brief for that team, map and side.

The brief is built from the same payload the app uses. `scout.server.scout_payload(team, map, side, since, phase)` returns it; read `scout/server.py` and `scout/analysis.py` (`scout`, `insights`, `utility_hotspots`, `operator_profile`, `setup_fingerprint`, `sample_info`) to learn its exact shape before writing anything. Do not recompute any statistic in the new module: every number in the brief must be read from the payload, so the brief can never disagree with the app.

Split the work in two functions so it can be tested without data:

- `render_brief(payload: dict) -> str` is pure. It takes a payload dictionary and returns Markdown.
- `build_brief(team, map_name, side, period) -> str` resolves the team (accept a team name, case-insensitive, or a team id), works out the `since` value the way the server does for the "recent" period, fetches the payload and calls `render_brief`.

## What the brief contains

In this order, skipping any section the payload has nothing for:

1. Title line: team, map, side, period and the sample (rounds, maps, date range), all taken from the payload.
2. Key findings: one bullet per finding, with its count as "k of n" and its evidence strength in words. Thin evidence must be labelled as thin, never dropped silently and never presented like a strong finding.
3. Utility: the repeated spots, most used first, each with ability, agent, callout, "k of n rounds", who places it and when.
4. Operator: buy rate, primary holder, opening areas with counts, timing profile.
5. Setup: the recurring setup and the predictability figure, if present.
6. A final line saying how the numbers are defined, pointing to `docs/METHODOLOGY.md`.

Write it the way a coach would write a note to players: short lines, callout names, no statistics jargon beyond "k of n rounds".

## Rules

- Percentages come from the payload fields that already hold them. Do not divide and round again; the project rounds percentages in exactly one place (`pct_int` in `scout/analysis.py`).
- No new dependencies.
- Unknown team, map or side must end with a clear one-line error listing the valid choices, not a traceback.
- Follow `.junie/AGENTS.md`.

## Tests

Add `tests/test_brief.py`:

- Unit tests for `render_brief` using a small hand-written payload in the test file (invented team and player names, invented numbers, so no licensed data is copied into the repository). Cover: a normal payload, a payload with no Operator rounds, a payload with only thin findings, and that every "k of n" in the output matches the payload.
- One test that needs the built store, marked and skipped the same way the existing data tests are skipped when the store is missing: build the brief for a real view and check that every count in its Key findings section equals the corresponding finding in `scout_payload` for the same view.

Run `python -m pytest` and make sure the whole suite passes before you finish.

## Also

- Add the command to the docstring and parser in `scout/__main__.py`.
- Add a short "Scouting brief" section to `README.md` with the command and a three or four line example of the output using invented names and numbers.

## Constraints

- Do not open or list the data repository beside this one. Do not read the files inside `derived/` or `web/public/data/` directly; use the Python API.
- Do not paste real output from the data into any file you write.
- Do not change the analysis numbers, the server API, or the front end.
- Do not run `git commit`, `git push` or any command that changes git history.
