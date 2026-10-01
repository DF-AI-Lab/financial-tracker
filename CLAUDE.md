# Financial Tracker

**Front page for this project. Read this first. Keep it short and current; update it at the end of every session.**
_Last updated: 1 Oct 2026._

## What it is
A personal tool (user only, no login) for one HSBC current account. The user drops monthly statement PDFs in a folder,
runs one command, and gets: bills, payday-to-payday cycles, what is Common / Random / One-off, and a "Latest pay?"
question that shows what is left after a typical month. Everything is Python 3 + pdfplumber + SQLite.
Older project (do not build on it): `python-finance-tracker` repo, see its `IDEA.md`.

## Read next
- `SPEC.md`: the agreed plan for the next build (steps 1-9). Map + tickets: GitHub issue #1 on this repo.
- `DECISIONS.md`: everything the user said yes to (rules, question-list behaviour, rent rule). Overrides anything else.
- `FUTURE_FEATURES.md`: what is built and what is planned.
- `README.md`: how to run on Windows.

## How it runs (user's PC, Windows)
`C:\ftvenv\Scripts\python.exe run.py` (also `run.py test`, `run.py fix`, `run.py folder "C:\path"`).
Real PDFs live in `...\Financial Tracker Project\statements` (next to the code folder). The database `tracker.db` lives
next to it. **Never commit PDFs or .db files** (.gitignore covers them). The user downloads the repo as a ZIP each time and
extracts it inside `Financial Tracker Project`; they are not a developer: give exact, copy-paste commands.

## Code map (`fintrack/`)
parse.py (PDF -> statements, column x positions from the header row) | checks.py (balance check) | dedupe.py |
cycles.py (payday cycles, wage = VERTU MOTORS PLC >= 500) | common.py (analyse: Common/Random/One-off, answers, rules) |
questions.py (the confirm-as-you-go list: `common 1 2`, `all`, `later`, `stop`, `fix`) | store.py (SQLite: statements,
payments, items, rules) | paydayrule.py (rent-by-transfer rule) | left.py (pay question) | settings.py (remembered folder).
`run.py` ties it together. Tests in `tests/` (fake data only; `tools/make_fake_*.py` build the fake PDFs).
Run tests: `.venv/bin/pytest -q` (create with `python3 -m venv .venv && .venv/bin/pip install pdfplumber reportlab pytest`).

## How we work (important)
- **The user has ADHD: short replies, plenty of spacing, emojis as signposts, one clear next step.** Tell them the score
  after every build round. Explain plainly; say which file/folder/command.
- **Tests first, then build.** Write failing tests from made-up data, commit, hand the build to a Haiku subagent
  (max 5 rounds, usually passes in 1), then **verify yourself**: run the full suite, check `git status` only touched the
  allowed files, try it on real data. Haiku has (a) claimed things that were not true and (b) added unrequested behaviour
  to satisfy a bad test: read the diff. If a test contradicts the documented rule, fix the test, not the code.
- Real statement layouts differ from fake ones: every real bug so far came from real PDFs (footer text glued on, small
  print read as payments, bank text in names). When the user shows an odd result, reproduce it in the fake PDFs first.
- Credits are limited: do not start loops unasked; nothing should run in the background.
- Push to branch `claude/stoic-archimedes-da95na` AND `main` (the user downloads `main`). Repo: DF-AI-Lab/financial-tracker
  (dash, not underscore; attach it with add_repo). Pull requests only if asked.

## Where we are (1 Oct 2026)
Built and tested (154 tests): reading + balance check, duplicates, cycles, common/random/one-off, database, question list,
pay question, payday transfer (rent) rule. Planning done with the wayfinder map (issue #1): `SPEC.md` holds every
decision. Mock-up of the home page: `prototype/home.html` (fake numbers). Nothing from `SPEC.md` is built yet.

## Next
1. Build `SPEC.md` step by step (tests first, Haiku builds, verify yourself, tell the user the score). Terminal first.
2. After each step the user runs it on their 18 months and reports anything odd; add a test for every real oddity.
3. Home page (step 9) last.
