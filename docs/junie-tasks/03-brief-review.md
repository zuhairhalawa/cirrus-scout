# Task 3: review findings on the scouting brief

The brief from task 2 runs and its tests pass, but trying it on real views showed the problems below. Fix all of them, in `scout/brief.py`, `tests/test_brief.py` and the README section.

## 1. The brief disagrees with the app (must fix)

`--period recent` uses a 30-day window per team, map and side, with fallbacks. The app's "Last 6 months" is 183 days counted back from the team's most recent match in the data: see `sinceFor` in `web/src/App.tsx` and the `last_played` field of the rows from `teams_index` in `scout/analysis.py`. For the same team, map and side the brief reported 23 rounds where the app reports 84.

- Compute `since` exactly as the app does. Remove the fallback heuristics.
- Say the period in the title block in the app's words: "Last 6 months" or "All matches".
- Add a test that the `since` used for a team equals 183 days before its `last_played`, and make the data test compare the brief with `scout_payload` called with that same `since`.

## 2. Wording bug in Key findings

Bullets read "11 of 23 of defense rounds". The finding's `unit` already starts with "of". Use the fields so the sentence reads "11 of 23 defense rounds".

## 3. Key findings must state the evidence strength for every finding

Only thin findings are labelled. State it for each one in words: strong, moderate or thin evidence.

## 4. The Utility section lists everything

One real view produced 70 bullets, most of them spots seen in 3 or 4 rounds. A coach will not read that.

- List the spots whose `strength` is strong or moderate, most used first, at most 12.
- Then one line saying how many less frequent spots were left out.
- If no spot is strong or moderate, list the top 5 and label them as thin evidence.
- Add the abilities in `utility.global` (smokes placed from the tactical map, which have no position to report) as one line each: ability, agent, "k of n rounds".

## 5. Operator section

- `operator.rounds` is the number of rounds in the sample, not Operator rounds, so the section currently appears even when no Operator was bought. When `buy_rounds` is 0, write a single line that no Operator was bought in n rounds. That is useful to a coach, so do not hide it.
- The opening-area fallback prints an area's `k` and `n` labelled as Operator rounds. Those fields count something else (rounds with a sighting there). Remove the fallback: list only areas with `open_k` above 0, ordered by `open_k`, and include each area's `style`.
- Replace "median kill" with what the payload says about opening picks (`operator.kills`: `opening` of `total`).
- Say how many Operator rounds the primary holder had, not only the percentage.

## 6. Setup section

Name the agent with each ability in the recurring setup, and use the wording of the app for the predictability figure (read how `predictability` is computed in `setup_fingerprint` and describe exactly that).

## 7. Command line

- On Windows the dash characters in the output printed as replacement characters. Make the command write UTF-8 to standard output, and keep `--out` writing UTF-8.
- For an unknown team, suggest the closest names first (the standard library can do this), then say how to list all of them, instead of printing every team.
- The last line links to `docs/METHODOLOGY.md` as a relative Markdown link, which breaks once the brief is pasted somewhere else. Name the file in plain text.

## Checks before you finish

- `python -m pytest` passes.
- Run the command yourself for one team on one map, for both periods, and confirm the round count in the title equals `sample.rounds` of `scout_payload` for the same `since`. Do not paste the output into any file.
- Update the README example (invented names and numbers) so it matches the new format.

Same constraints as before: no reading of the data folders, no real output pasted into files, no changes to analysis numbers, the server API or the front end, no git commands that change history.
