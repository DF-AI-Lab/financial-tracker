# Where's My Money? v3: the whole app on PythonAnywhere

Master file for v3. Links back to: `CLAUDE.md` (v2 front page), `FUTURE_FEATURES.md` ('v3 AGREED DESIGN (4 Oct)', the old AWS idea).

## Where we are
- Plan: GitHub map **Map: v3, the whole app on PythonAnywhere** (issue 15). Built on branch `v3` (v3.4, 506 tests).
- Now: **Darren tests v3 on the PC** (V3_SETUP.md Part 1, :5001, copy of the data in v3data). Fix what he finds.
- Then: privacy check (tools/privacy_check.py) → Gmail app password → move-in on PythonAnywhere (V3_SETUP.md Part 2).

## Principles / constraints
- Darren is not a developer: exact copy-paste steps, short messages.
- Free plans only (PythonAnywhere free: 1 website, 512 MB disk).
- v2 stays untouched on `main` and on the PC until v3 is proven. v3 is built on a `v3` branch.
- Bank data: must stay private (PIN or better).
- Tests first, fake data only in the repo.

## 1. Idea
- Who: Darren only (one HSBC current account, one Zopa credit card).
- Problem: the PC has to be on and sync with the phone site; changes wait up to 5 min; two copies of the data.
- Destination: one website on PythonAnywhere that does everything (database, maths, PDF upload). PC and phone both just open it. No syncing.
- Success looks like: (to grill)
- Assumptions: PythonAnywhere free can run pdfplumber; data fits (under 5 MB vs 512 MB).
- Missing info: (to grill)
- In scope: the new look (built in v2.21), the maths, the database, dropping PDFs on the site, login.
- Out of scope: Firebase (not needed: PythonAnywhere runs Python). Other banks.

## 2. Steps
(draft from the chat, to grill)
1. Build v3 on a `v3` branch.
2. Test v3 on the PC at 127.0.0.1:5001 on a copy of the database, next to v2 at :5000.
3. Move in: v3 onto PythonAnywhere in place of the phone site, database copied up once.
4. v2 kept on the PC as a backup.

## 3. Choose & Prove

## 4. Fine Detail

## Decisions
| # | Decision | Why | Date |
|---|----------|-----|------|
| 1 | Stay on PythonAnywhere, no Firebase | PythonAnywhere runs Python, so the maths can live there; Firebase only stores data | 14 Oct 2026 |
| 2 | Build v3 on a `v3` branch, test on the PC at :5001, then move in | PythonAnywhere free has only 1 website; v2 must keep working meanwhile | 14 Oct 2026 |

## Parked (this version, not now)

## Research
- PythonAnywhere free: can it install pdfplumber? Any limits on uploads, CPU, always-on tasks?

## Prototypes / tests

## Risks
- Losing the automatic "move PDFs from Downloads" (only works on the PC).
- Bank data on someone else's server.

## Later / V2

## PRD

## Tickets

## Build / test progress

## Change log
- 14 Oct 2026: Project file created from the chat (brain dump: move everything to PythonAnywhere, build on v3 branch).
- 14 Oct 2026: Charted as a GitHub wayfinder map (issue 15); agreed: website only, email-code sign-in, PDFs not kept, database copied up once, one-tap Update, daily backups + download, extras into Settings.
- 15 Oct 2026: v3 built (v3.0-3.4): website entry, email code + 6-digit passcode (email weekly), backups, Fix an item, bill swap, privacy check. Darren testing.
