# Financial Tracker

**Front page for this project. Read this first. Keep it short and current; update it at the end of every session.**
_Last updated: 4 Oct 2026._

## What it is
A personal tool (user only, no login) for one HSBC current account. The user drops monthly statement PDFs in a folder,
runs one command, and gets: bills, payday-to-payday cycles, what is Common / Random / One-off, and a "Latest pay?"
question that shows what is left after a typical month. Everything is Python 3 + pdfplumber + SQLite.
Older project (do not build on it): `python-finance-tracker` repo, see its `IDEA.md`.

## Read next
- `SPEC.md`: the agreed plan for the next build (steps 1-9). Map + tickets: GitHub issue #1 on this repo.
- `DECISIONS.md`: everything the user said yes to (rules, question-list behaviour, rent rule). Overrides anything else.
- `FUTURE_FEATURES.md`: what is built and what is planned.
- `README.md`: how to run on Windows. `PHONE_SETUP.md`: the phone copy setup, step by step.

## How it runs (user's PC, Windows)
`C:\ftvenv\Scripts\python.exe run.py` (also `run.py test`, `run.py fix`, `run.py folder "C:\path"`, `cat N`, `show N`,
`add 12.50 Costa`, `spends`, `remove N`). In PowerShell always put `C:\ftvenv\Scripts\python.exe` in front.
Real PDFs live in `...\Financial Tracker Project\statements` (next to the code folder). The database `tracker.db` lives
next to it. **Never commit PDFs or .db files** (.gitignore covers them). The user downloads the repo as a ZIP each time and
extracts it inside `Financial Tracker Project`; they are not a developer: give exact, copy-paste commands.

