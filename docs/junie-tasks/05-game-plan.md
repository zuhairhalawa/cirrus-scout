# Task 5: a game plan against a defense (analysis, payload, brief)

The hackathon brief asks tools to go beyond listing tendencies and suggest data-backed responses. Cirrus already tests one counter at a time: select a defensive spot and `counter_for_hotspot` in `scout/analysis.py` says whether attackers who put utility on it early won more, across every league round where a defense used that spot. A coach has to click every spot to find the ones that matter.

Build the summary: for a team's defense on a map, which of their setups are worth hitting early, which are better left alone, and which show no edge.

This task covers the analysis, the payload and the text brief. The app's interface is the next task; do not touch `web/`.

## What to build

### 1. `game_plan` in `scout/analysis.py`

```
game_plan(map_name: str, hot: dict) -> list[dict]
```

- `hot` is the result of `utility_hotspots` for a defense view (whole round, not a phase filter).
- Consider the spots whose `category` is "trap" or "sentinel" and whose `strength` is "strong" or "moderate". Those are the setups a team can be expected to repeat. Read how `export.py` picks the spots it precomputes counters for and stay consistent with it.
- For each, call `counter_for_hotspot(map_name, h["x"], h["y"], h["ability"])`.
- Classify each result into exactly one `advice` value:
  - `"hit"`: the counter has `enough` and its `signal` is "clear" or "some", and `delta` is positive.
  - `"leave"`: the counter has `enough` and its `signal` is "clear" or "some", and `delta` is negative.
  - `"no_edge"`: the counter has `enough` and its `signal` is "noise".
  - `"untested"`: the counter does not have `enough` (too few rounds in one arm), or it is `None`.
- Return one item per spot with: the spot's `id`, `ability_name`, `agent`, `callout`, `u`, `v`, `k`, `n`, `p`, `strength`; the `advice`; and a `counter` object holding the counter's own fields unchanged (`rounds`, `contested_rounds`, `uncontested_rounds`, `won_contested`, `won_uncontested`, `win_contested`, `win_uncontested`, `delta`, `z`, `signal`, `tools`, `contest_before`, `enough`), using `None` for fields the counter does not have.
- Order: "hit" first by `z` descending, then "leave" by `z` ascending, then "no_edge", then "untested"; inside the last two, most-used spot first.
- Do not invent any new statistic or threshold. The signal labels and the minimum arm size already exist; use them as they are. Do not round or recompute percentages.

`counter_for_hotspot` scans the league each time. Memoise it (the standard library can) so the same spot is not computed twice in one process, without changing what it returns.

### 2. Payload

In `scout()`, add a `"plan"` key: `game_plan(...)` for defense views, and an empty list for attack views. Always compute it from the whole-round hotspots (the `base` variable), like the findings. This is an added key; nothing existing may change.

### 3. Brief

Add a "Game plan" section to `scout/brief.py`, after "Key findings". Skip it when the plan is empty. One line per item, in the plan's order, written for a coach:

- hit: "Hit the Vyse Shear at C Main early: attackers won 53.8% (105 of 195) when they did, 47% (350 of 744) when they left it. Some signal."
- leave: the same numbers, worded so it is clear that hitting it early went with losing more often.
- no_edge: one line saying no reliable edge either way, with the round count.
- untested: collapse all of them into a single line listing the spots and saying too few league rounds to tell.

Add, for hit items, the utility most used on the spot (the counter's `tools`, at most three). End the section with one sentence that this is an association across the league, not proof of cause, which is how the app words it.

The example numbers above are real output already published in the README, and may be used in tests only as a hand-written payload.

## Tests

- Unit tests (no data) for the classification and the ordering, by calling the classifier with hand-written counter dictionaries. Structure the code so that this is possible: the classification of one counter result must be a small pure function.
- Unit tests for the brief section with a hand-written payload, covering each advice value and the empty plan.
- Data tests, skipped without the store like the others:
  - for one real defense view, every plan item's `counter` equals what `counter_for_hotspot` returns for that spot, and every `advice` follows the rules above;
  - attack views have an empty plan;
  - the existing keys of the payload are unchanged by this task (the existing data tests already cover their values; make sure they still pass).

Run `python -m pytest` before finishing and report the count.

## Also

- Add a "Game plan" paragraph to `docs/METHODOLOGY.md`, next to the counter definition, stating the four advice values and their exact conditions.
- Update the brief example in `README.md` (invented names and numbers).
- Update the test count where the documentation states it.

## Constraints

- Follow `.junie/AGENTS.md`.
- Do not touch `web/`, `scout/server.py` or `scout/export.py`.
- Do not read the data folders or `derived/` directly; use the Python API. Do not paste real output into any file, except the one example sentence above.
- Do not run `git commit`, `git push` or any command that changes git history.
