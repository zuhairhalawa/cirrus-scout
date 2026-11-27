# Working with Junie on Cirrus: a short case study

**The one-minute version, as a video:** [Its tests passed. It was still wrong.](https://youtube.com/shorts/m51nOFzyjGg)

Cirrus is a VALORANT scouting tool built on the official GRID data. This is an account of how Junie, JetBrains' coding agent, was used on it, including the part where it got something wrong and how that was caught.

## The setup

For tasks 1 to 6 Junie ran through the Junie CLI, in headless mode, from the project folder. Task 7 ran in JetBrains Air. Each task was a Markdown brief in [docs/junie-tasks](junie-tasks), and Junie was told to read the brief and carry it out. The briefs are in the repository exactly as Junie received them.

| Task | Junie's run time | Result |
|---|---|---|
| 1. Write the project guidelines | 79 s | [.junie/AGENTS.md](../.junie/AGENTS.md), 74 lines |
| 2. Build the scouting brief | 158 s | `scout/brief.py`, a new command, 9 tests |
| 3. Fix seven review findings | 160 s | 17 tests, brief now matches the app |
| 4. Fix three more findings | 109 s | 20 tests in `tests/test_brief.py` |
| 5. Build the game plan (analysis, payload, brief) | 303 s | `game_plan` and 22 tests |
| 6. Fix six findings, then add it to the web app | 266 s | types, section, styles, help entry |
| 7. Other tracked weapons (in JetBrains Air) | about 10 minutes, with approvals | summary, payload key, brief lines, Operator tab list, 12 tests |

The whole test suite went from 38 to 97 tests.

## What worked

**Guidelines before features.** The first task asked Junie to read the codebase and write the rules it would follow: how the pipeline fits together, which commands really work, that the licensed data must never be committed or pasted into a file, and the analysis conventions, such as the single function that turns a share into a percentage. Every claim in the file was checked against the code afterwards and held. Junie then loaded it on every later task, and it showed: the feature it wrote used the existing helpers, added no dependencies and put its tests where the others live.

**A brief with one hard rule.** The feature task said: read every number from the payload the app already uses and recompute nothing. That rule made the result checkable, because the brief and the app could be compared number by number.

## What went wrong

Junie's first version passed all of its own tests. Run on a real view, it reported 23 rounds for a team where the app reports 84. The brief had said "work out the period the way the server does". That logic lives in the web client, not on the server, and Junie filled the gap with a 30-day window and fallbacks of its own. Nothing in its tests could notice, since they were written from the same misunderstanding.

The same check on real views found six more problems, for example a utility section 70 lines long and an Operator section that mislabelled one count as another. They became [task 3](junie-tasks/03-brief-review.md). Junie fixed all seven, and over-corrected one: the findings lost their sample size ("45 of defense rounds"). That and two smaller points became [task 4](junie-tasks/04-brief-second-review.md).

## The second feature

Tasks 5 and 6 added the game plan: for a team's defense, which of their setups are worth hitting early, judged by every league round where a defense used that spot. The brief for task 5 applied the lessons above. It named the function to build on, gave the four outcomes and their exact conditions, forbade new thresholds, and asked for the classification to be a small pure function so it could be tested without data.

This time the analysis was right on the first run. A separate script re-derived every advice value from the counter on six real views and all of them matched. What the review found was presentation: the section in the wrong place, two lines a coach could not tell apart, tools listed without their agents, and a cache that handed the same dictionary to every caller. Task 6 fixed those and built the interface.

The interface was the weaker half. Junie reused the existing selection handler as asked, so clicking a row focuses the map and opens the existing counter panel, and the build passed. But it cannot see the page: the rows came out with an upper-case badge and their own box, unlike anything else in the app. Screenshots on desktop, phone and dark mode showed that at once, and the rows were restyled by hand to reuse the finding-row pattern.

## The third feature, in Air

Task 7 added the other tracked weapons: the Outlaw, Marshal and Odin next to the Operator. It ran in JetBrains Air instead of the CLI, in the mode where the agent asks before every command. That changed the work. Each command was read before it ran, so the plan was visible step by step: read the brief and the guidelines, measure one view before touching anything, write the summary as a small pure function over the existing Operator profile, test, build, then update the documents.

One approval was refused. Junie wanted to build its test environment on a Python version that cannot install the pinned numpy, and said so itself; it was told which interpreter to use and carried on. Everything else was approved as proposed.

The result needed no review round. A separate script compared 51 summary rows on five teams with the Operator code and all matched, the full suite passed, and the list in the Operator tab reused existing styles, so it looked like the rest of the app. The brief was the reason: it named the function to build on, forbade new numbers, and asked for the cost to be measured (about 12 ms per view).

## What it taught

- **Point the agent at the exact source.** "The way the server does" was a wrong pointer, and Junie filled the gap with a plausible guess. Task 3 named the function and the file, and the fix was right the first time.
- **Passing tests are not a review.** An agent's tests encode the agent's understanding. The check that mattered came from outside: real views compared against the app's own payload after each task.
- **Ask for the test that would have caught it.** Tasks 3 and 4 asked for the missing tests as well as the fix, so the suite now compares the brief's counts with the app's.
- **Look at what it cannot see.** A passing build says nothing about how a screen reads. Visual work needs a person looking at screenshots, however precise the brief.
- **Keep the briefs.** Because every task is a file, the review rounds are part of the repository's history instead of a chat that is gone.

By hand: wording after task 4, the row styling after task 6, and a three-line change to the export. Nothing in task 7 was changed by hand. Junie joined after the pipeline, the analysis and the web app were in place; the guidelines, the scouting brief, the game plan and the other-weapons summary are its work, and the seven task files are the complete record of it.