## Code map (`fintrack/`)
parse.py (PDF -> statements, column x positions from the header row) | checks.py (balance check) | dedupe.py |
cycles.py (payday cycles, wage = VERTU MOTORS PLC >= 500, plus names added with `run.py wage NAME`: wages.py, kv table) | common.py (analyse: Common/Random/One-off, answers, rules) |
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
Built and tested (365 tests): reading + balance check, duplicates, cycles, common/random/one-off, database, question list,
pay question, payday transfer (rent) rule, and from `SPEC.md`: **step 1** (same bill: DDs ignore the reference, one-off
"Same bill? y/n" for similar SO/BP references, Enter = no) and **step 2** (categories: guessed from keywords in
`fintrack/categories.py`, `cat 1 Car` in the question list and in `fix`) and **step 3** (yearly bills: `yearly 3`, left out like one-offs, WARNING line 11-13 months after the last payment) and **step 5** (spending by category: `fintrack/bycategory.py`, table after the picture, `run.py cat 2` opens one; "now" = the newest cycle so far) and **step 6** (`fintrack/spare.py`: LAST CYCLE expected vs actual + missing, and the pay question now shows
left over + wage - bills (last month's) - normal = expected spare; replaces format_left) and **step 7** (`fintrack/where.py`: WHERE DID THE X GO? / EXTRA X COME FROM?, reasons add up exactly,
`run.py show 2`; analyse keeps common_txns/random_txns) and **step 8** (`fintrack/typed.py`: `run.py add 12.50 Costa`, `run.py spends`, `run.py remove 1`; left now =
left over + pay (last typed, kv table) - bills - typed; typed spends auto-matched to the statement, unmatched asked) and **step 9** (home page: `web.py` Flask on 127.0.0.1:5000, `start.bat` double-click, `templates/home.html`
(written by hand, not Haiku), data from `fintrack/home.py` home_data; pay box, add/remove spend; one-time
`C:\ftvenv\Scripts\python.exe -m pip install flask`) and **step 4** (six-month picture printed by run.py: `fintrack/picture.py`; analyse gives each common item "last" and "type"). Planning map: GitHub issue #1.
Mock-up of the home page: `prototype/home.html`. **2 Oct: user ran steps 1-4 on all 18 months: works.** Rent 562.50
(rule 570 accepted; fixed: small payday top-ups hid the rent), IVA (BENNETT JONES, finished) marked one-off + cat Debt,
left after typical month 416.71 on 2,677. The user's code folder is still named `...stoic-archimedes...` (it holds main).

## Next
00. **4 Oct (grill session): step 10 phone copy BUILT (391 tests)** on PythonAnywhere instead of the AWS v3 design (the user
   chose it in the grill and drew the diagram: PC -> JSON/page -> PythonAnywhere <-> phone; phone changes go back to the PC,
   which asks y/n). See SPEC.md step 10 + DECISIONS.md 4 Oct. Code: `cloud/flask_app.py` (the site: page.html,
   changes.json, first key kept, PIN hash, 5 tries = 15 min lock), `fintrack/phone.py` (PC side: connect/pin/upload/
   fetch/apply, key in ~/.financial_tracker_phone_key.txt so test + real DBs share it), `web.phone_page` (home.html with
   phone=True: PC-only cards/script hidden, spends done by a small script + localStorage, Send button), `web.push` after
   every change, `/phone` box on the PC page, run.py asks at start (Enter = all) and pushes at the end, `run.py phone URL`,
   `run.py pin N`. Built by me, not Haiku. Tried in Chromium at phone width against a local copy of the site.
   4 Oct LIVE: https://darrenfawcett2448.pythonanywhere.com (Python 3.13), real data on the phone, phone spend reached
   the PC prompt. Real DB found only after making an (empty) `Financial Tracker Project\statements` folder.
   Known snags: fake PDFs are paid by ACME so `run.py test` gives "No paydays" on the phone (PHONE_SETUP Part 2 is
   misleading: skip to Part 3); `run.py wage NAME test` would save "NAME test". User told to run setup.bat in the new
   folder so shortcuts point at it, and to use the PC home page's "From your phone" box.
   4 Oct ROUND 2 BUILT (404 tests + browser check, Haiku built both parts, I fixed and verified). User's choices (grill):
   the WEBSITE is the main screen (phone and PC); the PC runs hidden (setup.bat -> hidden.vbs/server.bat) and every
   5 min (web.engine_tick thread) does phone changes STRAIGHT AWAY (no y/n; phone.sync_once, kv phone_done stops doing a
   change twice) and moves HSBC '*statement*.pdf' from Downloads into statements (fintrack/downloads.py, kv
   downloads_seen). Phone can change spends, pay (+clear), left, this-cycle bills, answer sort/quick questions (change
   types in phone.apply_changes; site accepts them, cloud/flask_app.py MUST BE RE-PASTED on PythonAnywhere). Phone page:
   ⏳ Syncing N / ✅ Up to date / 📴 Offline, changes sent at once (localStorage queue), reloads when /stamp changes,
   tables become cards under 640px (CSS media query, [data-card] tables, data-label from headers). Email fetch ON HOLD
   (user asks HSBC for the PDF; check if HSBC can email it). Browser check script: see git log of this round.
   4 Oct evening: phone page acts instantly (removed spends vanish, numbers follow), every device applies ALL waiting
   changes (applyPending: pay/left/bills/cleared spends), cards = 3 equal columns. User ran setup.bat: hidden start
   WORKS on Windows (127.0.0.1:5000 with no window). User very happy. Next: wait for oddities from real use.
   OPEN (user, 4 Oct): ZOPA CREDIT CARDS (DD, saved 'common' by the user, cat Debt) is NOT in the Bills list. Real DB:
   paid once only, 14 Sep 2026 (100.00), inside the cycle still running, so pay_block/analysis (complete cycles only)
   skips it. auto_bills needs 2+ months, so it was asked. Agreed direction: a bill saved as common with a payment in
   the current cycle shows straight away (last = this cycle's amount). Write the failing test first (fake data).
   DECIDED (user, 4 Oct, see DECISIONS.md 'new and stopped bills'): every DD/SO straight into Bills even if paid once
   (marked 🆕 new until paid in 2 cycles); not paid in the last finished cycle = stopped and NOT counted (plus a tap
   'Stopped' button); card payments stay questions. BUILT 4 Oct (414 tests): questions.auto_bills (any DD/SO),
   spare.pay_block (new/stopped flags, bills paid only in the running cycle, spare.common_key = analyse's key: saved
   label or payee name, NOT the DD|..| item key), billchange get/set_stopped (kv stopped_bills: {key: ISO date} or
   "no" = Undo beats the auto stop), POST /stopped, phone change {type bill, key, stopped}, Stop / Undo button per
   bill. Real DB copy: Zopa Credit Cards shows (100, NEW). Haiku built it; I rewrote pay_block (it had re-keyed bills).
   Always-subscriptions (user, 4 Oct): fintrack/subs.py ALWAYS list (Claude/ANTHROPIC, ChatGPT/OPENAI, Google Play,
   Audible), card payments matched on description + detail (overseas payments: shop name is in detail), no regularity
   checks, refunds and cash never count. Add more names to ALWAYS. Real DB: all 4 show (ChatGPT stopped, last Jun 2026).
0. 3 Oct: user changed jobs (from Apr 2026); cycles were stuck at 31 Mar. Added `run.py wage NAME` (fintrack/wages.py).
   Same day: `run.py early` / `early N` (fintrack/early.py): rent sent the day before payday counts in the next cycle
   (moved payments are re-dated to the payday in load_moved; kv key moved_early).
   Then SPARE CASH = pay - bills only (no left over, no 'spend like usual'): see DECISIONS.md 3 Oct.
   Home page top = countdown (spare - typed spends); tiles = spare last month + 6-month avg (fintrack/sparehist.py). Also added setup.bat (shortcuts + start with Windows). v2 ideas from today are in FUTURE_FEATURES.md.
1. All 9 SPEC steps built (3 Oct). Home page tried on real data: liked it. Then added: bills first in "Last month's
   spending", and a 6 months / 12 months / year-so-far totals table (`fintrack/periods.py`, per-payment rule).
   Haiku warning (3 Oct): it hard-coded "3-mth avg", reverted the template it was told not to touch, and skipped a
   payment by a hard-coded name to match a wrong test sum. Read every diff; write small modules yourself. (3 Oct: step 7 checked on real data, adds up: 7.34 = IVA 279 paid - food shopping 240 less ...) (3 Oct: steps 5-6 checked on real data; last cycle missing only 7.34,
expected spare 292.74 on 2,677) (tests first, Haiku builds, verify yourself, tell the user the score). Terminal first.
2. 3 Oct small fixes DONE: pay block redone to the user's layout (bills avg/last -> SPARE CASH = No. 1 -> last month's
   non-bill spending by category -> left if usual; `spare.pay_block`), subscription spotter (`fintrack/subs.py`), a typed
   sentence at the rent question is not saved as a label. User skipped: show guessed categories in `fix`, "finished" kind.
   Still open: where.py bill note says "last month" even when the usual is the average.
   3 Oct BUILT (329 tests): Bills card under 'Add a spend'; every avg/last table = avg | Last month | Diff (green minus);
   unpaid bills show the average with * + footnote; tap a bill's Last month amount to change it for THIS cycle only
   (`fintrack/billchange.py`, kv 'bill_changes' with the cycle start, POST /bill, also used by run.py); subscriptions =
   one table: Monthly price | Last 12 months | This year ('Paid so far' dropped). 6/12 months table untouched.
   3 Oct BUILT (333 tests): bill boxes update spare cash/Diff/Total live as you type (page script, quiet POST /bill
   with X-Requested-With: fetch -> 204), several at once, x puts back. 'Left from last month' box under the pay box
   (POST /left, x removes; billchange.get_left, kv 'left_over_typed' with the cycle start): spare = pay + left - bills,
   hero line 'Pay + left - bills', terminal '+ Left from last month'.
   3 Oct BUILT (337 tests): '✏️ Move & rename' button on the home page: drag cards and rows (Bills, Last month's
   spending, Spending by category, Subscriptions) by the handle, click a name to rename it (empty = normal name),
   '↺ Put the order back'. Kept for good (`fintrack/layout.py`, kv 'layout'; POST /layout, /name, /layout/reset);
   page only. Cards are rendered in the saved order (Jinja set-blocks in home.html). Bill changes still reset at payday.
   Also: click a handle to pick a card/row, then arrow up/down moves it (drag did not auto-scroll for the user);
   dragging near the window edge now scrolls too.
   AGREED PLAN 3 Oct (v2, build in this order, one at a time, user says go):
   (1) BUILT 3 Oct (340 tests): `fintrack/update.py` (stdlib only; skips statements/, *.db, PDFs, .env; never
       deletes; version.txt), POST /update, start.bat restarts web.py on exit code 3, update.bat = python -m fintrack.update.
       Was: '🔄 Update' button on the home page + update.bat backup: fetch main.zip from GitHub, replace the code
       folder, keep statements + tracker.db. (3) BUILT 3 Oct (342 tests): DD/SO paid in 2+ months = bill automatically
       (questions.auto_bills, run before the question list), paid once = asked. (2) BUILT 3 Oct (345 tests): a new pay (different from the saved one) with typed spends
       asks 'New pay. Clear your typed spends?' on the page (confirm, clear=1 to POST /pay) and in run.py (y/n).
       (6a+6b) BUILT 3 Oct (353 tests): drop PDFs anywhere on the home page (or click the bar): `fintrack/inbox.py`
       (read from a temp copy; only new statements are kept in the statements folder), POST /upload; new items sorted on
       the page (`fintrack/sortpage.py`: buttons Bill/Random/One-off/Yearly, category, name; Copy for AI / Paste answers
       -> POST /sort/parse, POST /sort/save). The page starts with an empty database. 6c BUILT 3 Oct (359 tests): same bill /
       rent / typed-spend questions on the page ('❓ quick questions' card, `fintrack/pagequestions.py`, POST /ask; same rules
       and saved answers as run.py; kept typed spends in kv 'kept_spends'). run.py is now only needed for the extras.
       Was: (6+5) Drop a PDF on the home page: it is read in and the questions show on the page: a simple form
       (Bill / One-off / Yearly / Random + category per item) AND 'Copy for AI' / 'Paste answers'. Replaces the
       keyword question list. (4) BUILT 3 Oct (363 tests): new job spotted by itself (`fintrack/newjob.py`: no known wage for
       35+ days and another payer 500+ in 2+ months since -> '💼 Is X your new job?' in the quick questions; yes = add_payer,
       no = kv 'not_wage'). ALL of the 3 Oct v2 plan is built. See FUTURE_FEATURES.md.
   3 Oct late (365 tests): silent start: hidden.vbs runs server.bat (FT_QUIET, no window, no browser, restarts on
   exit 3) from the Startup shortcut; setup.bat remakes shortcuts (desktop = hidden.vbs open, icon static/app.ico);
   stop.bat kills web.py; /manifest.json + static/icon-*.png so Chrome/Edge can install it as an app. start.bat
   unchanged on purpose (never rewrite a running .bat). Windows scripts NOT tried on Windows yet: ask the user.
   END OF 3 Oct: user is testing v2 on real data (told to back up tracker.db first). NEXT SESSION: fix anything odd
   they report; then v3 = phone version on AWS:
   AGREED design in FUTURE_FEATURES.md 'v3 AGREED DESIGN (4 Oct)'. The user is drawing an architecture diagram
   first: check it against that section before building. 4 Oct: user had not run setup.bat yet (silent start untested).
3. After each step the user runs it on their 18 months and reports anything odd; add a test for every real oddity.
4. Ideas after that: FUTURE_FEATURES.md (email fetch, other banks...).
