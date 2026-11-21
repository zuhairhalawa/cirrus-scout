# Task 1: write the project guidelines

Explore this repository and write the guidelines you will follow on every later task, in `.junie/AGENTS.md`.

Read first: `README.md`, `docs/METHODOLOGY.md`, the `scout/` package, `tests/`, `web/src/`, `requirements.txt`, `.github/workflows/demo.yml` and `.gitignore`.

The guidelines must be specific to this codebase, not generic advice. Cover:

1. What the project is and how the pieces connect (extract, build, analysis, server, export, web).
2. The commands that actually work here: install, extract, build, serve, export, tests, web build. Check them against the code and the workflow file, do not guess.
3. Data rules. The GRID data is licensed for this hackathon only. It lives outside the repository and its extracts live in `derived/` and `web/public/data/`. None of it may be committed, copied into source files, pasted into documentation or printed in bulk. `scripts/check_no_data.py` guards commits.
4. The analysis conventions a change must respect: where percentages are rounded, how evidence strength is decided, the final-setup rule, which rounds and maps are excluded and why, and that every number shown must be recountable.
5. Testing: which tests need the built store and which run without data, and what a new feature is expected to add.
6. Front-end conventions you can see in `web/src/`.
7. What an agent must not do in this repository.

Constraints for this task:

- Create only `.junie/AGENTS.md`. Do not change any other file.
- Do not open or list the data repository beside this one, and do not read files inside `derived/` or `web/public/data/`.
- Do not run `git commit`, `git push` or any command that changes git history.
- Keep it under 150 lines. Plain sentences, no marketing language.
