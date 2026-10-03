# Financial Tracker

**Front page for this project. Read this first. Keep it short and current; update it at the end of every session.**
_Last updated: 3 Oct 2026._

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
Built and tested (255 tests): reading + balance check, duplicates, cycles, common/random/one-off, database, question list,
pay question, payday transfer (rent) rule, and from `SPEC.md`: **step 1** (same bill: DDs ignore the reference, one-off
"Same bill? y/n" for similar SO/BP references, Enter = no) and **step 2** (categories: guessed from keywords in
`fintrack/categories.py`, `cat 1 Car` in the question list and in `fix`) and **step 3** (yearly bills: `yearly 3`, left out like one-offs, WARNING line 11-13 months after the last payment) and **step 5** (spending by category: `fintrack/bycategory.py`, table after the picture, `run.py cat 2` opens one; "now" = the newest cycle so far) and **step 6** (`fintrack/spare.py`: LAST CYCLE expected vs actual + missing, and the pay question now shows
left over + wage - bills (last month's) - normal = expected spare; replaces format_left) and **step 4** (six-month picture printed by run.py: `fintrack/picture.py`; analyse gives each common item "last" and "type"). Planning map: GitHub issue #1.
Mock-up of the home page: `prototype/home.html`. **2 Oct: user ran steps 1-4 on all 18 months: works.** Rent 562.50
(rule 570 accepted; fixed: small payday top-ups hid the rent), IVA (BENNETT JONES, finished) marked one-off + cat Debt,
left after typical month 416.71 on 2,677. The user's code folder is still named `...stoic-archimedes...` (it holds main).

## Next
1. Build `SPEC.md` step by step from step 7 (3 Oct: steps 5-6 checked on real data; last cycle missing only 7.34,
expected spare 292.74 on 2,677) (tests first, Haiku builds, verify yourself, tell the user the score). Terminal first.
2. Small fixes from real use: PAYDAY TRANSFERS prompt saves any typed sentence as a label and Enter = yes (ask to
   confirm long labels); `fix` list hides guessed categories (show them); a "finished" kind for ended bills (IVA) instead
   of one-off; HPI INSTANT INK (11 x 2.99) suggested Random, check why.
3. After each step the user runs it on their 18 months and reports anything odd; add a test for every real oddity.
4. Home page (step 9) last.
