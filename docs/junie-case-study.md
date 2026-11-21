# Working with Junie on Cirrus: a short case study

Cirrus is a VALORANT scouting tool built on the official GRID data. This is an account of how Junie, JetBrains' coding agent, was used on it, including the part where it got something wrong and how that was caught.

## The setup

Junie ran through the Junie CLI, in headless mode, from the project folder. Each task was a Markdown brief in [docs/junie-tasks](junie-tasks), and Junie was told to read the brief and carry it out. The briefs are in the repository exactly as Junie received them.

| Task | Junie's run time | Result |
|---|---|---|
| 1. Write the project guidelines | 79 s | [.junie/AGENTS.md](../.junie/AGENTS.md), 74 lines |
| 2. Build the scouting brief | 158 s | `scout/brief.py`, a new command, 9 tests |
| 3. Fix seven review findings | 160 s | 17 tests, brief now matches the app |
| 4. Fix three more findings | 109 s | 20 tests in `tests/test_brief.py` |

The whole test suite went from 38 to 58 tests.

## What worked

**Guidelines before features.** The first task asked Junie to read the codebase and write the rules it would follow: how the pipeline fits together, which commands really work, that the licensed data must never be committed or pasted into a file, and the analysis conventions, such as the single function that turns a share into a percentage. Every claim in the file was checked against the code afterwards and held. Junie then loaded it on every later task, and it showed: the feature it wrote used the existing helpers, added no dependencies and put its tests where the others live.

**A brief with one hard rule.** The feature task said: read every number from the payload the app already uses and recompute nothing. That rule made the result checkable, because the brief and the app could be compared number by number.

## What went wrong

Junie's first version passed all of its own tests. Run on a real view, it reported 23 rounds for a team where the app reports 84. The brief had said "work out the period the way the server does". That logic lives in the web client, not on the server, and Junie filled the gap with a 30-day window and fallbacks of its own. Nothing in its tests could notice, since they were written from the same misunderstanding.

The same check on real views found six more problems, for example a utility section 70 lines long and an Operator section that mislabelled one count as another. They became [task 3](junie-tasks/03-brief-review.md). Junie fixed all seven, and over-corrected one: the findings lost their sample size ("45 of defense rounds"). That and two smaller points became [task 4](junie-tasks/04-brief-second-review.md).

## What it taught

- **Point the agent at the exact source.** "The way the server does" was a wrong pointer, and Junie filled the gap with a plausible guess. Task 3 named the function and the file, and the fix was right the first time.
- **Passing tests are not a review.** An agent's tests encode the agent's understanding. The check that mattered came from outside: real views compared against the app's own payload after each task.
- **Ask for the test that would have caught it.** Tasks 3 and 4 asked for the missing tests as well as the fix, so the suite now compares the brief's counts with the app's.
- **Keep the briefs.** Because every task is a file, the review rounds are part of the repository's history instead of a chat that is gone.

After task 4, a last pass by hand changed wording only. Junie joined after the pipeline, the analysis and the web app were in place; the guidelines and the scouting brief are its work, and the four task files are the complete record of it.
