# Future features

_Ideas agreed but not built yet. Newest at the bottom._

## Built (30 Sep, with tests)
- Payday-to-payday cycles (wage = VERTU MOTORS PLC, 500 or more; a second credit within 10 days is a bonus in the same cycle)
- Common / random / one-off split over the last 6 complete cycles (bills: 4 of 6 cycles; others: 4 of 6 within 15%; one-off: 1,000 or more and not common)
- "Latest pay?" question at the end of `run.py` (Enter = last wage) showing what is left

- SQLite database (`tracker.db` next to the statements folder): statements and payments stored once, duplicates skipped
- Confirm-as-you-go questions (10 at a time; `common 1 2`, `oneoff 3`, `label 1 Rent`, `later`, `stop`), saved answers, and `run.py fix`
- Your answers decide common / random / one-off; items with the same label merge
- `run.py folder "C:\path"` remembers the statements folder

- Payday transfer rule (rent by transfer): within 2 days of payday, about the usual amount (10%), asked once with examples, remembered; a new price is noticed after 2 payments
- `all` answer and skipping tiny one-offs in the question list

## Next up
- **Categories report:** totals per label (Rent, Gas & Electric...) month by month and the 6-cycle average
  per label (the labels are already saved by the questions).
- **Missing statements warning:** if one statement does not start where the last one ended,
  say which month is missing (cycles across a gap are wrong).
- **"Same bill?" question:** when two bill names look similar (for example CAR LOAN PAYMENT
  and CAR PAYMENT OWED), ask the user once and remember the answer. Build the database with a
  place to store these answers.
- **"Off by X" marker:** when a statement's balance check is off by a small amount, keep the
  CHECK warning and show how much it is off by.

## Also planned
- Spending so far in the current cycle vs the typical cycle
- Fetch statement PDFs from email automatically
- Side income and bonus tracking
- Other banks

## Ideas for v2 (3 Oct, user)
- **(BUILT 3 Oct) Typed spends: full wipe on a new PDF.** v1 (now): typed spends that match the statement are removed,
  others are asked about, ones after the statement's last day stay. Idea: wipe them all when the next
  statement goes in. Open question: wipe at the statement's end date or at payday? Payday makes most sense
  but varies (end of the month), and a statement end date can fall after the next payday.
  **User's answer (3 Oct):** tie it to the pay box. When a new pay is typed in (home page or `run.py`), ask
  "New pay. Clear your typed spends? y/n". Typing the pay = "I got paid", so no date guessing. It is a question,
  not automatic, so fixing a typo in the pay does not wipe anything.
- **(BUILT 3 Oct) Home page order (user, 3 Oct):** 1 This month's pay, 2 Add a spend, 3 Bills, 4 Subscriptions,
  5 Where did last cycle's money go?, then the rest (Last month's spending, Spending by category,
  6 / 12 months / this year). Only `templates/home.html` changes (cards move, nothing else).
- **(BUILT 3 Oct) Easier question list (user, 3 Oct):** after showing the 10 items, ask one question at a time:
  "Which are Common? (numbers)" -> "Which are One-off?" -> "Which are Yearly?" -> the rest are Random.
  Then "Any categories to change?" Enter = skip each step. No keywords to remember.
- **(BUILT 3 Oct) DD / SO are Common by default (user, 3 Oct):** direct debits and standing orders go straight to Common
  without a question; only ask when one stops. Fewer questions. (Card and BP stay as now.)
- **(BUILT 3 Oct) New job spotted by itself (user, 3 Oct):** when no wage from a known payer for about 35 days but another
  credit of 500+ arrives (around payday, 2+ months), ask once: "Is PENDRAGON PAYROLL your new job? y/n".
  y -> saved with fintrack/wages.add_payer (no `run.py wage` command needed).
- **(BUILT 3 Oct) Updates without downloading ZIPs (user, 3 Oct):** an `update.bat` (or a button on the home page) that
  fetches the latest code from GitHub and replaces the code folder, leaving statements + tracker.db alone.

## Ideas for v3 (3 Oct, user)
- **Phone version, quick:** Tailscale (free) on the PC and phone: open the home page anywhere, data stays on the PC.
  Needs web.py to listen on the Tailscale address too. PC must be on.
- **Phone version, cloud (user's design):**
  - S3 + CloudFront: the web page itself (HTML/JS/CSS), cached.
  - Lambda (+ function URL or API Gateway): the maths: today's Flask routes become a JSON API (home data, pay,
    bill changes, spends, upload PDF, questions, layout).
  - S3: `tracker.db` (SQLite: Lambda downloads it, works, uploads it back; one user, so no clashes) and settings.
  - Must have: HTTPS (CloudFront) and a login (Cognito or a simple password), S3 bucket private, versioning on
    (every save kept = free backups). About GBP 0-1 a month on the free tier.
  - Work: split home.html into a static page that fetches JSON; pdfplumber in a Lambda layer; a one-time
    upload of today's tracker.db; step-by-step AWS setup guide for the user.

### v3 AGREED DESIGN (4 Oct, user) - phone version on AWS, PC stays the boss
- **PC = master.** Main app, local `tracker.db`, all the real maths. Nothing about the PC app changes.
- **S3 statements bucket:** the statement PDFs live here for good. Both the PC (drop on the page) and the phone
  (upload on the phone page) can put PDFs in. ONLY the PC reads them into the local database (it checks the bucket for
  new PDFs when it starts and every so often).
- **S3 snapshot:** after every change the PC uploads an up-to-date JSON snapshot (what the home page shows) and a
  backup copy of tracker.db (versioning on = history of backups).
- **S3 + CloudFront:** the bare-bones phone page (HTTPS). It shows the snapshot. What-ifs on the phone (change a bill,
  add spends, left from last month) are worked out on the phone and kept on the phone only, never sent to the PC;
  a new snapshot starts them fresh.
- **Lambda = gatekeeper:** checks the token, hands the snapshot to the phone, gives the phone a one-time upload link
  for a PDF. Buckets stay private.
- **Login = a token, no login screens:** open a secret link once on the phone, the token is remembered on the phone.
  New token = old phone locked out. (Cognito possible later if wanted.)
- PC needs an AWS key limited to these buckets only. Excel copy in OneDrive also discussed (optional, not agreed).
